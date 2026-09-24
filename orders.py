"""
orders.py
~~~~~~~~~
Service module for preparing, building, validating, and submitting Charles
Schwab orders, conforming to the schemas in ~/schwab_client.
"""

import logging
import re
from typing import Any

from constants import (
    get_account_hash,
    get_primary_account_hash,
    get_secondary_account_hash,
    get_all_account_hashes,
)
import schwab_api


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

INSTRUCTION_MAP = {
    # Option instructions
    "BTO": "BUY_TO_OPEN",
    "BTC": "BUY_TO_CLOSE",
    "STO": "SELL_TO_OPEN",
    "STC": "SELL_TO_CLOSE",
    "BUY_TO_OPEN": "BUY_TO_OPEN",
    "BUY_TO_CLOSE": "BUY_TO_CLOSE",
    "SELL_TO_OPEN": "SELL_TO_OPEN",
    "SELL_TO_CLOSE": "SELL_TO_CLOSE",
    # Equity instructions
    "BUY": "BUY",
    "SELL": "SELL",
    "SELL_SHORT": "SELL_SHORT",
    "BUY_TO_COVER": "BUY_TO_COVER",
}

DURATION_MAP = {
    "GTC": "GOOD_TILL_CANCEL",
    "GOOD_TILL_CANCEL": "GOOD_TILL_CANCEL",
    "DAY": "DAY",
    "FILL_OR_KILL": "FILL_OR_KILL",
    "FOK": "FILL_OR_KILL",
    "IMMEDIATE_OR_CANCEL": "IMMEDIATE_OR_CANCEL",
    "IOC": "IMMEDIATE_OR_CANCEL",
}

ORDER_TYPE_MAP = {
    "LIMIT": "LIMIT",
    "MARKET": "MARKET",
    "STOP": "STOP",
    "STOP_LIMIT": "STOP_LIMIT",
    "NET_DEBIT": "NET_DEBIT",
    "NET_CREDIT": "NET_CREDIT",
}

SESSION_MAP = {
    "NORMAL": "NORMAL",
    "AM": "AM",
    "PM": "PM",
    "SEAMLESS": "SEAMLESS",
}

# OCC option symbol regex: 6-digit YYMMDD date, C or P, 8-digit strike
_OCC_REGEX = re.compile(r"\d{6}[CP]\d{8}$")


# ---------------------------------------------------------------------------
# Private formatting and validation helpers
# ---------------------------------------------------------------------------

def _is_occ_option_symbol(symbol: str) -> bool:
    """Return True if symbol matches the OCC option symbol pattern.

    OCC format: TICKER + YYMMDD + C/P + 8-digit strike price.
    Example: 'AAPL  260821C00205000'
    """
    if not symbol or len(symbol) < 15:
        return False
    return bool(_OCC_REGEX.search(symbol.replace(" ", "")))


def format_price(price: float | str | int) -> str:
    """Format price to string representation.

    Matches ~/schwab_client truncate_float conventions:
    - 4 decimal places if absolute value < 1.0 and non-zero
    - 2 decimal places otherwise

    NOTE: Uses int() truncation (toward zero), NOT rounding.
    This is intentional to match Schwab client conventions where
    prices are always truncated rather than rounded.
    """
    try:
        val = float(price)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid price value: {price}") from e

    if val < 0:
        raise ValueError(f"Price cannot be negative: {price}")

    if abs(val) < 1.0 and val != 0.0:
        return "{:.4f}".format(float(int(val * 10000)) / 10000.0)
    return "{:.2f}".format(float(int(val * 100)) / 100.0)


def _normalize_field(value: str, lookup_map: dict, field_name: str) -> str:
    """Normalize and validate a string value against a lookup map.

    Args:
        value:      Raw input value to normalize.
        lookup_map: Dict mapping accepted keys to canonical values.
        field_name: Human-readable field name for error messages.

    Returns:
        Canonical value from the lookup map.

    Raises:
        ValueError: If the value is not found in the lookup map.
    """
    key = str(value).strip().upper()
    if key not in lookup_map:
        raise ValueError(
            f"Unknown {field_name} '{value}'. Must be one of: {sorted(lookup_map.keys())}"
        )
    return lookup_map[key]


def _validate_quantity(quantity) -> float:
    """Validate and return numeric quantity (must be positive)."""
    try:
        qty = float(quantity)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid order quantity: {quantity}") from e
    if qty <= 0:
        raise ValueError(f"Order quantity must be positive, got {quantity}")
    return qty


