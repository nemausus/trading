"""
schwab_api.py
~~~~~~~~~~~~~
Single authoritative gateway for all non-auth Schwab API calls.

Each public function corresponds to exactly one Schwab endpoint.  Functions
validate that required parameters are present, apply sensible defaults, then
delegate to the shared ``schwab_request()`` HTTP transport at the bottom of
this module.  No business logic lives here.

Auth-related calls (token exchange / refresh) remain in ``schwab_auth.py``.
"""

from datetime import datetime
import json
import logging
import re

import requests

from constants import SCHWAB_REQUEST_TIMEOUT

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------

SCHWAB_MARKETDATA_BASE_URL = "https://api.schwabapi.com/marketdata/v1"
SCHWAB_TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SchwabAPIError(Exception):
    """Raised when a Schwab API HTTP call fails.

    Wraps the underlying requests.HTTPError so callers only need to import
    and catch this one type rather than anything from the requests library.
    """

    def __init__(self, message: str, response: requests.Response | None = None):
        super().__init__(message)
        self.response = response


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _headers(access_token: str) -> dict:
    """Return standard Schwab Bearer auth headers for every API call."""
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


def _save_response_dump(url: str, data: dict | list) -> None:
    """Save raw response JSON to a file in responses/ directory for debugging."""
    filename = "responses/" + url.replace("/", "_").replace(":", "_") + ".json"
    with open(filename, "w") as f:
        f.write(str(datetime.now()))
        f.write("\n")
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Market Data endpoints
# ---------------------------------------------------------------------------


def get_quotes(access_token: str, symbols: list[str]) -> dict:
    """Fetch real-time quotes for a list of symbols.

    Args:
        access_token: Valid Schwab Bearer access token.
        symbols:      Non-empty list of ticker / option symbols.

    Returns:
        Raw quotes dict keyed by symbol.

    Raises:
        ValueError: If *symbols* is empty.
    """
    if not symbols:
        raise ValueError("get_quotes: 'symbols' must be a non-empty list.")

    return schwab_request(
        "GET",
        f"{SCHWAB_MARKETDATA_BASE_URL}/quotes",
        headers=_headers(access_token),
        params={"symbols": ",".join(symbols)},
    )


def get_option_chains(
    access_token: str,
    symbol: str,
    *,
    contract_type: str = "ALL",
    from_date: str | None = None,
    to_date: str | None = None,
    include_underlying_quote: bool = True,
) -> dict:
    """Fetch the option chain for an underlying symbol.

    Args:
        access_token:             Valid Schwab Bearer access token.
        symbol:                   Underlying ticker (e.g. 'AAPL', '$SPX').
        contract_type:            'CALL', 'PUT', or 'ALL' (default 'ALL').
        from_date:                ISO date string filter (inclusive lower bound).
        to_date:                  ISO date string filter (inclusive upper bound).
        include_underlying_quote: Whether to include the underlying quote in the
                                  response (default True).

    Returns:
        Raw Schwab chains response dict.

    Raises:
        ValueError: If *symbol* is missing.
    """
    if not symbol:
        raise ValueError("get_option_chains: 'symbol' is required.")

    if contract_type not in ("CALL", "PUT", "ALL"):
        logging.warning(
            "get_option_chains: unexpected contract_type '%s', defaulting to 'ALL'.",
            contract_type,
        )
        contract_type = "ALL"

    params: dict = {
        "symbol": symbol,
        "contractType": contract_type,
        "includeUnderlyingQuote": include_underlying_quote,
    }
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date

    return schwab_request(
        "GET",
        f"{SCHWAB_MARKETDATA_BASE_URL}/chains",
        headers=_headers(access_token),
        params=params,
    )


