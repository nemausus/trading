"""
schwab_transactions.py
~~~~~~~~~~~~~~~~~~~~~~
Incremental transaction sync from the Schwab Trader API to Firestore.

Flow:
    1. Resolve the primary (ind) account hash via /accounts/accountNumbers.
    2. Look up the most recent stored transaction time in Firestore;
       fall back to DEFAULT_FROM_DATE if none exist yet.
    3. Fetch raw transactions from Schwab for that date range.
    4. Deduplicate against activityIds already in Firestore.
    5. Persist new records under:
         users/{uid}/accounts/{accountHash}/transactions/{activityId}
"""

import datetime
import logging
import requests

import firestore_db
from constants import SCHWAB_TZ, get_account_number_for_hash
from schwab_api import schwab_request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADER_API_BASE_URL = "https://api.schwabapi.com/trader/v1"

# Earliest date to backfill from when no stored transactions exist.
DEFAULT_FROM_DATE = "2026-01-01T00:00:00-07:30"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _today_iso() -> str:
    """Return today's date as a Schwab-compatible ISO datetime string (MST)."""
    return datetime.datetime.now(SCHWAB_TZ).replace(microsecond=0).isoformat()


def _normalize_to_seconds(iso_str: str) -> str:
    """Strip fractional seconds from ISO string to match Schwab format."""
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.replace(microsecond=0).isoformat()
    except (ValueError, TypeError) as err:
        logger.warning("Failed to normalize ISO datetime string %r: %s", iso_str, err)
        return DEFAULT_FROM_DATE


# ---------------------------------------------------------------------------
# Core Service Functions
# ---------------------------------------------------------------------------

def fetch_transactions_raw(
    access_token: str,
    account_hash: str,
    from_date: str,
    to_date: str,
) -> list[dict]:
    """
    Fetch raw transaction records from the Schwab Trader API for a given account.

    Args:
        access_token: Valid Schwab Bearer access token.
        account_hash:  Encrypted Schwab account hash.
        from_date:     ISO string (e.g. '2026-01-01T00:00:00-07:30').
        to_date:       ISO string (e.g. '2026-06-01T23:59:59-07:30').

    Returns:
        List of raw transaction dicts from Schwab, or [] on error.
    """
    url = f"{TRADER_API_BASE_URL}/accounts/{account_hash}/transactions"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    params = {"startDate": from_date, "endDate": to_date}

    try:
        data = schwab_request("GET", url, headers=headers, params=params)
        if not isinstance(data, list):
            logger.error("Unexpected response shape from transactions API: %s", type(data))
            return []
        return data
    except Exception as exc:
        logger.error("Failed to fetch transactions for account %s: %s", account_hash, exc)
        return []


def sync_transactions(uid: str, access_token: str, account_hash: str) -> dict:
    """
    Orchestrate an incremental sync of Schwab transactions for the given user and account.

    Steps:
        1. Determine fromDate from the latest stored transaction time
           (falls back to DEFAULT_FROM_DATE if none stored yet).
        2. Fetch raw transactions from Schwab.
        3. Deduplicate against activityIds already stored in Firestore.
        4. Persist new records to Firestore.

    Args:
        uid:          Firebase user ID.
        access_token: Valid Schwab Bearer access token.
        account_hash: Target Schwab account hash.

    Returns:
        Dict with keys:
            new_count    (int)  -- number of new transactions written
            from_date    (str)  -- startDate used for this sync
            to_date      (str)  -- endDate used for this sync
            account_hash (str)  -- resolved account hash
    """
    # -- Step 1: determine fromDate ------------------------------------------
    latest_time = firestore_db.get_latest_transaction_time(uid, account_hash)
    from_date = _normalize_to_seconds(latest_time) if latest_time else DEFAULT_FROM_DATE
    to_date = _today_iso()
    logger.info(
        "Syncing transactions for uid=%s account=%s from=%s to=%s",
        uid, account_hash[:10], from_date, to_date,
    )

    # -- Step 2: fetch from Schwab -------------------------------------------
    account_number = get_account_number_for_hash(account_hash)
    raw_txns = fetch_transactions_raw(access_token, account_hash, from_date, to_date)
    if not raw_txns:
        return {
            "new_count": 0,
            "from_date": from_date,
            "to_date": to_date,
            "account_number": account_number,
        }

    # -- Step 3: deduplicate -------------------------------------------------
    incoming_ids = [str(txn["activityId"]) for txn in raw_txns if "activityId" in txn]
    existing_ids = firestore_db.get_existing_activity_ids(
        uid, account_hash, incoming_ids
    )

    new_txns = [
        txn for txn in raw_txns
        if "activityId" in txn and str(txn["activityId"]) not in existing_ids
    ]

    logger.info(
        "Fetched %d txns, %d already stored, %d new to write.",
        len(raw_txns), len(existing_ids), len(new_txns),
    )

    # -- Step 4: persist to Firestore ----------------------------------------
    if new_txns:
        firestore_db.save_transactions(uid, account_hash, new_txns)

    return {
        "new_count": len(new_txns),
        "from_date": from_date,
        "to_date": to_date,
        "account_number": account_number,
    }
