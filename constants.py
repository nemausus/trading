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

# Schwab's API reports times in Mountain Standard Time (UTC-7:00).
SCHWAB_TZ: datetime.timezone = datetime.timezone(
    -datetime.timedelta(hours=7)
)


accounts: dict[str, Account] = {}

class Account:
    def __init__(self, name: str) -> None:
        self.name = name
        info = os.environ.get(name, '').split(',')
        assert len(info) == 2
        self.number = info[0]
        self.hash = info[1]


def init_accounts() -> None:
    """Initialize accounts from environment variables once at startup."""
    global accounts
    if accounts:
        return
    ind = Account('IND_ACCOUNT')
    ira = Account('IRA_ACCOUNT')
    accounts = {ind.name: ind, ira.name: ira}


def get_account_hash(account_number: str) -> str:
    for account in accounts.values():
        if account.number == account_number:
            return account.hash
    raise ValueError("Invalid account number")


def get_account_number_for_hash(account_hash: str) -> str:
    for account in accounts.values():
        if account.hash == account_hash:
            return account.number
    raise ValueError("Invalid account Hash")


def get_all_account_hashes() -> list[str]:
    return [acc.hash for acc in accounts.values()]


def get_all_account_numbers() -> list[str]:
    return [acc.number for acc in accounts.values()]


def resolve_account_hash(account_param: str | None) -> list[str]:
    if not account_param or account_param.strip().upper() == 'ALL':
        return get_all_account_hashes()
    val = account_param.strip()
    if val in accounts:
        return [accounts[val].hash]
    return [get_account_hash(val)]


def resolve_account_number(account_param: str | None) -> list[str]:
    if not account_param or account_param.strip().upper() == 'ALL':
        return get_all_account_numbers()
    return [account_param.strip()]