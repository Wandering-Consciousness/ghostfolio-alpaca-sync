# Ghostfolio Alpaca Sync

Automatically sync your Alpaca trading activities to Ghostfolio portfolio tracker.

## Features

- **Automatic Syncing**: Sync trades, dividends, interest, and fees from Alpaca to Ghostfolio
- **Deduplication**: Smart deduplication prevents duplicate activities
- **Scheduled Runs**: Optional cron scheduling for automated syncing
- **Symbol Mapping**: Configurable symbol mapping for compatibility
- **Docker Support**: Easy deployment with Docker/Docker Compose
- **Multiple Operations**: Sync, view, or delete activities

## Supported Activity Types

| Alpaca Activity | Ghostfolio Type | Description |
|----------------|-----------------|-------------|
| FILL (buy) | BUY | Stock purchases |
| FILL (sell) | SELL | Stock sales |
| DIV* | DIVIDEND | All dividend types |
| INT* | INTEREST | Interest payments |
| FEE, CFEE | FEE | Fees and commissions |

## Prerequisites

- Python 3.11+ (for local running) or Docker
- Alpaca account with API credentials
- Ghostfolio instance with API access

## Quick Start

### Option 1: Docker Compose (Recommended)

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ghostfolio-alpaca-sync
   ```

2. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   nano .env
   ```

3. Edit `.env` with your credentials:
   ```env
   # Alpaca Configuration
   ALPACA_API_KEY=your_alpaca_api_key
   ALPACA_SECRET_KEY=your_alpaca_secret_key
   ALPACA_BASE_URL=https://paper-api.alpaca.markets

   # Ghostfolio Configuration
   GHOST_HOST=https://ghostfol.io
   GHOST_TOKEN=your_ghostfolio_token
   GHOST_ACCOUNT_NAME=Alpaca
   GHOST_CURRENCY=USD

   # Optional: Set for scheduled syncing
   CRON=0 */6 * * *
   ```

4. Run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

### Option 2: Local Python

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables (copy from `.env.example`)

3. Run the sync:
   ```bash
   python main.py
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ALPACA_API_KEY` | Yes | - | Alpaca API key |
| `ALPACA_SECRET_KEY` | Yes | - | Alpaca secret key |
| `ALPACA_BASE_URL` | No | `https://paper-api.alpaca.markets` | API base URL (use `https://api.alpaca.markets` for live) |
| `GHOST_HOST` | No | `https://ghostfol.io` | Ghostfolio instance URL |
| `GHOST_TOKEN` | Yes* | - | Ghostfolio bearer token |
| `GHOST_KEY` | Yes* | - | Ghostfolio user key (alternative to token) |
| `GHOST_ACCOUNT_NAME` | No | `Alpaca` | Account name in Ghostfolio |
| `GHOST_CURRENCY` | No | `USD` | Account currency |
| `OPERATION` | No | `SYNC_ALPACA` | Operation mode (see below) |
| `CRON` | No | - | Cron schedule for automated syncing |

*Either `GHOST_TOKEN` or `GHOST_KEY` is required

### Getting Ghostfolio Credentials

**Option 1: Bearer Token (Preferred)**
1. Log into Ghostfolio
2. Go to Settings → API
3. Copy your bearer token
4. Set `GHOST_TOKEN` in `.env`

**Option 2: User Key**
1. Log into Ghostfolio
2. Go to Settings → API
3. Copy your API key
4. Set `GHOST_KEY` in `.env`

### Getting Alpaca API Credentials