def resolve_account_hash(account: str | None) -> str:
    """Resolve an account identifier (alias, suffix, or full hash) to a full Schwab account hash.

    Args:
        account: Account alias ('ind', 'ira', 'primary', 'secondary'), suffix ('acc2', 'acc1'),
                 or full 64-char account hash. Defaults to primary account hash if None.
    """
    if not account:
        return get_primary_account_hash()

    acc_str = str(account).strip()
    acc_lower = acc_str.lower()

    if acc_lower in ("ind", "primary", "individual"):
        return get_primary_account_hash()
    if acc_lower in ("ira", "secondary", "roth"):
        return get_secondary_account_hash()

    configured_hashes = get_all_account_hashes()
    if acc_str in configured_hashes:
        return acc_str

    return get_account_hash(acc_str)


# ---------------------------------------------------------------------------
# Order payload construction
# ---------------------------------------------------------------------------

def build_single_order(
    *,
    symbol: str,
    quantity: int | float,
    instruction: str,
    price: float | str | int | None = None,
    order_type: str = "LIMIT",
    duration: str = "GOOD_TILL_CANCEL",
    session: str = "NORMAL",
    asset_type: str | None = None,
) -> dict[str, Any]:
    """Build a single-leg order dictionary conforming to Charles Schwab's Trader API schema.

    Args:
        symbol:      Ticker or OCC option symbol (e.g. 'AAPL' or 'AAPL  260821C00205000').
        quantity:    Number of shares or option contracts (must be > 0).
        instruction: Order instruction (e.g. 'BTO', 'BTC', 'STO', 'STC', 'BUY', 'SELL').
        price:       Limit price (required if order_type is 'LIMIT', 'NET_DEBIT', 'NET_CREDIT').
        order_type:  'LIMIT', 'MARKET', etc. (default 'LIMIT').
        duration:    'GOOD_TILL_CANCEL', 'DAY', etc. (default 'GOOD_TILL_CANCEL').
        session:     'NORMAL', 'AM', 'PM', 'SEAMLESS' (default 'NORMAL').
        asset_type:  'OPTION' or 'EQUITY'. Auto-detected if None.

    Returns:
        Dict conforming to Schwab order schema.

    Raises:
        ValueError: If any parameter is invalid.
    """
    if not symbol or not str(symbol).strip():
        raise ValueError("Order requires a non-empty 'symbol'.")
    symbol_str = str(symbol).strip().upper()

    qty_num = _validate_quantity(quantity)
    canonical_instruction = _normalize_field(instruction, INSTRUCTION_MAP, "instruction")
    canonical_order_type = _normalize_field(order_type, ORDER_TYPE_MAP, "order_type")
    canonical_duration = _normalize_field(duration, DURATION_MAP, "duration")
    canonical_session = _normalize_field(session, SESSION_MAP, "session")

    # Detect asset type
    if not asset_type:
        asset_type = "OPTION" if _is_occ_option_symbol(symbol_str) else "EQUITY"
    canonical_asset_type = asset_type.strip().upper()
    if canonical_asset_type not in ("OPTION", "EQUITY"):
        raise ValueError(f"Unknown asset_type '{asset_type}'. Must be 'OPTION' or 'EQUITY'.")

    order: dict[str, Any] = {
        "session": canonical_session,
        "duration": canonical_duration,
        "orderType": canonical_order_type,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": canonical_instruction,
                "quantity": qty_num,
                "instrument": {
                    "assetType": canonical_asset_type,
                    "symbol": symbol_str,
                },
            }
        ],
    }

    if canonical_order_type in ("LIMIT", "NET_DEBIT", "NET_CREDIT", "STOP_LIMIT"):
        if price is None:
            raise ValueError(f"Price is required for order type '{canonical_order_type}'.")
        order["price"] = format_price(price)

    return order


