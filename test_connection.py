#!/usr/bin/env python3
"""
Test connection to Ghostfolio and Alpaca APIs
"""

import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

def test_ghostfolio():
    """Test Ghostfolio connection"""
    host = os.getenv('GHOST_HOST')
    token = os.getenv('GHOST_TOKEN')

    print(f"\n=== Testing Ghostfolio at {host} ===")
    print(f"Token length: {len(token) if token else 0} characters")

    # Test 1: Try bearer token directly
    print("\nTest 1: Using token as bearer token directly...")
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    response = requests.get(f"{host}/api/v1/account", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")

    # Test 2: Try without 'Bearer' prefix
    print("\nTest 2: Using token without Bearer prefix...")
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    response = requests.get(f"{host}/api/v1/account", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")

    # Test 3: Try with different header name
    print("\nTest 3: Using X-API-KEY header...")
    headers = {
        'X-API-KEY': token,
        'Content-Type': 'application/json'
    }

    response = requests.get(f"{host}/api/v1/account", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")

    # Test 4: Check Ghostfolio info endpoint
    print("\nTest 4: Testing public info endpoint...")
    response = requests.get(f"{host}/api/v1/info")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Response: {response.text[:200]}")

def test_alpaca():
    """Test Alpaca connection"""
    api_key = os.getenv('ALPACA_API_KEY')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    base_url = os.getenv('ALPACA_BASE_URL')

    print(f"\n=== Testing Alpaca at {base_url} ===")

    headers = {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': secret_key
    }

    # Test account endpoint
    print("\nTesting account endpoint...")
    response = requests.get(f"{base_url}/v2/account", headers=headers)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        account = response.json()
        print(f"Account number: {account.get('account_number')}")
        print(f"Cash: ${float(account.get('cash', 0)):.2f}")
        print(f"Equity: ${float(account.get('equity', 0)):.2f}")
    else:
        print(f"Error: {response.text[:200]}")

    # Test activities endpoint
    print("\nTesting activities endpoint...")
    response = requests.get(
        f"{base_url}/v2/account/activities",
        headers=headers,
        params={'page_size': 5}
    )
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        activities = response.json()
        print(f"Found {len(activities)} recent activities")
        if activities:
            print(f"Sample activity: {json.dumps(activities[0], indent=2)}")
    else:
        print(f"Error: {response.text[:200]}")

if __name__ == "__main__":
    test_ghostfolio()
    test_alpaca()
