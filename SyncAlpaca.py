"""
Main Alpaca to Ghostfolio Sync Logic
Coordinates data fetching, transformation, and import
"""

import logging
import json
import re
import yaml
from datetime import datetime
from typing import Dict, List, Optional

from alpaca_client import AlpacaClient
from ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)


class SyncAlpaca:
    """Main class for syncing Alpaca activities to Ghostfolio"""

    # Activity type mapping from Alpaca to Ghostfolio
    ACTIVITY_TYPE_MAPPING = {
        'FILL': 'TRADE',  # Will be BUY or SELL based on side
        'DIV': 'DIVIDEND',
        'DIVCGL': 'DIVIDEND',  # Dividend (capital gain long term)
        'DIVCGS': 'DIVIDEND',  # Dividend (capital gain short term)
        'DIVFEE': 'FEE',
        'DIVFT': 'DIVIDEND',  # Dividend (foreign tax)
        'DIVNRA': 'DIVIDEND',  # Dividend (NRA withholding)
        'DIVROC': 'DIVIDEND',  # Dividend (return of capital)
        'DIVTW': 'DIVIDEND',  # Dividend (tax withheld)
        'DIVTXEX': 'DIVIDEND',  # Dividend (tax exempt)
        'INT': 'INTEREST',
        'INTNRA': 'INTEREST',  # Interest (NRA withholding)
        'INTTW': 'INTEREST',  # Interest (tax withheld)
        'FEE': 'FEE',
        'CFEE': 'FEE',  # Commission fee
        # Note: Other types like ACATC, ACATS, JNL, JNLC, JNLS, MA, etc.
        # are transfers and may not map directly to Ghostfolio activities
    }

    def __init__(
        self,
        alpaca_api_key: str,
        alpaca_secret_key: str,
        alpaca_base_url: str,
        ghost_host: str,
        ghost_token: Optional[str] = None,
        ghost_key: Optional[str] = None,
        ghost_account_name: str = "Alpaca",
        ghost_currency: str = "USD",
        symbol_mapping: Optional[Dict[str, str]] = None
    ):
        """
        Initialize sync instance

        Args:
            alpaca_api_key: Alpaca API key
            alpaca_secret_key: Alpaca secret key
            alpaca_base_url: Alpaca base URL
            ghost_host: Ghostfolio host URL
            ghost_token: Ghostfolio bearer token
            ghost_key: Ghostfolio user key
            ghost_account_name: Name for the Ghostfolio account
            ghost_currency: Currency for the account
            symbol_mapping: Dict mapping Alpaca symbols to Ghostfolio symbols
        """
        self.alpaca = AlpacaClient(alpaca_api_key, alpaca_secret_key, alpaca_base_url)
        self.ghostfolio = GhostfolioClient(ghost_host, ghost_token, ghost_key)

        self.ghost_account_name = ghost_account_name
        self.ghost_currency = ghost_currency
        self.symbol_mapping = symbol_mapping or {}
        self.account_id = None

    def sync(self, sync_days: Optional[int] = None):
        """
        Perform the main sync operation

        Args:
            sync_days: Number of days to sync (None = all history)
        """
        logger.info("=" * 60)
        logger.info("Starting Alpaca to Ghostfolio sync")
        logger.info("=" * 60)

        # Step 1: Get or create Ghostfolio account
        self.account_id = self._get_or_create_account()

        # Step 2: Fetch Alpaca activities
        logger.info("\n--- Fetching activities from Alpaca ---")
        alpaca_activities = self._fetch_alpaca_activities(sync_days)

        if not alpaca_activities:
            logger.info("No activities found in Alpaca")
            return

        # Step 3: Transform activities to Ghostfolio format
        logger.info("\n--- Transforming activities ---")
        ghostfolio_activities = self._transform_activities(alpaca_activities)

        # Step 4: Get existing activities from Ghostfolio
        logger.info("\n--- Fetching existing activities from Ghostfolio ---")
        existing_activities = self.ghostfolio.get_activities(accounts=[self.account_id])

        # Step 5: Find new activities (deduplication)
        logger.info("\n--- Deduplicating activities ---")
        new_activities = self._deduplicate_activities(ghostfolio_activities, existing_activities)

        if not new_activities:
            logger.info("No new activities to import")
        else:
            # Step 6: Import new activities
            logger.info(f"\n--- Importing {len(new_activities)} new activities ---")
            self._import_activities(new_activities)

        # Step 7: Update account balance
        logger.info("\n--- Updating account balance ---")
        self._update_account_balance()

        logger.info("\n" + "=" * 60)
        logger.info("Sync completed successfully!")
        logger.info("=" * 60)

    def _get_or_create_account(self) -> str:
        """
        Get existing account or create new one

        Returns:
            Account ID
        """
        logger.info(f"Looking for account: {self.ghost_account_name}")

        account = self.ghostfolio.get_account_by_name(self.ghost_account_name)

        if account:
            return account['id']

        logger.info(f"Account not found, creating new account: {self.ghost_account_name}")
        account_id = self.ghostfolio.create_account(
            name=self.ghost_account_name,
            currency=self.ghost_currency
        )

        return account_id

    def _fetch_alpaca_activities(self, sync_days: Optional[int] = None) -> List[Dict]:
        """
        Fetch activities from Alpaca

        Args:
            sync_days: Number of days to sync

        Returns:
            List of Alpaca activities
        """
        # Calculate date range if sync_days specified
        after_date = None
        if sync_days:
            from datetime import timedelta
            after_date = (datetime.now() - timedelta(days=sync_days)).strftime('%Y-%m-%d')
            logger.info(f"Syncing activities from the last {sync_days} days (after {after_date})")

        # Fetch all activities
        # Note: We fetch all types and filter/transform as needed
        activities = self.alpaca.get_activities(
            after=after_date,
            direction='asc'  # Oldest first for chronological import
        )

        logger.info(f"Fetched {len(activities)} activities from Alpaca")

        return activities

    def _transform_activities(self, alpaca_activities: List[Dict]) -> List[Dict]:
        """
        Transform Alpaca activities to Ghostfolio format

        Args:
            alpaca_activities: List of Alpaca activities

        Returns:
            List of Ghostfolio-formatted activities
        """
        ghostfolio_activities = []

        for activity in alpaca_activities:
            activity_type = activity.get('activity_type')

            # Skip unsupported activity types
            if activity_type not in self.ACTIVITY_TYPE_MAPPING:
                logger.debug(f"Skipping unsupported activity type: {activity_type}")
                continue

            try:
                if activity_type == 'FILL':
                    # Trade activity
                    transformed = self._transform_trade_activity(activity)
                elif activity_type.startswith('DIV'):
                    # Dividend activity
                    transformed = self._transform_dividend_activity(activity)
                elif activity_type.startswith('INT'):
                    # Interest activity
                    transformed = self._transform_interest_activity(activity)
                elif activity_type in ['FEE', 'CFEE']:
                    # Fee activity
                    transformed = self._transform_fee_activity(activity)
                else:
                    logger.warning(f"Unhandled activity type: {activity_type}")
                    continue

                if transformed:
                    ghostfolio_activities.append(transformed)

            except Exception as e:
                logger.error(f"Error transforming activity: {e}")
                logger.debug(f"Activity data: {json.dumps(activity, indent=2)}")

        logger.info(f"Transformed {len(ghostfolio_activities)} activities")
        return ghostfolio_activities

    def _transform_trade_activity(self, activity: Dict) -> Optional[Dict]:
        """Transform a FILL (trade) activity"""
        # Determine buy or sell
        side = activity.get('side', '').upper()
        if side == 'BUY':
            order_type = 'BUY'
        elif side == 'SELL':
            order_type = 'SELL'
        else:
            logger.warning(f"Unknown trade side: {side}")
            return None

        symbol = self._map_symbol(activity.get('symbol', ''))
        quantity = abs(float(activity.get('qty', 0)))
        price = abs(float(activity.get('price', 0)))

        # Parse date
        transaction_time = activity.get('transaction_time', '')
        date = self._parse_date(transaction_time)

        # Alpaca activity ID for deduplication
        activity_id = activity.get('id', '')

        return {
            'accountId': self.account_id,
            'comment': f"alpaca_id={activity_id}",  # For deduplication
            'currency': 'USD',  # Alpaca is US-based
            'dataSource': 'YAHOO',  # Use Yahoo for US stocks
            'date': date,
            'fee': 0,  # Alpaca commission-free trading
            'quantity': quantity,
            'symbol': symbol,
            'type': order_type,
            'unitPrice': price,
            '_alpaca_id': activity_id,  # Store for deduplication
            '_alpaca_order_id': activity.get('order_id', '')
        }

    def _transform_dividend_activity(self, activity: Dict) -> Optional[Dict]:
        """Transform a dividend activity"""
        symbol = self._map_symbol(activity.get('symbol', ''))
        net_amount = float(activity.get('net_amount', 0))
        qty = float(activity.get('qty', 1))

        # Calculate per-share amount
        if qty > 0:
            per_share = abs(net_amount / qty)
        else:
            per_share = abs(net_amount)

        # Parse date
        date_str = activity.get('date', '')
        date = self._parse_date(date_str)

        activity_id = activity.get('id', '')

        return {
            'accountId': self.account_id,
            'comment': f"alpaca_id={activity_id}",
            'currency': 'USD',
            'dataSource': 'YAHOO',
            'date': date,
            'fee': 0,
            'quantity': abs(qty),
            'symbol': symbol,
            'type': 'DIVIDEND',
            'unitPrice': per_share,
            '_alpaca_id': activity_id
        }

    def _transform_interest_activity(self, activity: Dict) -> Optional[Dict]:
        """Transform an interest activity"""
        net_amount = float(activity.get('net_amount', 0))
        date_str = activity.get('date', '')
        date = self._parse_date(date_str)
        activity_id = activity.get('id', '')

        # Interest is recorded as a special activity
        # We'll use a cash symbol or skip if Ghostfolio doesn't support it
        return {
            'accountId': self.account_id,
            'comment': f"alpaca_id={activity_id} - Interest",
            'currency': 'USD',
            'dataSource': 'MANUAL',
            'date': date,
            'fee': 0,
            'quantity': 1,
            'symbol': 'USD',  # Cash symbol
            'type': 'INTEREST',
            'unitPrice': abs(net_amount),
            '_alpaca_id': activity_id
        }

    def _transform_fee_activity(self, activity: Dict) -> Optional[Dict]:
        """Transform a fee activity"""
        net_amount = float(activity.get('net_amount', 0))
        date_str = activity.get('date', '')
        date = self._parse_date(date_str)
        activity_id = activity.get('id', '')

        return {
            'accountId': self.account_id,
            'comment': f"alpaca_id={activity_id} - Fee",
            'currency': 'USD',
            'dataSource': 'MANUAL',
            'date': date,
            'fee': abs(net_amount),
            'quantity': 0,
            'symbol': 'USD',
            'type': 'FEE',
            'unitPrice': 0,
            '_alpaca_id': activity_id
        }

    def _map_symbol(self, symbol: str) -> str:
        """
        Map Alpaca symbol to Ghostfolio symbol using mapping configuration

        Args:
            symbol: Alpaca symbol

        Returns:
            Mapped symbol or original if no mapping exists
        """
        if symbol in self.symbol_mapping:
            mapped = self.symbol_mapping[symbol]
            logger.debug(f"Mapped symbol: {symbol} -> {mapped}")
            return mapped

        # Clean up symbol (remove spaces, special chars for crypto pairs)
        cleaned = symbol.replace('/', '').replace(' ', '-')
        return cleaned

    def _parse_date(self, date_str: str) -> str:
        """
        Parse date string to ISO format

        Args:
            date_str: Date string from Alpaca

        Returns:
            ISO formatted date string
        """
        try:
            # Alpaca uses RFC3339 format
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.isoformat()
        except Exception as e:
            logger.error(f"Error parsing date '{date_str}': {e}")
            return datetime.now().isoformat()

    def _deduplicate_activities(
        self,
        new_activities: List[Dict],
        existing_activities: List[Dict]
    ) -> List[Dict]:
        """
        Find activities that don't already exist in Ghostfolio

        Args:
            new_activities: Activities to import
            existing_activities: Existing activities in Ghostfolio

        Returns:
            List of new activities to import
        """
        # Build set of existing Alpaca activity IDs
        existing_ids = set()

        for activity in existing_activities:
            comment = activity.get('comment', '')
            if comment:
                # Extract alpaca_id from comment
                match = re.search(r'alpaca_id=([^\s]+)', comment)
                if match:
                    existing_ids.add(match.group(1))

        # Filter out activities that already exist
        unique_activities = []
        for activity in new_activities:
            alpaca_id = activity.get('_alpaca_id', '')

            if alpaca_id and alpaca_id not in existing_ids:
                # Remove internal fields before importing
                clean_activity = {k: v for k, v in activity.items() if not k.startswith('_')}
                unique_activities.append(clean_activity)
            else:
                logger.debug(f"Skipping duplicate activity: {alpaca_id}")

        logger.info(f"Found {len(unique_activities)} new activities to import")
        return unique_activities

    def _import_activities(self, activities: List[Dict]):
        """
        Import activities to Ghostfolio in chunks

        Args:
            activities: List of activities to import
        """
        # Sort by date for chronological import
        sorted_activities = sorted(activities, key=lambda x: x['date'])

        # Import in chunks of 10 (following IB sync pattern)
        chunk_size = 10
        for i in range(0, len(sorted_activities), chunk_size):
            chunk = sorted_activities[i:i + chunk_size]

            logger.info(f"Importing chunk {i // chunk_size + 1} ({len(chunk)} activities)")
            logger.debug(f"Activities:\n{json.dumps(chunk, indent=2)}")

            try:
                result = self.ghostfolio.import_activities(chunk, dry_run=False)
                logger.info(f"Import result: {result}")
            except Exception as e:
                logger.error(f"Failed to import chunk: {e}")
                # Continue with next chunk

    def _update_account_balance(self):
        """Update account balance from Alpaca"""
        try:
            account_info = self.alpaca.get_account()

            # Get cash balance
            cash = float(account_info.get('cash', 0))
            equity = float(account_info.get('equity', 0))

            logger.info(f"Account cash: ${cash:.2f}, equity: ${equity:.2f}")

            # Update Ghostfolio account with cash balance
            self.ghostfolio.update_account_balance(
                account_id=self.account_id,
                balance=cash,
                currency=self.ghost_currency,
                name=self.ghost_account_name
            )

        except Exception as e:
            logger.error(f"Failed to update account balance: {e}")

    def get_all_activities(self):
        """Get and display all Ghostfolio activities for this account"""
        logger.info(f"Fetching all activities for account: {self.ghost_account_name}")

        if not self.account_id:
            account = self.ghostfolio.get_account_by_name(self.ghost_account_name)
            if not account:
                logger.error(f"Account '{self.ghost_account_name}' not found")
                return
            self.account_id = account['id']

        activities = self.ghostfolio.get_activities(accounts=[self.account_id])

        logger.info(f"\nFound {len(activities)} activities:")
        for activity in activities:
            logger.info(json.dumps(activity, indent=2))

    def delete_all_activities(self):
        """Delete all activities for this account"""
        logger.info(f"Deleting all activities for account: {self.ghost_account_name}")

        if not self.account_id:
            account = self.ghostfolio.get_account_by_name(self.ghost_account_name)
            if not account:
                logger.error(f"Account '{self.ghost_account_name}' not found")
                return
            self.account_id = account['id']

        self.ghostfolio.delete_all_activities(self.account_id)
        logger.info("All activities deleted")


def load_symbol_mapping(mapping_file: str = 'mapping.yaml') -> Dict[str, str]:
    """
    Load symbol mapping from YAML file

    Args:
        mapping_file: Path to mapping YAML file

    Returns:
        Dict of symbol mappings
    """
    try:
        with open(mapping_file, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('symbol_mapping', {})
    except FileNotFoundError:
        logger.warning(f"Mapping file '{mapping_file}' not found, using empty mapping")
        return {}
    except Exception as e:
        logger.error(f"Error loading mapping file: {e}")
        return {}