def get_price_history(
    access_token: str,
    symbol: str,
    *,
    period_type: str | None = None,
    period: int | None = None,
    frequency_type: str | None = None,
    frequency: int | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    need_extended_hours_data: bool = False,
    need_previous_close: bool = False,
) -> dict:
    """Fetch historical candlestick price data for a symbol.

    Args:
        access_token:             Valid Schwab Bearer access token.
        symbol:                   Security ticker (e.g. 'AAPL').
        period_type:              'day', 'month', 'year', 'ytd'.
        period:                   Number of periods.
        frequency_type:           'minute', 'daily', 'weekly', 'monthly'.
        frequency:                Granularity frequency (e.g. 1, 5, 15, 30).
        start_date:               Epoch time in milliseconds.
        end_date:                 Epoch time in milliseconds.
        need_extended_hours_data: Whether to include extended hours data.
        need_previous_close:      Whether to include previous close price.

    Returns:
        Raw Schwab price history response dict containing candles.

    Raises:
        ValueError: If access_token or symbol is missing.
    """
    if not access_token:
        raise ValueError("get_price_history: 'access_token' is required.")
    if not symbol:
        raise ValueError("get_price_history: 'symbol' is required.")

    params: dict = {"symbol": symbol}
    if period_type is not None:
        params["periodType"] = period_type
    if period is not None:
        params["period"] = period
    if frequency_type is not None:
        params["frequencyType"] = frequency_type
    if frequency is not None:
        params["frequency"] = frequency
    if start_date is not None:
        params["startDate"] = start_date
    if end_date is not None:
        params["endDate"] = end_date
    if need_extended_hours_data:
        params["needExtendedHoursData"] = "true"
    if need_previous_close:
        params["needPreviousClose"] = "true"

    return schwab_request(
        "GET",
        f"{SCHWAB_MARKETDATA_BASE_URL}/pricehistory",
        headers=_headers(access_token),
        params=params,
    )


# ---------------------------------------------------------------------------
# Trader / Accounts endpoints
# ---------------------------------------------------------------------------


def get_accounts(access_token: str, *, fields: str = "positions") -> list:
    """Fetch all accounts for the authenticated user.

    Args:
        access_token: Valid Schwab Bearer access token.
        fields:       Comma-separated fields to include (default 'positions').

    Returns:
        Raw list of account dicts from Schwab.
    """
    return schwab_request(
        "GET",
        f"{SCHWAB_TRADER_BASE_URL}/accounts",
        headers=_headers(access_token),
        params={"fields": fields},
    )


def get_orders(
    access_token: str,
    account_hash: str,
    *,
    from_entered_time: str,
    to_entered_time: str,
) -> list:
    """Fetch orders for a specific account within a time window.

    Args:
        access_token:      Valid Schwab Bearer access token.
        account_hash:      Encrypted Schwab account hash.
        from_entered_time: ISO datetime string (lower bound, inclusive).
        to_entered_time:   ISO datetime string (upper bound, inclusive).

    Returns:
        Raw list of order dicts from Schwab.

    Raises:
        ValueError: If *account_hash*, *from_entered_time*, or *to_entered_time*
                    are missing.
    """
    if not account_hash:
        raise ValueError("get_orders: 'account_hash' is required.")
    if not from_entered_time:
        raise ValueError("get_orders: 'from_entered_time' is required.")
    if not to_entered_time:
        raise ValueError("get_orders: 'to_entered_time' is required.")

    return schwab_request(
        "GET",
        f"{SCHWAB_TRADER_BASE_URL}/accounts/{account_hash}/orders",
        headers=_headers(access_token),
        params={
            "fromEnteredTime": from_entered_time,
            "toEnteredTime": to_entered_time,
        },
    )


def get_transactions(
    access_token: str,
    account_hash: str,
    *,
    start_date: str,
    end_date: str,
) -> list:
    """Fetch transactions for a specific account within a date range.

    Args:
        access_token:  Valid Schwab Bearer access token.
        account_hash:  Encrypted Schwab account hash.
        start_date:    ISO datetime string (lower bound, e.g. '2026-01-01T00:00:00-07:30').
        end_date:      ISO datetime string (upper bound).

    Returns:
        Raw list of transaction dicts from Schwab.

    Raises:
        ValueError: If *account_hash*, *start_date*, or *end_date* are missing.
    """
    if not account_hash:
        raise ValueError("get_transactions: 'account_hash' is required.")
    if not start_date:
        raise ValueError("get_transactions: 'start_date' is required.")
    if not end_date:
        raise ValueError("get_transactions: 'end_date' is required.")

    return schwab_request(
        "GET",
        f"{SCHWAB_TRADER_BASE_URL}/accounts/{account_hash}/transactions",
        headers=_headers(access_token),
        params={"startDate": start_date, "endDate": end_date},
    )