1. Log into [Alpaca](https://alpaca.markets/)
2. Go to Paper Trading or Live Trading
3. Generate API credentials
4. Copy API Key and Secret Key
5. For paper trading, use `https://paper-api.alpaca.markets`
6. For live trading, use `https://api.alpaca.markets`

### Symbol Mapping

Edit `mapping.yaml` to customize symbol mappings:

```yaml
symbol_mapping:
  # Map Alpaca symbols to Ghostfolio-compatible symbols
  BTC/USD: BTCUSD
  ETH/USD: ETHUSD
  # Add more mappings as needed
```

## Operation Modes

Set the `OPERATION` environment variable to control behavior:

### SYNC_ALPACA (Default)
Syncs activities from Alpaca to Ghostfolio:
```bash
OPERATION=SYNC_ALPACA python main.py
```

### GET_ALL_ACTS
View all activities for the Alpaca account in Ghostfolio:
```bash
OPERATION=GET_ALL_ACTS python main.py
```

### DELETE_ALL_ACTS
Delete all activities for the Alpaca account (use with caution):
```bash
OPERATION=DELETE_ALL_ACTS python main.py
```

## Scheduled Syncing

Use the `CRON` environment variable to schedule automatic syncs:

```env
# Every 6 hours
CRON=0 */6 * * *

# Daily at midnight
CRON=0 0 * * *

# Weekdays at 9 AM
CRON=0 9 * * 1-5

# Every hour during market hours (9:30 AM - 4 PM ET, Mon-Fri)
CRON=30 9-16 * * 1-5
```

Leave `CRON` empty for one-time runs.

## How It Works

1. **Fetch Activities**: Retrieves activities from Alpaca API (trades, dividends, interest, fees)
2. **Transform**: Converts Alpaca format to Ghostfolio format
3. **Deduplicate**: Compares with existing Ghostfolio activities to avoid duplicates
4. **Import**: Sends new activities to Ghostfolio in batches
5. **Update Balance**: Updates account cash balance from Alpaca

### Deduplication

The sync uses Alpaca activity IDs stored in the `comment` field to prevent duplicates:
```
comment: "alpaca_id=20241110123456789"
```

This ensures activities are never imported twice, even if you run the sync multiple times.

## Docker Usage

### Build and Run
```bash
# Build the image
docker build -t ghostfolio-alpaca-sync .

# Run one-time sync
docker run --env-file .env ghostfolio-alpaca-sync

# Run with cron scheduling
docker run --env-file .env -e CRON="0 */6 * * *" ghostfolio-alpaca-sync
```

### Docker Compose
```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

## Troubleshooting

### No activities imported
- Check that you have activities in your Alpaca account
- Verify your Alpaca API credentials are correct
- Check the logs for API errors

### Duplicate activities
- The sync should automatically prevent duplicates
- If duplicates occur, they may have been manually imported
- Use `OPERATION=DELETE_ALL_ACTS` to reset (careful!)

### Authentication errors
- Verify your Ghostfolio token/key is valid
- Check that your Alpaca API credentials are correct
- Ensure the Alpaca base URL matches your account type (paper vs live)

### Symbol not found in Ghostfolio
- Add a symbol mapping in `mapping.yaml`
- Check that the symbol exists in Yahoo Finance (default data source)
- For crypto, you may need to use a different data source

## Development

### Project Structure
```
ghostfolio-alpaca-sync/
├── main.py              # Entry point
├── SyncAlpaca.py        # Main sync logic
├── alpaca_client.py     # Alpaca API client
├── ghostfolio_client.py # Ghostfolio API client
├── mapping.yaml         # Symbol mapping config
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker build config
├── docker-compose.yml  # Docker Compose config
├── entrypoint.sh       # Container entrypoint
├── run.sh              # Cron wrapper script
└── README.md           # This file
```

### Running Tests
```bash
# Test Alpaca connection
OPERATION=GET_ALL_ACTS python main.py

# Dry run sync (test without importing)
python main.py  # Edit SyncAlpaca.py to set dry_run=True
```

## Architecture

This project follows the design pattern of [ghostfolio-sync](https://github.com/dickwolff/ghostfolio-sync) (Interactive Brokers integration):

- Single-class design for main sync logic
- Deduplication using unique transaction IDs
- Chunked imports (10 activities per batch)
- Docker-ready with cron support
- Extensive logging for troubleshooting

## Limitations

- Alpaca supports US stocks and crypto primarily
- Commission-free trading means fees are typically $0
- Some Alpaca activity types (transfers, journal entries) are not synced
- Requires internet access to both Alpaca and Ghostfolio APIs

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Related Projects

- [Ghostfolio](https://github.com/ghostfolio/ghostfolio) - Open source portfolio tracker
- [ghostfolio-sync](https://github.com/dickwolff/ghostfolio-sync) - Interactive Brokers sync
- [alpaca-py](https://github.com/alpacahq/alpaca-py) - Official Alpaca Python SDK

## Support

For issues and questions:
- Check the [Issues](../../issues) page
- Review Ghostfolio documentation
- Review Alpaca API documentation

## Disclaimer

This software is provided as-is for syncing trading data. Always verify imported data for accuracy. Not responsible for any financial losses or data issues.
