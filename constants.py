"""
constants.py
~~~~~~~~~~~~
Shared constants for the Schwab API integration.

Centralising these prevents drift between modules that previously
defined their own copies.
"""

import datetime
import os

# (connect timeout, read timeout) in seconds for all outbound Schwab requests.
SCHWAB_REQUEST_TIMEOUT: tuple[int, int] = (5, 30)

# Schwab's API reports times in Mountain Standard Time (UTC-7:30).
SCHWAB_TZ: datetime.timezone = datetime.timezone(
    -datetime.timedelta(hours=7, minutes=30)
)

def _get_account_hash(env_var: str) -> str:
    """Returns the account hash from environment variables."""
    account_hash = os.environ.get(env_var)
    if not account_hash:
        raise EnvironmentError(f"{env_var} environment variable is not configured.")
    return account_hash


def get_primary_account_hash() -> str:
    """Return the primary account hash from environment variables.

    Raises:
        EnvironmentError: If the IND_ACCOUNT environment variable is not set.
    """
    return _get_account_hash('IND_ACCOUNT')


def get_secondary_account_hash() -> str:
    """Returns the secondary account hash from environment variables."""
    return _get_account_hash('IRA_ACCOUNT')


def get_account_hash(account_number: str) -> str:
    """Returns the account hash for a given account number."""
    if account_number.endswith('acc1'):
        return get_primary_account_hash()
    if account_number.endswith('acc2'):
        return get_secondary_account_hash()
    raise ValueError(f"Unknown account number: {account_number}")
