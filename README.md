# maubot-redaction-regex

Matrix bot plugin that moderates messages based on regular expressions configured by the user.
It scans messages for matches against specified patterns and performs configurable actions when
a match is found.

## Features

- **Message Scanning**: Monitors all messages in rooms the bot is added to.
- **Customisable Patterns**: Supports an array of user-defined regex patterns.
- **Configurable Actions**: Allows actions like redacting messages, banning users, and reporting
  events to a moderation room.
- **Efficient Matching**: Compiles regex patterns at startup for performance.

## Requirements

- **Maubot**: Runs within the Maubot framework.
- **Python Dependencies**: Utilises the standard `re` module; no additional dependencies outside
  of Maubot.

## Installation

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/tcpipuk/maubot-redaction-regex
   ```

   Zip the plugin files and upload through the Maubot admin interface. Ensure the plugin is
   configured and enabled.

2. **Configure the Plugin**:
   See configuration section below for a summary of settings in the Maubot UI.

## Configuration

Edit `base-config.yaml` to set:

- `patterns`: List of regex patterns to match against messages.
- `actions`:
  - `redact_message`: Redact messages that match (default: `false`).
  - `ban_user`: Ban the user who sent a matching message (default: `false`).
  - `report_to_room`: Room ID for reporting; messages will be sent to this room when a match
    is found (default: empty string, reporting disabled).
    > **Note**: This can be a room alias (like `#room:server`), but using a room ID
    > (like `!roomid:server`) is more efficient.

## Usage

Once installed and configured, `regexmoderator` will automatically monitor messages in rooms
it's added to and take configured actions when messages match any of the defined patterns.

## Contributing

Contributions are welcome! Open an issue or submit a pull request on GitHub.

## License

This project is licensed under the GPLv3 License. See the [LICENSE](LICENSE) file for details.
