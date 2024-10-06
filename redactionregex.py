"""
Regex Moderator Plugin for Maubot.

This plugin monitors messages and takes actions when messages match configured regex patterns.

Features:
- Monitors messages in rooms the bot is a member of.
- Supports user-defined regular expression patterns.
- Performs configurable actions such as message redaction, user banning, and reporting events to a moderation room.
- Compiles regex patterns at startup for efficient matching.

Requirements:
- Maubot framework.
- Python standard library (`re` module).

Usage:
- Install and configure the plugin in Maubot.
- Define regex patterns and actions in the configuration.
- Add the bot to rooms to start monitoring messages.

License:
- This project is licensed under the GPLv3 License. See the LICENSE file for details.
"""

import re
from asyncio import Semaphore
from typing import List, Pattern, Type

from maubot import MessageEvent, Plugin  # type: ignore
from maubot.handlers import listener
from mautrix.errors import MForbidden, MUnknown
from mautrix.types import (
    EventType,
    MessageEventContent,
    RoomAlias,
    RoomID,
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class Config(BaseProxyConfig):
    """
    Configuration manager for the RedactionRegexPlugin.

    Attributes:
        patterns (List[str]): List of regex patterns to match against messages.
        actions (dict): Dictionary of actions to perform on matching messages.
    """

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        """
        Update the configuration with new values.

        Args:
            helper (ConfigUpdateHelper): Helper object to copy configuration values.
        """
        helper.copy("patterns")
        helper.copy("actions")


class RedactionRegexPlugin(Plugin):
    """
    Plugin to moderate messages based on regex patterns.

    Attributes:
        patterns (List[Pattern[str]]): Compiled regex patterns.
        actions (dict): Actions to perform when a pattern matches.
        report_to_room (str): Room ID to report matching messages to.
        semaphore (Semaphore): Semaphore to prevent concurrent handling of events.
    """

    patterns: List[Pattern[str]] = []
    actions = {}
    report_to_room: str = ""
    semaphore = Semaphore(1)

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        """
        Get the configuration class for the plugin.

        Returns:
            Type[BaseProxyConfig]: Configuration class.
        """
        return Config

    async def start(self) -> None:
        """
        Initialise the plugin by loading the config and compiling regex patterns.
        """
        await super().start()
        if not isinstance(self.config, Config):
            self.log.error("Plugin not yet configured.")
            return

        self.config.load_and_update()
        self.actions = self.config["actions"]
        self.report_to_room = str(self.actions.get("report_to_room", ""))
        if self.report_to_room.startswith("#"):
            try:
                report_room_info = await self.client.resolve_room_alias(
                    RoomAlias(self.report_to_room)
                )
                self.report_to_room = report_room_info.room_id
            except MUnknown:
                self.log.warning(f"Failed to resolve room alias {self.report_to_room}")
                self.report_to_room = ""
        elif self.report_to_room and not self.report_to_room.startswith("!"):
            self.log.warning("Invalid room ID or alias provided for report_to_room")
            self.report_to_room = ""

        # Compile regex patterns
        pattern_strings = self.config["patterns"]
        self.patterns = [re.compile(p) for p in pattern_strings]
        if not self.patterns:
            self.log.warning(
                "No patterns configured. The plugin will not match any messages."
            )
        self.log.info("Loaded RedactionRegexPlugin successfully")

    @listener.on(EventType.ROOM_MESSAGE)
    async def handle_message_event(self, evt: MessageEvent) -> None:
        """
        Handle message events and check against regex patterns.

        Args:
            evt (MessageEvent): The message event.
        """
        async with self.semaphore:
            content = evt.content
            if not isinstance(content, MessageEventContent):
                return

            # Extract message bodies to check
            bodies = []
            content_body = getattr(content, "body", None)
            if content_body:
                bodies.append(content_body)
            content_formatted_body = getattr(content, "formatted_body", None)
            if content_formatted_body:
                bodies.append(content_formatted_body)

            if not bodies:
                return

            # Check each body against all patterns
            for body in bodies:
                for pattern in self.patterns:
                    if pattern.search(body):
                        await self.take_actions(evt, pattern)
                        # Stop processing after first match and actions
                        return

    async def take_actions(self, evt: MessageEvent, pattern: Pattern[str]) -> None:
        """
        Perform configured actions when a pattern matches.

        Args:
            evt (MessageEvent): The message event.
            pattern (Pattern[str]): The regex pattern that matched.
        """
        # Prepare a report message
        report_message = (
            f"Message from {evt.sender} in {evt.room_id} matched pattern "
            f"'{pattern.pattern}':\n> {evt.content.body}"
        )

        # Report to a specific room
        if self.report_to_room:
            try:
                await self.client.send_text(
                    room_id=RoomID(self.report_to_room), text=report_message
                )
                self.log.info(f"Sent report to {self.report_to_room}")
            except Exception as e:
                self.log.warning(
                    f"Failed to send message to {self.report_to_room}: {e}"
                )

        # Redact the message if redacting is enabled
        if self.actions.get("redact_message", False):
            try:
                await self.client.redact(
                    room_id=evt.room_id,
                    event_id=evt.event_id,
                    reason="Inappropriate content",
                )
                self.log.info(f"Redacted message in {evt.room_id}")
            except MForbidden:
                self.log.warning(f"Failed to redact message in {evt.room_id}")

        # Ban the user if banning is enabled
        if self.actions.get("ban_user", False):
            try:
                await self.client.ban_user(
                    room_id=evt.room_id,
                    user_id=evt.sender,
                    reason="Inappropriate content",
                )
                self.log.info(f"Banned user {evt.sender} from {evt.room_id}")
            except MForbidden:
                self.log.warning(f"Failed to ban user {evt.sender} from {evt.room_id}")