def build_roll_order(
    *,
    close_symbol: str,
    open_symbol: str,
    quantity: int | float,
    close_instruction: str = "BUY_TO_CLOSE",
    open_instruction: str = "SELL_TO_OPEN",
    price: float | str | int | None = None,
    order_type: str = "NET_CREDIT",
    duration: str = "GOOD_TILL_CANCEL",
    session: str = "NORMAL",
) -> dict[str, Any]:
    """Build a two-leg roll order dictionary conforming to Charles Schwab's Trader API schema.

    Closes an existing option contract while simultaneously opening a new option contract.

    Args:
        close_symbol:      OCC option symbol of existing position to close (Leg 1).
        open_symbol:       OCC option symbol of new target position to open (Leg 2).
        quantity:          Number of option contracts (must be > 0).
        close_instruction: 'BUY_TO_CLOSE' or 'SELL_TO_CLOSE' (default 'BUY_TO_CLOSE').
        open_instruction:  'SELL_TO_OPEN' or 'BUY_TO_OPEN' (default 'SELL_TO_OPEN').
        price:             Net credit or net debit limit price (required).
        order_type:        'NET_CREDIT' or 'NET_DEBIT' (default 'NET_CREDIT').
        duration:          'GOOD_TILL_CANCEL' or 'DAY' (default 'GOOD_TILL_CANCEL').
        session:           'NORMAL', 'AM', 'PM', 'SEAMLESS' (default 'NORMAL').

    Returns:
        Dict conforming to Schwab multi-leg custom order schema.

    Raises:
        ValueError: If any parameter is invalid.
    """
    if not close_symbol or not str(close_symbol).strip():
        raise ValueError("Roll order requires a non-empty 'close_symbol'.")
    if not open_symbol or not str(open_symbol).strip():
        raise ValueError("Roll order requires a non-empty 'open_symbol'.")

    close_sym_str = str(close_symbol).strip().upper()
    open_sym_str = str(open_symbol).strip().upper()

    qty_num = _validate_quantity(quantity)

    # Normalize instructions
    canonical_close_instruction = _normalize_field(close_instruction, INSTRUCTION_MAP, "close_instruction")
    if canonical_close_instruction not in ("BUY_TO_CLOSE", "SELL_TO_CLOSE"):
        raise ValueError(
            f"Invalid close_instruction '{close_instruction}'. Must be BUY_TO_CLOSE or SELL_TO_CLOSE."
        )

    canonical_open_instruction = _normalize_field(open_instruction, INSTRUCTION_MAP, "open_instruction")
    if canonical_open_instruction not in ("SELL_TO_OPEN", "BUY_TO_OPEN"):
        raise ValueError(
            f"Invalid open_instruction '{open_instruction}'. Must be SELL_TO_OPEN or BUY_TO_OPEN."
        )

    # Normalize order type (must be NET_CREDIT or NET_DEBIT or NET_ZERO).
    # 'LIMIT' is mapped to 'NET_CREDIT' for UI ergonomics: the roll order form
    # defaults to NET_CREDIT, but the generic order type dropdown may send 'LIMIT'.
    otype_key = str(order_type).strip().upper()
    if otype_key not in ("NET_CREDIT", "NET_DEBIT", "NET_ZERO", "LIMIT"):
        raise ValueError(f"Invalid roll order_type '{order_type}'. Must be NET_CREDIT or NET_DEBIT.")
    canonical_order_type = "NET_CREDIT" if otype_key in ("NET_CREDIT", "LIMIT") else otype_key

    canonical_duration = _normalize_field(duration, DURATION_MAP, "duration")
    canonical_session = _normalize_field(session, SESSION_MAP, "session")

    if price is None:
        raise ValueError(f"Price is required for roll order type '{canonical_order_type}'.")

    return {
        "session": canonical_session,
        "duration": canonical_duration,
        "orderType": canonical_order_type,
        "complexOrderStrategyType": "CUSTOM",
        "orderStrategyType": "SINGLE",
        "quantity": qty_num,
        "price": format_price(price),
        "orderLegCollection": [
            {
                "instruction": canonical_close_instruction,
                "quantity": qty_num,
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": close_sym_str,
                },
            },
            {
                "instruction": canonical_open_instruction,
                "quantity": qty_num,
                "instrument": {
                    "assetType": "OPTION",
                    "symbol": open_sym_str,
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Public order placement and preview services
# ---------------------------------------------------------------------------

def execute_order(
    access_token: str,
    account: str | None = None,
    order_payload: dict | None = None,
    *,
    preview: bool = False,
) -> dict:
    """Submit or preview an order on the Charles Schwab Trader API.

    Args:
        access_token:  Valid Schwab Bearer access token.
        account:       Account alias, suffix, or hash.
        order_payload: Pre-constructed order dict (required).
        preview:       If True, preview the order without executing.

    Returns:
        Dict with order result or preview evaluation from Schwab.

    Raises:
        ValueError: If order_payload is missing.
    """
    if order_payload is None:
        raise ValueError("execute_order: 'order_payload' is required.")

    account_hash = resolve_account_hash(account)
    action = "Previewing" if preview else "Submitting live"
    logging.info("%s order for account %s: %s", action, account_hash, order_payload)

    fn = schwab_api.preview_order if preview else schwab_api.place_order
    return fn(access_token, account_hash, order_payload)


def place_order(
    access_token: str,
    account: str | None = None,
    order_payload: dict | None = None,
) -> dict:
    """Prepare and submit a live order to the Charles Schwab Trader API."""
    return execute_order(access_token, account, order_payload, preview=False)


def preview_order(
    access_token: str,
    account: str | None = None,
    order_payload: dict | None = None,
) -> dict:
    """Preview an order with the Charles Schwab Trader API without executing it."""
    return execute_order(access_token, account, order_payload, preview=True)
