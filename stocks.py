"""
stocks.py
~~~~~~~~~
Service module for historical stock price data, normalization, parameter validation,
and in-memory caching.
"""

import logging
import re
import threading
import time

import schwab_api
from schwab_api import SchwabAPIError

_VALID_PERIODS = {"5D", "1M", "3M", "6M", "1Y", "2Y", "5Y"}
_VALID_INTERVALS = {"1M", "5M", "15M", "30M", "1D", "1W", "1MO"}
_INTRADAY_INTERVALS = {"1M", "5M", "15M", "30M"}

_DEFAULT_DAILY_TTL = 900  # 15 minutes for daily/weekly/monthly data
_DEFAULT_INTRADAY_TTL = 60  # 1 minute for intraday data

_TICKER_REGEX = re.compile(r"^[A-Z0-9.\-\/\$]{1,10}$")


class StockHistoryCache:
    """Thread-safe in-memory cache for historical stock price data."""

    def __init__(
        self, daily_ttl: int = _DEFAULT_DAILY_TTL, intraday_ttl: int = _DEFAULT_INTRADAY_TTL
    ):
        self._daily_ttl = daily_ttl
        self._intraday_ttl = intraday_ttl
        self._cache: dict[str, tuple[float, int, dict]] = {}
        self._lock = threading.Lock()

    def _make_key(self, symbol: str, period: str, interval: str) -> str:
        return f"{symbol.upper()}|{period.upper()}|{interval.upper()}"

    def get(self, symbol: str, period: str, interval: str) -> dict | None:
        """Retrieve cached history if present and not expired."""
        key = self._make_key(symbol, period, interval)
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            cached_at, ttl, data = entry
            if time.time() - cached_at > ttl:
                del self._cache[key]
                return None
            return data

    def set(
        self, symbol: str, period: str, interval: str, data: dict, ttl: int | None = None
    ) -> None:
        """Store history data in cache with appropriate TTL."""
        key = self._make_key(symbol, period, interval)
        if ttl is None:
            norm_interval = interval.strip().upper()
            ttl = self._intraday_ttl if norm_interval in _INTRADAY_INTERVALS else self._daily_ttl
        with self._lock:
            self._cache[key] = (time.time(), ttl, data)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def delete(self, symbol: str, period: str, interval: str) -> bool:
        """Remove a specific entry from cache if present."""
        key = self._make_key(symbol, period, interval)
        with self._lock:
            return self._cache.pop(key, None) is not None


# Module singleton cache
stocks_cache = StockHistoryCache()


def _clean_ticker(ticker: str) -> str:
    """Validate and sanitize a stock ticker symbol."""
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Ticker symbol must be a non-empty string.")
    clean = ticker.strip().upper()
    if not _TICKER_REGEX.match(clean):
        raise ValueError(f"Invalid ticker symbol: '{ticker}'.")
    return clean


def _normalize_period_str(period: str) -> str:
    """Normalize period string to canonical representation (e.g. '1y' -> '1Y')."""
    if not period or not isinstance(period, str):
        raise ValueError("Period must be a non-empty string.")
    p = period.strip().upper()
    if p not in _VALID_PERIODS:
        raise ValueError(
            f"Unsupported period '{period}'. Supported periods: {', '.join(sorted(_VALID_PERIODS))}."
        )
    return p


def _normalize_interval_str(interval: str) -> str:
    """Normalize interval string to canonical representation (e.g. '1d' -> '1D')."""
    if not interval or not isinstance(interval, str):
        raise ValueError("Interval must be a non-empty string.")
    inv = interval.strip().upper()
    # Normalize synonyms (e.g. '1MO', '1MONTH', 'MONTHLY' -> '1MO')
    # NOTE: '1M' is NOT mapped to monthly — it means 1-minute intraday.
    if inv in ("1MO", "MONTH", "MONTHLY", "1MONTH"):
        inv = "1MO"
    elif inv in ("1MIN", "1MINUTE"):
        inv = "1M"
    elif inv in ("5MIN", "5MINUTE"):
        inv = "5M"
    elif inv in ("15MIN", "15MINUTE"):
        inv = "15M"
    elif inv in ("30MIN", "30MINUTE"):
        inv = "30M"
    elif inv in ("1DAY", "DAILY"):
        inv = "1D"
    elif inv in ("1WK", "WEEK", "WEEKLY"):
        inv = "1W"

    if inv not in _VALID_INTERVALS:
        raise ValueError(
            f"Unsupported interval '{interval}'. Supported intervals: {', '.join(sorted(_VALID_INTERVALS))}."
        )
    return inv


