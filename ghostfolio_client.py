"""
Ghostfolio API Client
Handles communication with the Ghostfolio API
"""

import requests
import logging
import json
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GhostfolioClient:
    """Client for interacting with Ghostfolio API"""

    def __init__(self, host: str, token: Optional[str] = None, key: Optional[str] = None):
        """
        Initialize Ghostfolio client

        Args:
            host: Ghostfolio instance URL
            token: Bearer token (preferred)
            key: User key (alternative to token)
        """
        self.host = host.rstrip('/')
        self.token = token

        # If no token provided, try to get one using the key
        if not self.token and key:
            self.token = self._create_token(key)

        if not self.token:
            raise ValueError("Either token or key must be provided for Ghostfolio authentication")

        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def _create_token(self, key: str) -> str:
        """
        Exchange user key for bearer token

        Args:
            key: User API key

        Returns:
            Bearer token
        """
        logger.info("No bearer token provided, fetching one using key")
        url = f"{self.host}/api/v1/auth/anonymous"

        payload = json.dumps({'accessToken': key})
        headers = {'Content-Type': 'application/json'}

        response = requests.post(url, headers=headers, data=payload)

        if response.status_code == 201:
            token = response.json().get('authToken', '')
            logger.info("Successfully obtained bearer token")
            return token
        else:
            logger.error(f"Failed to create token: {response.status_code} - {response.text}")
            raise Exception(f"Failed to authenticate with Ghostfolio: {response.text}")

    def get_all_accounts(self) -> List[Dict]:
        """
        Get all accounts from Ghostfolio

        Returns:
            List of account dictionaries
        """
        url = f"{self.host}/api/v1/account"
        logger.info("Fetching all accounts from Ghostfolio")

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            accounts = response.json().get('accounts', [])
            logger.info(f"Fetched {len(accounts)} accounts")
            return accounts
        else:
            logger.error(f"Failed to fetch accounts: {response.status_code} - {response.text}")
            return []

    def get_account_by_name(self, name: str) -> Optional[Dict]:
        """
        Find account by name

        Args:
            name: Account name to search for

        Returns:
            Account dict if found, None otherwise
        """
        accounts = self.get_all_accounts()
        for account in accounts:
            if account.get('name') == name:
                logger.info(f"Found account '{name}' with ID: {account.get('id')}")
                return account
        logger.info(f"Account '{name}' not found")
        return None

    def create_account(
        self,
        name: str,
        currency: str,
        balance: float = 0.0,
        platform_id: Optional[str] = None
    ) -> str:
        """
        Create a new account in Ghostfolio

        Args:
            name: Account name
            currency: Account currency (e.g., USD)
            balance: Initial balance
            platform_id: Optional platform ID

        Returns:
            Account ID
        """
        url = f"{self.host}/api/v1/account"
        logger.info(f"Creating account '{name}' with currency {currency}")

        payload = {
            'name': name,
            'currency': currency,
            'balance': balance,
            'isExcluded': False,
            'platformId': platform_id if platform_id else None
        }

        response = requests.post(
            url,
            headers=self.headers,
            data=json.dumps(payload)
        )

        if response.status_code == 201:
            account = response.json()
            account_id = account.get('id')
            logger.info(f"Account created successfully with ID: {account_id}")
            return account_id
        else:
            logger.error(f"Failed to create account: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create account: {response.text}")

    def update_account_balance(
        self,
        account_id: str,
        balance: float,
        currency: str,
        name: str,
        platform_id: Optional[str] = None
    ) -> bool:
        """
        Update account balance

        Args:
            account_id: Account ID
            balance: New balance
            currency: Account currency
            name: Account name
            platform_id: Optional platform ID

        Returns:
            True if successful
        """
        url = f"{self.host}/api/v1/account/{account_id}"
        logger.info(f"Updating balance for account {account_id} to {balance} {currency}")

        payload = {
            'id': account_id,
            'balance': balance,
            'currency': currency,
            'name': name,
            'isExcluded': False,
            'platformId': platform_id if platform_id else None
        }

        response = requests.put(
            url,
            headers=self.headers,
            data=json.dumps(payload)
        )

        if response.status_code == 200:
            logger.info("Account balance updated successfully")
            return True
        else:
            logger.error(f"Failed to update account balance: {response.status_code} - {response.text}")
            return False

    def get_activities(
        self,
        accounts: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Get activities/orders from Ghostfolio

        Args:
            accounts: List of account IDs to filter
            start_date: Start date for filtering (ISO format)
            end_date: End date for filtering (ISO format)

        Returns:
            List of activity dictionaries
        """
        url = f"{self.host}/api/v1/order"
        logger.info("Fetching activities from Ghostfolio")

        params = {}
        if accounts:
            params['accounts'] = ','.join(accounts)

        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code == 200:
            result = response.json()
            activities = result.get('activities', [])
            logger.info(f"Fetched {len(activities)} activities")
            return activities
        else:
            logger.error(f"Failed to fetch activities: {response.status_code} - {response.text}")
            return []

    def import_activities(self, activities: List[Dict], dry_run: bool = False) -> Dict:
        """
        Import activities to Ghostfolio in bulk

        Args:
            activities: List of activity dictionaries
            dry_run: If True, validate without importing

        Returns:
            Response from API
        """
        url = f"{self.host}/api/v1/import"

        if dry_run:
            url += "?dryRun=true"

        logger.info(f"Importing {len(activities)} activities (dry_run={dry_run})")

        payload = json.dumps({'activities': activities})

        response = requests.post(url, headers=self.headers, data=payload)

        if response.status_code == 201:
            result = response.json()
            logger.info(f"Import successful: {json.dumps(result, indent=2)}")
            return result
        else:
            logger.error(f"Failed to import activities: {response.status_code} - {response.text}")
            raise Exception(f"Failed to import activities: {response.text}")

    def delete_activity(self, activity_id: str) -> bool:
        """
        Delete a single activity

        Args:
            activity_id: Activity ID to delete

        Returns:
            True if successful
        """
        url = f"{self.host}/api/v1/order/{activity_id}"
        logger.info(f"Deleting activity {activity_id}")

        response = requests.delete(url, headers=self.headers)

        if response.status_code == 200:
            logger.info(f"Activity {activity_id} deleted successfully")
            return True
        else:
            logger.error(f"Failed to delete activity: {response.status_code} - {response.text}")
            return False

    def delete_all_activities(self, account_id: str) -> bool:
        """
        Delete all activities for an account

        Args:
            account_id: Account ID

        Returns:
            True if successful
        """
        url = f"{self.host}/api/v1/order"
        logger.info(f"Deleting all activities for account {account_id}")

        params = {'accounts': account_id}

        response = requests.delete(url, headers=self.headers, params=params)

        if response.status_code == 200:
            logger.info("All activities deleted successfully")
            return True
        else:
            logger.error(f"Failed to delete activities: {response.status_code} - {response.text}")
            return False

    def get_all_platforms(self) -> List[Dict]:
        """
        Get all platforms from Ghostfolio

        Returns:
            List of platform dictionaries
        """
        url = f"{self.host}/api/v1/platform"
        logger.info("Fetching all platforms from Ghostfolio")

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            result = response.json()
            # API returns list directly, not wrapped in an object
            platforms = result if isinstance(result, list) else result.get('platforms', [])
            logger.info(f"Fetched {len(platforms)} platforms")
            return platforms
        else:
            logger.error(f"Failed to fetch platforms: {response.status_code} - {response.text}")
            return []

    def get_platform_by_name(self, name: str) -> Optional[Dict]:
        """
        Find platform by name

        Args:
            name: Platform name to search for

        Returns:
            Platform dict if found, None otherwise
        """
        platforms = self.get_all_platforms()
        for platform in platforms:
            if platform.get('name') == name:
                logger.info(f"Found platform '{name}' with ID: {platform.get('id')}")
                return platform
        logger.info(f"Platform '{name}' not found")
        return None

    def create_platform(self, name: str, url: Optional[str] = None) -> str:
        """
        Create a new platform in Ghostfolio

        Args:
            name: Platform name
            url: Platform URL (optional)

        Returns:
            Platform ID
        """
        api_url = f"{self.host}/api/v1/platform"
        logger.info(f"Creating platform '{name}' with URL {url}")

        payload = {
            'name': name,
            'url': url if url else None
        }

        response = requests.post(
            api_url,
            headers=self.headers,
            data=json.dumps(payload)
        )

        if response.status_code == 201:
            platform = response.json()
            platform_id = platform.get('id')
            logger.info(f"Platform created successfully with ID: {platform_id}")
            return platform_id
        else:
            logger.error(f"Failed to create platform: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create platform: {response.text}")
