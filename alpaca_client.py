"""
Alpaca API Client
Handles communication with the Alpaca Trading API
"""

import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Client for interacting with Alpaca Trading API"""

    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        """
        Initialize Alpaca client

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            base_url: Base URL for Alpaca API (paper or live trading)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.secret_key,
            'Content-Type': 'application/json'
        }

    def get_account(self) -> Dict:
        """
        Get account information including balance and equity

        Returns:
            Dict with account information
        """
        url = f"{self.base_url}/v2/account"
        logger.info(f"Fetching account info from {url}")

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            account = response.json()
            logger.info(f"Account fetched successfully: {account.get('account_number', 'N/A')}")
            return account
        else:
            logger.error(f"Failed to fetch account: {response.status_code} - {response.text}")
            response.raise_for_status()

    def get_activities(
        self,
        activity_types: Optional[List[str]] = None,
        date: Optional[str] = None,
        after: Optional[str] = None,
        until: Optional[str] = None,
        direction: str = 'desc',
        page_size: int = 100
    ) -> List[Dict]:
        """
        Get account activities with optional filtering

        Args:
            activity_types: List of activity types to filter (e.g., ['FILL', 'DIV'])
            date: Specific date to query (YYYY-MM-DD)
            after: Get activities after this date (YYYY-MM-DD)
            until: Get activities until this date (YYYY-MM-DD)
            direction: Sort direction ('asc' or 'desc')
            page_size: Maximum number of results per page

        Returns:
            List of activity dictionaries
        """
        url = f"{self.base_url}/v2/account/activities"

        # Build query parameters
        params = {
            'direction': direction,
            'page_size': page_size
        }

        if date:
            params['date'] = date
        if after:
            params['after'] = after
        if until:
            params['until'] = until

        all_activities = []
        page_token = None

        # If specific activity types requested, query each type separately
        # (Alpaca API requires separate calls per activity type)
        if activity_types:
            for activity_type in activity_types:
                logger.info(f"Fetching {activity_type} activities...")
                activities = self._fetch_activity_type(
                    activity_type,
                    params.copy()
                )
                all_activities.extend(activities)
        else:
            # Fetch all activity types
            logger.info("Fetching all activities...")
            activities = self._fetch_all_activities(params.copy())
            all_activities.extend(activities)

        logger.info(f"Total activities fetched: {len(all_activities)}")
        return all_activities

    def _fetch_activity_type(self, activity_type: str, params: Dict) -> List[Dict]:
        """
        Fetch activities for a specific activity type with pagination

        Args:
            activity_type: The activity type to fetch
            params: Query parameters

        Returns:
            List of activities
        """
        url = f"{self.base_url}/v2/account/activities/{activity_type}"
        activities = []
        page_token = None

        while True:
            if page_token:
                params['page_token'] = page_token

            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                page_activities = response.json()

                if not page_activities:
                    break

                activities.extend(page_activities)

                # Check if there are more pages
                if len(page_activities) < params.get('page_size', 100):
                    break

                # Get the last activity ID for pagination
                if page_activities:
                    page_token = page_activities[-1].get('id')
                else:
                    break
            else:
                logger.error(f"Failed to fetch {activity_type} activities: {response.status_code} - {response.text}")
                break

        return activities

    def _fetch_all_activities(self, params: Dict) -> List[Dict]:
        """
        Fetch all activities (when no specific type is requested)

        Args:
            params: Query parameters

        Returns:
            List of activities
        """
        url = f"{self.base_url}/v2/account/activities"
        activities = []
        page_token = None

        while True:
            if page_token:
                params['page_token'] = page_token

            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                page_activities = response.json()

                if not page_activities:
                    break

                activities.extend(page_activities)

                # Check if there are more pages
                if len(page_activities) < params.get('page_size', 100):
                    break

                # Get the last activity ID for pagination
                if page_activities:
                    page_token = page_activities[-1].get('id')
                else:
                    break
            else:
                logger.error(f"Failed to fetch activities: {response.status_code} - {response.text}")
                break

        return activities

    def get_orders(
        self,
        status: str = 'closed',
        limit: int = 500,
        after: Optional[str] = None,
        until: Optional[str] = None
    ) -> List[Dict]:
        """
        Get orders from Alpaca

        Args:
            status: Order status ('open', 'closed', 'all')
            limit: Maximum number of orders to return
            after: Get orders after this date
            until: Get orders until this date

        Returns:
            List of order dictionaries
        """
        url = f"{self.base_url}/v2/orders"

        params = {
            'status': status,
            'limit': limit,
            'direction': 'desc'
        }

        if after:
            params['after'] = after
        if until:
            params['until'] = until

        logger.info(f"Fetching orders with status={status}...")

        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            orders = response.json()
            logger.info(f"Fetched {len(orders)} orders")
            return orders
        else:
            logger.error(f"Failed to fetch orders: {response.status_code} - {response.text}")
            return []
