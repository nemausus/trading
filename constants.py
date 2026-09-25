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

class Account:
    def __init__(self, name, env_var: str) -> None:
        self.name = name
        self.env_var = env_var
        info = os.environ.get(env_var, '').split(',')
        assert len(info) == 2
        self.number = info[0]
        self.hash = info[1]


ind_account = Account('ind', 'IND_ACCOUNT')
ira_account = Account('ira', 'IRA_ACCOUNT')
accounts = {ind_account.name: ind_account, ira_account.name: ira_account}


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