"""
Main Alpaca to Ghostfolio Sync Logic
Coordinates data fetching, transformation, and import
"""

import logging
import json
import re
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from alpaca_client import AlpacaClient
from ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)


class SyncAlpaca:
    """Main class for syncing Alpaca activities to Ghostfolio"""

    # Alpaca crypto trading fee tiers (as of 2024)
    # Based on 30-day crypto trading volume
    # Source: https://docs.alpaca.markets/docs/crypto-fees
    CRYPTO_FEE_TIERS = [
        {'min': 0,          'max': 100_000,    'maker': 0.0015, 'taker': 0.0025},  # Tier 1
        {'min': 100_000,    'max': 500_000,    'maker': 0.0012, 'taker': 0.0022},  # Tier 2
        {'min': 500_000,    'max': 1_000_000,  'maker': 0.0010, 'taker': 0.0020},  # Tier 3
        {'min': 1_000_000,  'max': 10_000_000, 'maker': 0.0008, 'taker': 0.0018},  # Tier 4
        {'min': 10_000_000, 'max': 25_000_000, 'maker': 0.0005, 'taker': 0.0015},  # Tier 5
        {'min': 25_000_000, 'max': 50_000_000, 'maker': 0.0002, 'taker': 0.0012},  # Tier 6
        {'min': 50_000_000, 'max': 100_000_000,'maker': 0.0000, 'taker': 0.0010},  # Tier 7
        {'min': 100_000_000,'max': float('inf'),'maker': 0.0000, 'taker': 0.0008},  # Tier 8
    ]

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

        # Cache for crypto trading volume and order details
        self._crypto_volume_30d = None
        self._crypto_fee_tier = None
        self._order_details_cache = {}  # order_id -> order details

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

    def _calculate_crypto_volume_30d(self) -> float:
        """
        Calculate 30-day crypto trading volume for fee tier determination

        Returns:
            Total USD volume of crypto trades in the last 30 days
        """
        if self._crypto_volume_30d is not None:
            return self._crypto_volume_30d

        logger.info("Calculating 30-day crypto trading volume for fee tier determination")

        # Fetch last 30 days of activities
        after_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        activities = self.alpaca.get_activities(
            activity_types=['FILL'],
            after=after_date
        )

        total_volume = 0.0

        for activity in activities:
            symbol = activity.get('symbol', '')
            # Check if it's a crypto trade
            is_crypto = '/' in symbol or (symbol.endswith('USD') and len(symbol) > 3)

            if is_crypto:
                qty = abs(float(activity.get('qty', 0)))
                price = abs(float(activity.get('price', 0)))
                total_volume += qty * price

        self._crypto_volume_30d = total_volume
        logger.info(f"30-day crypto trading volume: ${total_volume:,.2f}")

        return total_volume

    def _get_fee_tier(self) -> Dict:
        """
        Determine the fee tier based on 30-day crypto trading volume

        Returns:
            Fee tier dictionary with maker and taker rates
        """
        if self._crypto_fee_tier is not None:
            return self._crypto_fee_tier

        volume = self._calculate_crypto_volume_30d()

        for tier in self.CRYPTO_FEE_TIERS:
            if tier['min'] <= volume < tier['max']:
                self._crypto_fee_tier = tier
                tier_num = self.CRYPTO_FEE_TIERS.index(tier) + 1
                logger.info(f"Fee Tier {tier_num}: ${tier['min']:,} - ${tier['max']:,}")
                logger.info(f"  Maker: {tier['maker'] * 100}%, Taker: {tier['taker'] * 100}%")
                return tier

        # Should never reach here, but default to Tier 1
        self._crypto_fee_tier = self.CRYPTO_FEE_TIERS[0]
        return self._crypto_fee_tier

    def _get_order_details(self, order_id: str) -> Optional[Dict]:
        """
        Fetch order details from Alpaca API

        Args:
            order_id: The Alpaca order ID

        Returns:
            Order details dictionary or None if not found
        """
        if order_id in self._order_details_cache:
            return self._order_details_cache[order_id]

        try:
            order = self.alpaca.get_order(order_id)
            self._order_details_cache[order_id] = order
            return order
        except Exception as e:
            logger.warning(f"Failed to fetch order details for {order_id}: {e}")
            return None

    def _is_taker_order(self, order_id: str) -> bool:
        """
        Determine if an order is a taker order (pays taker fee)

        Market orders are always taker orders.
        Limit orders are taker if they execute immediately, maker if they add liquidity.
        Since the activities API doesn't indicate maker/taker status directly,
        we check the order type from the orders API.

        Args:
            order_id: The Alpaca order ID

        Returns:
            True if taker order, False if maker order (defaults to True)
        """
        order = self._get_order_details(order_id)

        if not order:
            # Default to taker (more common and conservative)
            logger.debug(f"Order details not found for {order_id}, defaulting to taker")
            return True

        order_type = order.get('type', 'market')

        # Market orders are always taker orders
        if order_type == 'market':
            return True

        # For limit orders, check if it was filled immediately (taker) or added liquidity (maker)
        # The filled_at time vs submitted_at can indicate this
        # If they're very close (< 1 second), likely a taker order
        submitted_at = order.get('submitted_at', '')
        filled_at = order.get('filled_at', '')

        if submitted_at and filled_at:
            try:
                submitted_dt = datetime.fromisoformat(submitted_at.replace('Z', '+00:00'))
                filled_dt = datetime.fromisoformat(filled_at.replace('Z', '+00:00'))
                time_diff = (filled_dt - submitted_dt).total_seconds()

                # If filled within 1 second, likely a taker (took existing liquidity)
                # Otherwise likely a maker (added liquidity and waited)
                is_taker = time_diff < 1.0
                logger.debug(f"Order {order_id}: type={order_type}, fill_time={time_diff}s, is_taker={is_taker}")
                return is_taker
            except Exception as e:
                logger.warning(f"Error parsing order times: {e}")

        # Default to taker for limit orders if we can't determine
        return True

    def _calculate_crypto_fee(self, order_id: str, is_buy: bool) -> float:
        """
        Calculate the appropriate crypto trading fee based on tier and order type

        Args:
            order_id: The Alpaca order ID
            is_buy: True for buy orders, False for sell orders

        Returns:
            Fee rate to apply (e.g., 0.0025 for 0.25%)
        """
        # Only apply fees to buy orders (quantity received is reduced by fee)
        if not is_buy:
            return 0.0

        tier = self._get_fee_tier()
        is_taker = self._is_taker_order(order_id)

        fee_rate = tier['taker'] if is_taker else tier['maker']
        fee_type = 'taker' if is_taker else 'maker'

        logger.debug(f"Order {order_id}: {fee_type} fee = {fee_rate * 100}%")

        return fee_rate

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

        original_symbol = activity.get('symbol', '')
        symbol = self._map_symbol(original_symbol)
        quantity = abs(float(activity.get('qty', 0)))
        price = abs(float(activity.get('price', 0)))

        # Apply Alpaca crypto trading fees to match actual positions
        # Fees are based on 30-day volume tier and whether order is maker/taker
        is_crypto = '/' in original_symbol or (original_symbol.endswith('USD') and len(original_symbol) > 3)

        if is_crypto and side == 'BUY':
            # Get the order ID to determine maker/taker status and apply correct fee
            order_id = activity.get('order_id', '')
            fee_rate = self._calculate_crypto_fee(order_id, is_buy=True)

            if fee_rate > 0:
                original_qty = quantity
                quantity = quantity * (1 - fee_rate)
                logger.debug(
                    f"Applied {fee_rate * 100:.2f}% crypto fee to {original_symbol}: "
                    f"{original_qty:.8f} -> {quantity:.8f}"
                )

        # Parse date
        transaction_time = activity.get('transaction_time', '')
        date = self._parse_date(transaction_time)

        # Alpaca activity ID for deduplication
        activity_id = activity.get('id', '')

        # Use YAHOO for all assets
        # Note: Yahoo Finance crypto prices may differ from Alpaca by ~0.5-1%
        # PEPEUSD in particular can have larger variance (20%+)
        data_source = 'YAHOO'

        return {
            'accountId': self.account_id,
            'comment': f"alpaca_id={activity_id}",  # For deduplication
            'currency': 'USD',  # Alpaca is US-based
            'dataSource': data_source,
            'date': date,
            'fee': 0,  # Fee already applied to quantity for crypto
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
