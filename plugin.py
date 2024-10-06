"""
Regex Moderator Plugin for Maubot

This plugin monitors messages and takes actions when messages match configured regex patterns.
"""

import re
from asyncio import Semaphore
from typing import List, Pattern, Type

from maubot import MessageEvent, Plugin  # type: ignore
from maubot.handlers import event
from mautrix.errors import MBadJSON, MForbidden
from mautrix.types import (
    EventType,
    MessageEventContent,
    RoomAlias,
    RoomID,
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class Config(BaseProxyConfig):
    """
    Configuration manager for the RegexModeratorPlugin.
    """

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        """
        Update the configuration with new values.

        :param helper: Helper object to copy configuration values.
        """
        helper.copy("patterns")
        helper.copy("actions")


class RegexModeratorPlugin(Plugin):
    """
    Plugin to moderate messages based on regex patterns.
    """

    patterns: List[Pattern] = []
    actions = {}
    report_to_room = ""
    semaphore = Semaphore(1)

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        """
        Get the configuration class for the plugin.

        :return: Configuration class.
        """
        return Config

    async def start(self) -> None:
        """
        Initialise plugin by loading config and compiling regex patterns.
        """
        await super().start()
        try:
            if not isinstance(self.config, Config):
                self.log.error("Plugin not yet configured.")
            else:
                self.config.load_and_update()
                self.actions = self.config["actions"]
                self.report_to_room = str(self.actions.get("report_to_room", ""))
                if self.report_to_room.startswith("#"):
                    report_to_info = await self.client.resolve_room_alias(
                        RoomAlias(self.report_to_room)
                    )
                    self.report_to_room = report_to_info.room_id
                elif self.report_to_room and not self.report_to_room.startswith("!"):
                    self.log.warning(
                        "Invalid room ID or alias provided for report_to_room"
                    )

                # Compile regex patterns
                pattern_strings = self.config["patterns"]
                self.patterns = [re.compile(p) for p in pattern_strings]
                if not self.patterns:
                    self.log.warning(
                        "No patterns configured. The plugin will not match any messages."
                    )
                self.log.info("Loaded regexmoderator successfully")
        except Exception as e:
            self.log.error(f"Error during start: {e}")

    @event.on(EventType.ROOM_MESSAGE)
    async def handle_message_event(self, evt: MessageEvent) -> None:
        """
        Handle message events and check against regex patterns.

        :param evt: The message event.
        """
        async with self.semaphore:
            try:
                content = evt.content
                if not isinstance(content, MessageEventContent):
                    return

                # Extract message bodies to check
                bodies = []
                if content.body:
                    bodies.append(content.body)
                if content.formatted_body:
                    bodies.append(content.formatted_body)

                if not bodies:
                    return

                # Check each body against all patterns
                for body in bodies:
                    for pattern in self.patterns:
                        if pattern.search(body):
                            await self.take_actions(evt, pattern)
                            # Stop processing after first match and actions
                            return
            except Exception as e:
                self.log.error(f"Error handling message event: {e}")

    async def take_actions(self, evt: MessageEvent, pattern: Pattern) -> None:
        """
        Perform configured actions when a pattern matches.

        :param evt: The message event.
        :param pattern: The regex pattern that matched.
        """
        try:
            # Prepare a report message
            report_message = (
                f"Message from {evt.sender} in {evt.room_id} matched pattern '{pattern.pattern}':\n"
                f"> {evt.content.body}"
            )

            # Report to a specific room
            if self.report_to_room:
                try:
                    await self.client.send_text(
                        room_id=RoomID(self.report_to_room), text=report_message
                    )
                    self.log.info(f"Sent report to {RoomID(self.report_to_room)}")
                except MBadJSON as e:
                    self.log.warning(
                        f"Failed to send message to {RoomID(self.report_to_room)}: {e}"
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
                    self.log.warning(
                        f"Failed to ban user {evt.sender} from {evt.room_id}"
                    )
        except Exception as e:
            self.log.error(f"Error taking actions: {e}")
