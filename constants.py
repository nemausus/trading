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
SCHWAB_TZ: datetime.timezone = datetime.timezone(-datetime.timedelta(hours=7))


class Account:
    def __init__(self, name: str) -> None:
        self.name = name
        info = os.environ.get(name, "").split(",")
        assert len(info) == 2
        self.number = info[0]
        self.hash = info[1]


accounts: dict[str, Account] = {}


def init_accounts() -> None:
    """Initialize accounts from environment variables once at startup."""
    global accounts
    if accounts:
        return
    ind = Account("IND_ACCOUNT")
    ira = Account("IRA_ACCOUNT")
    accounts = {ind.name: ind, ira.name: ira}


def _resolve_accounts(account_id: str) -> list[Account]:
    if not account_id:
        raise ValueError("Empty account input")
    account_id = account_id.strip().upper()
    if account_id == "ALL":
        return list(accounts.values())
    if account_id in accounts:
        return [accounts[account_id]]
    for account in accounts.values():
        if account_id == account.number:
            return [account]
    raise ValueError(f"Invalid account input: {account_id}")


def get_account_hash_for_number(account_number: str) -> str:
    account = _resolve_accounts(account_number)
    assert len(account) == 1
    return account[0].hash


def get_all_account_hashes() -> list[str]:
    return [acc.hash for acc in accounts.values()]


def get_all_account_numbers() -> list[str]:
    return [acc.number for acc in accounts.values()]


def resolve_account_numbers(account_param: str) -> list[str]:
    return [acc.number for acc in _resolve_accounts(account_param)]
