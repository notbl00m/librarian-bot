# Librarian Bot

A modular Discord bot for automated audiobook and ebook management using Prowlarr (for searching indexers) and qBittorrent (for downloading), with automatic library organization.

## Features

- 🔍 **Prowlarr Integration**: Search multiple indexers (including MyAnonamouse) from Discord
- 📥 **qBittorrent Integration**: Automated torrent downloading with monitoring
- 📚 **Automatic Organization**: Downloads automatically organized by author using Google Books API
- 🔗 **Smart Hardlinks**: Preserves seeding while organizing files
- 👥 **Admin Approval**: Role-based approval workflow for downloads
- 📧 **User Notifications**: DM notifications for request approval and completion
- ⚡ **Async Throughout**: Built with async/await for responsiveness

## Project Structure

```
librarian-bot/
├── bot.py                 # Main Discord bot entry point
├── config.py             # Configuration management
├── prowlarr_api.py       # Prowlarr search functions
├── qbit_client.py        # qBittorrent download management
├── library_organizer.py  # File organization and metadata extraction
├── discord_commands.py   # Discord command handlers
├── discord_views.py      # Discord UI components (buttons, views)
├── utils.py              # Helper functions
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
└── README.md            # This file
```

## Installation

### Prerequisites
- Python 3.8+
- Discord Bot with intents enabled
- Running Prowlarr instance
- Running qBittorrent instance
- Google Books API key (optional, for better metadata)

### Setup

1. **Clone and install dependencies**:
   ```bash
   git clone https://github.com/yourusername/librarian-bot.git
   cd librarian-bot
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Run the bot**:
   ```bash
   python bot.py
   ```

## Configuration

See `.env.example` for all available configuration options:

### Required Variables
- `DISCORD_TOKEN` - Your Discord bot token
- `PROWLARR_API_KEY` - Prowlarr API key
- `QBIT_PASSWORD` - qBittorrent password
- `QBIT_DOWNLOAD_PATH` - Directory where qBit downloads files
- `LIBRARY_PATH` - Directory for organized library

### Optional Variables
- `GOOGLE_BOOKS_API_KEY` - For accurate metadata extraction
- `ENABLE_HARDLINKS` - Create hardlinks instead of copies (default: true)
- `AUTO_APPROVE_MIN_SEEDERS` - Auto-approve torrents with X+ seeders (default: 0)

## Usage

### Discord Commands

- `!request <query>` - Search for a book/audiobook
  - Select result by reacting with numbers (1️⃣-5️⃣)
  - Admin approves/denies with buttons
  - On approval, automatically downloads and organizes

- `!status` - View active downloads and organization jobs
- `!help` - Show available commands

## Workflow

1. **User Request**: `!request The Name of the Wind`
2. **Search Results**: Bot displays top 5 results with metadata
3. **User Selection**: React with 1️⃣-5️⃣
4. **Admin Approval**: Admin must approve via button click
5. **Download**: Approved torrent sent to qBittorrent
6. **Monitoring**: Bot monitors download completion
7. **Organization**: Completed download automatically organized by author
8. **Notification**: Requester notified with library location

## Development

### Running in Development Mode
```bash
ENVIRONMENT=development python bot.py
```

### Code Structure

Each module has a specific responsibility:
- `config.py` - Centralized configuration
- `prowlarr_api.py` - External API interaction (Prowlarr)
- `qbit_client.py` - External API interaction (qBittorrent)
- `library_organizer.py` - File system operations and metadata
- `discord_commands.py` - Bot command handlers
- `discord_views.py` - UI components and interactions
- `utils.py` - Shared utilities and helpers

## API Integration

### Prowlarr
- REST API for searching indexers
- Returns results with download URLs and metadata
- Supports custom category/indexer filtering

### qBittorrent
- WebAPI for adding torrents and monitoring
- Polling-based completion detection
- Support for magnet links and .torrent files

### Google Books API
- Metadata extraction for accurate author/title information
- Used during library organization
- Optional (degrades gracefully without it)

## Error Handling

The bot includes comprehensive error handling:
- Graceful degradation when services are unavailable
- Detailed error logging
- User-friendly error messages in Discord
- Automatic retry logic for transient failures

## Logging

Configure logging via environment variables:
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR (default: INFO)
- `LOG_FILE` - Optional file path for logging output

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT License - see LICENSE file for details

## Support

For issues or questions, please open an issue on GitHub.