def place_order(
    access_token: str,
    account_hash: str,
    order_payload: dict,
) -> dict:
    """Place an order for a specific account.

    Args:
        access_token:  Valid Schwab Bearer access token.
        account_hash:  Encrypted Schwab account hash.
        order_payload: Full Schwab order dictionary.

    Returns:
        Dict with 'success', 'orderId' (if extracted from Location header),
        'location' (if present), and original 'order'.

    Raises:
        ValueError:    If account_hash or order_payload are missing.
        SchwabAPIError: If the Schwab API request fails.
    """
    if not access_token:
        raise ValueError("place_order: 'access_token' is required.")
    if not account_hash:
        raise ValueError("place_order: 'account_hash' is required.")
    if not order_payload or not isinstance(order_payload, dict):
        raise ValueError("place_order: 'order_payload' must be a non-empty dict.")

    resp = schwab_request(
        "POST",
        f"{SCHWAB_TRADER_BASE_URL}/accounts/{account_hash}/orders",
        headers=_headers(access_token),
        params={"accountNumber": account_hash},
        json=order_payload,
        return_response=True,
    )

    location = resp.headers.get("Location") or resp.headers.get("location")
    order_id = None
    if location:
        m = re.search(r"/accounts/(\w+)/orders/(\d+)", location)
        if m:
            order_id = int(m.group(2))

    res: dict = {
        "success": True,
        "orderId": order_id,
        "location": location,
        "order": order_payload,
    }
    if resp.text and resp.text.strip():
        try:
            res["response"] = resp.json()
        except Exception:
            res["raw"] = resp.text
    return res


def preview_order(
    access_token: str,
    account_hash: str,
    order_payload: dict,
) -> dict:
    """Preview/simulate an order for a specific account without executing it.

    Args:
        access_token:  Valid Schwab Bearer access token.
        account_hash:  Encrypted Schwab account hash.
        order_payload: Full Schwab order dictionary.

    Returns:
        Parsed JSON evaluation dictionary from Schwab previewOrder endpoint.

    Raises:
        ValueError:    If account_hash or order_payload are missing.
        SchwabAPIError: If the Schwab API request fails.
    """
    if not access_token:
        raise ValueError("preview_order: 'access_token' is required.")
    if not account_hash:
        raise ValueError("preview_order: 'account_hash' is required.")
    if not order_payload or not isinstance(order_payload, dict):
        raise ValueError("preview_order: 'order_payload' must be a non-empty dict.")

    return schwab_request(
        "POST",
        f"{SCHWAB_TRADER_BASE_URL}/accounts/{account_hash}/previewOrder",
        headers=_headers(access_token),
        params={"accountNumber": account_hash},
        json=order_payload,
    )


# ---------------------------------------------------------------------------
# HTTP transport (shared by all gateway functions above)
# ---------------------------------------------------------------------------


def schwab_request(
    method: str,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    data: dict | None = None,
    timeout: tuple[int, int] = SCHWAB_REQUEST_TIMEOUT,
    return_response: bool = False,
    **kwargs,
) -> dict | list | requests.Response:
    """Make an HTTP request to the Schwab backend with unified logging.

    Logs the request, executes the call, and returns parsed JSON (or Response object
    if return_response=True).
    Raises SchwabAPIError on any HTTP or network failure.
    """
    logging.info("Making Schwab API %s request to %s (params=%s)", method, url, params)

    try:
        resp = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            data=data,
            timeout=timeout,
            **kwargs,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        resp = getattr(e, "response", None)
        raise SchwabAPIError(f"{method.upper()} {url} failed: {e}", response=resp) from e

    if return_response:
        return resp

    if not resp.text or not resp.text.strip():
        return {}

    ret = resp.json()
    # _save_response_dump(url, ret)
    return ret
