#!/usr/bin/env python3
"""
Ghostfolio Alpaca Sync - Main Entry Point
Syncs Alpaca trading activities to Ghostfolio portfolio tracker
"""

import os
import sys
import logging
from dotenv import load_dotenv
from SyncAlpaca import SyncAlpaca, load_symbol_mapping

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Operation constants
SYNC_ALPACA = "SYNC_ALPACA"
DELETE_ALL_ACTS = "DELETE_ALL_ACTS"
GET_ALL_ACTS = "GET_ALL_ACTS"


def get_env(key: str, default: str = "") -> str:
    """Get environment variable with default value"""
    return os.getenv(key, default).strip()


def main():
    """Main execution function"""
    logger.info("Ghostfolio Alpaca Sync starting...")

    # Load environment variables
    alpaca_api_key = get_env('ALPACA_API_KEY')
    alpaca_secret_key = get_env('ALPACA_SECRET_KEY')
    alpaca_base_url = get_env('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

    ghost_host = get_env('GHOST_HOST', 'https://ghostfol.io')
    ghost_token = get_env('GHOST_TOKEN')
    ghost_key = get_env('GHOST_KEY')
    ghost_account_name = get_env('GHOST_ACCOUNT_NAME', 'Alpaca')
    ghost_currency = get_env('GHOST_CURRENCY', 'USD')
    ghost_platform_id = get_env('GHOST_PLATFORM_ID', '')

    operation = get_env('OPERATION', SYNC_ALPACA)

    # Validate required credentials
    if not alpaca_api_key or not alpaca_secret_key:
        logger.error("Missing required Alpaca credentials (ALPACA_API_KEY, ALPACA_SECRET_KEY)")
        sys.exit(1)

    if not ghost_token and not ghost_key:
        logger.error("Missing Ghostfolio credentials (GHOST_TOKEN or GHOST_KEY required)")
        sys.exit(1)

    # Load symbol mapping
    symbol_mapping = load_symbol_mapping('mapping.yaml')
    if symbol_mapping:
        logger.info(f"Loaded {len(symbol_mapping)} symbol mappings")
    else:
        symbol_mapping = {}
        logger.info("No symbol mappings configured")

    # Initialize sync instance
    try:
        sync = SyncAlpaca(
            alpaca_api_key=alpaca_api_key,
            alpaca_secret_key=alpaca_secret_key,
            alpaca_base_url=alpaca_base_url,
            ghost_host=ghost_host,
            ghost_token=ghost_token,
            ghost_key=ghost_key,
            ghost_account_name=ghost_account_name,
            ghost_currency=ghost_currency,
            ghost_platform_id=ghost_platform_id if ghost_platform_id else None,
            symbol_mapping=symbol_mapping
        )
    except Exception as e:
        logger.error(f"Failed to initialize sync: {e}")
        sys.exit(1)

    # Execute operation
    try:
        if operation == SYNC_ALPACA:
            logger.info("Starting sync operation...")
            sync.sync()

        elif operation == GET_ALL_ACTS:
            logger.info("Fetching all activities...")
            sync.get_all_activities()

        elif operation == DELETE_ALL_ACTS:
            logger.info("WARNING: Deleting all activities!")
            # Add a confirmation mechanism in production
            sync.delete_all_activities()

        else:
            logger.error(f"Unknown operation: {operation}")
            logger.info(f"Valid operations: {SYNC_ALPACA}, {GET_ALL_ACTS}, {DELETE_ALL_ACTS}")
            sys.exit(1)

        logger.info("\nOperation completed successfully!")

    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