def _map_period_and_interval(period: str, interval: str) -> tuple[dict, int | None]:
    """Validate combination and map to Schwab pricehistory request parameters.

    Returns:
        (schwab_params, slice_last_n)
    """
    schwab_params: dict = {}
    slice_last_n: int | None = None

    if interval in _INTRADAY_INTERVALS:
        if period != "5D":
            raise ValueError(
                f"Intraday interval '{interval}' is not supported for period '{period}'. "
                "Intraday data is only available for periods up to 10 days (e.g. 5D)."
            )
        freq = int(interval[:-1])
        schwab_params = {
            "period_type": "day",
            "period": 5,
            "frequency_type": "minute",
            "frequency": freq,
        }
    elif interval == "1D":
        if period == "5D":
            # Schwab API day periodType does not support daily frequencyType directly.
            # Request 1 month daily from Schwab, then slice the last 5 trading days.
            schwab_params = {
                "period_type": "month",
                "period": 1,
                "frequency_type": "daily",
                "frequency": 1,
            }
            slice_last_n = 5
        elif period in ("1M", "3M", "6M"):
            months = int(period[:-1])
            schwab_params = {
                "period_type": "month",
                "period": months,
                "frequency_type": "daily",
                "frequency": 1,
            }
        elif period in ("1Y", "2Y", "5Y"):
            years = int(period[:-1])
            schwab_params = {
                "period_type": "year",
                "period": years,
                "frequency_type": "daily",
                "frequency": 1,
            }
    elif interval == "1W":
        if period == "5D":
            raise ValueError("Weekly interval '1W' requires a period of at least 1M.")
        elif period in ("1M", "3M", "6M"):
            months = int(period[:-1])
            schwab_params = {
                "period_type": "month",
                "period": months,
                "frequency_type": "weekly",
                "frequency": 1,
            }
        elif period in ("1Y", "2Y", "5Y"):
            years = int(period[:-1])
            schwab_params = {
                "period_type": "year",
                "period": years,
                "frequency_type": "weekly",
                "frequency": 1,
            }
    elif interval == "1MO":
        if period in ("5D", "1M", "3M", "6M"):
            raise ValueError(f"Monthly interval '{interval}' requires a period of at least 1Y.")
        years = int(period[:-1])
        schwab_params = {
            "period_type": "year",
            "period": years,
            "frequency_type": "monthly",
            "frequency": 1,
        }

    if not schwab_params:
        raise ValueError(
            f"No valid Schwab parameter mapping for period='{period}', interval='{interval}'."
        )

    return schwab_params, slice_last_n


def _normalize_candle(raw: dict) -> dict | None:
    """Normalize a single raw Schwab candle dict.

    Returns:
        dict with keys: time (int, seconds), open, high, low, close, volume,
        or None if required fields are missing or invalid.
    """
    raw_dt = raw.get("datetime")
    if raw_dt is None:
        return None
    try:
        # Schwab reports datetime in milliseconds since epoch
        time_sec = int(raw_dt) // 1000
        open_val = round(float(raw.get("open", 0.0)), 4)
        high_val = round(float(raw.get("high", 0.0)), 4)
        low_val = round(float(raw.get("low", 0.0)), 4)
        close_val = round(float(raw.get("close", 0.0)), 4)
        volume_val = int(raw.get("volume", 0))
    except (ValueError, TypeError):
        return None

    return {
        "time": time_sec,
        "open": open_val,
        "high": high_val,
        "low": low_val,
        "close": close_val,
        "volume": volume_val,
    }


def normalize_price_history(
    raw_response: dict, symbol: str, slice_last_n: int | None = None
) -> dict:
    """Normalize raw Schwab price history JSON response into clean OHLCV format.

    Ensures candles are strictly sorted ascending by time and deduplicated.
    """
    if not isinstance(raw_response, dict):
        return {"symbol": symbol, "candles": []}

    raw_candles = raw_response.get("candles", [])
    if not raw_candles:
        return {"symbol": symbol, "candles": []}

    parsed = []
    for c in raw_candles:
        norm = _normalize_candle(c)
        if norm is not None:
            parsed.append(norm)

    # Sort ascending by time
    parsed.sort(key=lambda x: x["time"])

    # Deduplicate consecutive identical timestamps (Lightweight Charts requires strictly ascending time)
    deduped = []
    seen_times = set()
    for candle in parsed:
        t = candle["time"]
        if t not in seen_times:
            seen_times.add(t)
            deduped.append(candle)

    if slice_last_n is not None and len(deduped) > slice_last_n:
        deduped = deduped[-slice_last_n:]

    return {
        "symbol": symbol,
        "candles": deduped,
    }


def fetch_stock_history(
    access_token: str,
    ticker: str,
    period: str = "1Y",
    interval: str = "1D",
    use_cache: bool = True,
) -> dict:
    """Fetch, normalize, and cache historical price data for a ticker.

    Args:
        access_token: Valid Schwab Bearer access token.
        ticker:       Stock ticker symbol (e.g. 'AAPL').
        period:       Time horizon (5D, 1M, 3M, 6M, 1Y, 2Y, 5Y).
        interval:     Candle interval (1M, 5M, 15M, 30M, 1D, 1W, 1MO).
        use_cache:    Whether to check/populate the in-memory cache.

    Returns:
        Dict formatted as:
        {
            "symbol": "AAPL",
            "candles": [
                {
                    "time": 1724976000,
                    "open": 228.55,
                    "high": 229.40,
                    "low": 226.88,
                    "close": 228.22,
                    "volume": 31234567
                },
                ...
            ]
        }

    Raises:
        ValueError: On invalid ticker or incompatible period/interval parameters.
        SchwabAPIError: If the Schwab API call fails.
    """
    clean_ticker = _clean_ticker(ticker)
    norm_period = _normalize_period_str(period)
    norm_interval = _normalize_interval_str(interval)

    # Check cache first
    if use_cache:
        cached = stocks_cache.get(clean_ticker, norm_period, norm_interval)
        if cached is not None:
            logging.debug(
                "Stock history cache hit for %s %s %s", clean_ticker, norm_period, norm_interval
            )
            return cached

    # Map parameters to Schwab API request kwargs
    schwab_params, slice_last_n = _map_period_and_interval(norm_period, norm_interval)

    # Invoke Schwab pricehistory endpoint
    raw_resp = schwab_api.get_price_history(
        access_token,
        clean_ticker,
        **schwab_params,
    )

    # Normalize response
    result = normalize_price_history(raw_resp, clean_ticker, slice_last_n=slice_last_n)

    # Cache successful non-empty result
    if use_cache and result.get("candles"):
        stocks_cache.set(clean_ticker, norm_period, norm_interval, result)

    return result
