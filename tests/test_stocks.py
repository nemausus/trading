"""
Unit tests for stocks.py and Schwab price history integration.

Run with:
    ./.venv/bin/python -m unittest tests/test_stocks.py -v
"""

import time
import unittest
from unittest.mock import patch, MagicMock

import schwab_api as sa
from schwab_api import SchwabAPIError
import stocks
from stocks import (
    StockHistoryCache,
    _clean_ticker,
    _normalize_period_str,
    _normalize_interval_str,
    _map_period_and_interval,
    normalize_price_history,
    fetch_stock_history,
)


class TestSchwabPriceHistoryApi(unittest.TestCase):
    """Tests for schwab_api.get_price_history."""

    @patch("schwab_api.schwab_request")
    def test_get_price_history_success(self, mock_request):
        mock_request.return_value = {
            "symbol": "AAPL",
            "candles": [
                {
                    "datetime": 1724976000000,
                    "open": 228.5,
                    "high": 229.4,
                    "low": 226.8,
                    "close": 228.2,
                    "volume": 10000,
                }
            ],
            "empty": False,
        }

        res = sa.get_price_history(
            "token123", "AAPL", period_type="year", period=1, frequency_type="daily", frequency=1
        )

        self.assertEqual(res["symbol"], "AAPL")
        self.assertEqual(len(res["candles"]), 1)
        mock_request.assert_called_once_with(
            "GET",
            f"{sa.SCHWAB_MARKETDATA_BASE_URL}/pricehistory",
            headers=sa._headers("token123"),
            params={
                "symbol": "AAPL",
                "periodType": "year",
                "period": 1,
                "frequencyType": "daily",
                "frequency": 1,
            },
        )

    def test_get_price_history_missing_args(self):
        with self.assertRaises(ValueError):
            sa.get_price_history("", "AAPL")
        with self.assertRaises(ValueError):
            sa.get_price_history("token123", "")

    @patch("schwab_api.schwab_request")
    def test_get_price_history_api_error(self, mock_request):
        mock_request.side_effect = SchwabAPIError("Schwab API 500 internal error")
        with self.assertRaises(SchwabAPIError):
            sa.get_price_history("token123", "AAPL")


class TestStockValidationAndMapping(unittest.TestCase):
    """Tests for ticker and parameter validation, normalization, and Schwab parameter mapping."""

    def test_clean_ticker_valid(self):
        self.assertEqual(_clean_ticker("aapl"), "AAPL")
        self.assertEqual(_clean_ticker("  msft  "), "MSFT")
        self.assertEqual(_clean_ticker("brk.b"), "BRK.B")
        self.assertEqual(_clean_ticker("$spx"), "$SPX")

    def test_clean_ticker_invalid(self):
        with self.assertRaises(ValueError):
            _clean_ticker("")
        with self.assertRaises(ValueError):
            _clean_ticker("   ")
        with self.assertRaises(ValueError):
            _clean_ticker("TOOLONGTICKERNAME")
        with self.assertRaises(ValueError):
            _clean_ticker("AAPL!@#")

    def test_normalize_period(self):
        self.assertEqual(_normalize_period_str("1y"), "1Y")
        self.assertEqual(_normalize_period_str("5d"), "5D")
        self.assertEqual(_normalize_period_str("6m"), "6M")
        with self.assertRaises(ValueError):
            _normalize_period_str("10D")
        with self.assertRaises(ValueError):
            _normalize_period_str("invalid")

    def test_normalize_interval(self):
        self.assertEqual(_normalize_interval_str("1d"), "1D")
        self.assertEqual(_normalize_interval_str("daily"), "1D")
        self.assertEqual(_normalize_interval_str("5m"), "5M")
        self.assertEqual(_normalize_interval_str("5min"), "5M")
        self.assertEqual(_normalize_interval_str("1w"), "1W")
        self.assertEqual(_normalize_interval_str("weekly"), "1W")
        self.assertEqual(_normalize_interval_str("1mo"), "1MO")
        with self.assertRaises(ValueError):
            _normalize_interval_str("2h")

    def test_map_period_and_interval_valid(self):
        # 1Y + 1D -> periodType: year, period: 1, frequencyType: daily, frequency: 1
        params, slice_n = _map_period_and_interval("1Y", "1D")
        self.assertEqual(params["period_type"], "year")
        self.assertEqual(params["period"], 1)
        self.assertEqual(params["frequency_type"], "daily")
        self.assertIsNone(slice_n)

        # 5D + 5M -> periodType: day, period: 5, frequencyType: minute, frequency: 5
        params, slice_n = _map_period_and_interval("5D", "5M")
        self.assertEqual(params["period_type"], "day")
        self.assertEqual(params["period"], 5)
        self.assertEqual(params["frequency_type"], "minute")
        self.assertEqual(params["frequency"], 5)
        self.assertIsNone(slice_n)

        # 5D + 1D -> periodType: month, period: 1, frequencyType: daily, slice_n: 5
        params, slice_n = _map_period_and_interval("5D", "1D")
        self.assertEqual(params["period_type"], "month")
        self.assertEqual(params["period"], 1)
        self.assertEqual(params["frequency_type"], "daily")
        self.assertEqual(slice_n, 5)

        # 6M + 1W -> periodType: month, period: 6, frequencyType: weekly
        params, slice_n = _map_period_and_interval("6M", "1W")
        self.assertEqual(params["period_type"], "month")
        self.assertEqual(params["period"], 6)
        self.assertEqual(params["frequency_type"], "weekly")
        self.assertIsNone(slice_n)

        # 2Y + 1MO -> periodType: year, period: 2, frequencyType: monthly
        params, slice_n = _map_period_and_interval("2Y", "1MO")
        self.assertEqual(params["period_type"], "year")
        self.assertEqual(params["period"], 2)
        self.assertEqual(params["frequency_type"], "monthly")
        self.assertIsNone(slice_n)

    def test_map_period_and_interval_incompatible(self):
        # 1Y with 5m minute data should fail
        with self.assertRaises(ValueError):
            _map_period_and_interval("1Y", "5M")

        # 5D with 1W should fail (5 days is less than a week)
        with self.assertRaises(ValueError):
            _map_period_and_interval("5D", "1W")

        # 1M with 1MO should fail (requires >= 1Y)
        with self.assertRaises(ValueError):
            _map_period_and_interval("1M", "1MO")


class TestCandleNormalization(unittest.TestCase):
    """Tests for normalizing raw Schwab candles into simple OHLCV JSON."""

    def test_normalize_price_history_basic(self):
        raw = {
            "symbol": "AAPL",
            "candles": [
                {
                    "datetime": 1724976000000,
                    "open": 228.55,
                    "high": 229.40,
                    "low": 226.88,
                    "close": 228.22,
                    "volume": 31234567,
                }
            ],
        }
        res = normalize_price_history(raw, "AAPL")
        self.assertEqual(res["symbol"], "AAPL")
        self.assertEqual(len(res["candles"]), 1)
        candle = res["candles"][0]
        self.assertEqual(candle["time"], 1724976000)
        self.assertEqual(candle["open"], 228.55)
        self.assertEqual(candle["high"], 229.40)
        self.assertEqual(candle["low"], 226.88)
        self.assertEqual(candle["close"], 228.22)
        self.assertEqual(candle["volume"], 31234567)

    def test_normalize_price_history_sorting_and_dedup(self):
        raw = {
            "candles": [
                {"datetime": 3000000, "open": 3, "high": 3, "low": 3, "close": 3, "volume": 3},
                {"datetime": 1000000, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"datetime": 2000000, "open": 2, "high": 2, "low": 2, "close": 2, "volume": 2},
                {
                    "datetime": 2000000,
                    "open": 2.1,
                    "high": 2.1,
                    "low": 2.1,
                    "close": 2.1,
                    "volume": 20,
                },  # Duplicate timestamp
            ]
        }
        res = normalize_price_history(raw, "AAPL")
        times = [c["time"] for c in res["candles"]]
        self.assertEqual(times, [1000, 2000, 3000])

    def test_normalize_price_history_slicing(self):
        raw = {
            "candles": [
                {"datetime": i * 1000000, "open": i, "high": i, "low": i, "close": i, "volume": i}
                for i in range(1, 11)
            ]
        }
        res = normalize_price_history(raw, "AAPL", slice_last_n=5)
        self.assertEqual(len(res["candles"]), 5)
        self.assertEqual(res["candles"][-1]["time"], 10000)
        self.assertEqual(res["candles"][0]["time"], 6000)

    def test_normalize_price_history_empty(self):
        res = normalize_price_history({}, "AAPL")
        self.assertEqual(res, {"symbol": "AAPL", "candles": []})
        res = normalize_price_history({"candles": []}, "AAPL")
        self.assertEqual(res, {"symbol": "AAPL", "candles": []})


class TestStockHistoryCache(unittest.TestCase):
    """Tests for thread-safe in-memory cache."""

    def setUp(self):
        self.cache = StockHistoryCache(daily_ttl=2, intraday_ttl=1)

    def test_cache_set_and_get(self):
        dummy_data = {"symbol": "AAPL", "candles": [{"time": 100, "close": 200}]}
        self.cache.set("aapl", "1Y", "1D", dummy_data)

        # Retrieval is case-insensitive
        cached = self.cache.get("AAPL", "1y", "1d")
        self.assertEqual(cached, dummy_data)

    def test_cache_miss(self):
        self.assertIsNone(self.cache.get("MSFT", "1Y", "1D"))

    def test_cache_expiration(self):
        dummy_data = {"symbol": "AAPL", "candles": []}
        self.cache.set("AAPL", "1Y", "1D", dummy_data, ttl=0.1)
        self.assertEqual(self.cache.get("AAPL", "1Y", "1D"), dummy_data)

        time.sleep(0.15)
        self.assertIsNone(self.cache.get("AAPL", "1Y", "1D"))

    def test_cache_clear_and_delete(self):
        self.cache.set("AAPL", "1Y", "1D", {"a": 1})
        self.cache.set("MSFT", "1Y", "1D", {"b": 2})

        self.assertTrue(self.cache.delete("AAPL", "1Y", "1D"))
        self.assertIsNone(self.cache.get("AAPL", "1Y", "1D"))
        self.assertIsNotNone(self.cache.get("MSFT", "1Y", "1D"))

        self.cache.clear()
        self.assertIsNone(self.cache.get("MSFT", "1Y", "1D"))


class TestFetchStockHistoryService(unittest.TestCase):
    """Tests for high-level fetch_stock_history service function."""

    def setUp(self):
        stocks.stocks_cache.clear()

    @patch("schwab_api.get_price_history")
    def test_fetch_stock_history_caches_response(self, mock_get_history):
        mock_get_history.return_value = {
            "symbol": "AAPL",
            "candles": [
                {
                    "datetime": 1724976000000,
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 104,
                    "volume": 5000,
                }
            ],
        }

        # First call hits Schwab API
        res1 = fetch_stock_history("tok123", "AAPL", "1Y", "1D")
        self.assertEqual(len(res1["candles"]), 1)
        self.assertEqual(mock_get_history.call_count, 1)

        # Second call hits cache; mock_get_history should NOT be called again
        res2 = fetch_stock_history("tok123", "AAPL", "1Y", "1D")
        self.assertEqual(res1, res2)
        self.assertEqual(mock_get_history.call_count, 1)


class TestStockHistoryEndpoint(unittest.TestCase):
    """Tests for /api/schwab/stocks/<ticker>/history Flask route."""

    def setUp(self):
        from app import app

        app.config["TESTING"] = True
        self.client = app.test_client()
        stocks.stocks_cache.clear()

    def test_endpoint_missing_auth(self):
        resp = self.client.get("/api/schwab/stocks/AAPL/history")
        self.assertEqual(resp.status_code, 401)

    @patch("app.auth.verify_id_token")
    @patch("app.schwab_auth.refresh_user_tokens_if_needed")
    def test_endpoint_invalid_param(self, mock_tokens, mock_verify):
        mock_verify.return_value = {"uid": "test_user"}
        mock_tokens.return_value = "valid_schwab_token"

        # Invalid period
        resp = self.client.get(
            "/api/schwab/stocks/AAPL/history?period=99Y&interval=1D",
            headers={"Authorization": "Bearer test_token"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported period", resp.get_json()["error"])

    @patch("app.auth.verify_id_token")
    @patch("app.schwab_auth.refresh_user_tokens_if_needed")
    @patch("schwab_api.get_price_history")
    def test_endpoint_success(self, mock_schwab, mock_tokens, mock_verify):
        mock_verify.return_value = {"uid": "test_user"}
        mock_tokens.return_value = "valid_schwab_token"
        mock_schwab.return_value = {
            "symbol": "AAPL",
            "candles": [
                {
                    "datetime": 1724976000000,
                    "open": 228.55,
                    "high": 229.4,
                    "low": 226.88,
                    "close": 228.22,
                    "volume": 31234567,
                }
            ],
        }

        resp = self.client.get(
            "/api/schwab/stocks/AAPL/history?period=1Y&interval=1D",
            headers={"Authorization": "Bearer test_token"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["symbol"], "AAPL")
        self.assertEqual(len(data["candles"]), 1)
        self.assertEqual(data["candles"][0]["time"], 1724976000)
        self.assertEqual(data["candles"][0]["close"], 228.22)

    @patch("app.auth.verify_id_token")
    @patch("app.schwab_auth.refresh_user_tokens_if_needed")
    @patch("schwab_api.get_price_history")
    def test_endpoint_schwab_error(self, mock_schwab, mock_tokens, mock_verify):
        mock_verify.return_value = {"uid": "test_user"}
        mock_tokens.return_value = "valid_schwab_token"
        mock_schwab.side_effect = SchwabAPIError("Schwab API 502")

        resp = self.client.get(
            "/api/schwab/stocks/AAPL/history?period=1Y&interval=1D",
            headers={"Authorization": "Bearer test_token"},
        )
        self.assertEqual(resp.status_code, 502)
        self.assertIn("Schwab API error", resp.get_json()["error"])


class TestIndicatorAlgorithms(unittest.TestCase):
    """Verify SMA and Wilder's RSI algorithmic correctness against standard formulas."""

    def _calculate_sma(self, closes: list[float], period: int) -> list[float]:
        if len(closes) < period or period <= 0:
            return []
        res = []
        window_sum = sum(closes[:period])
        res.append(round(window_sum / period, 2))
        for i in range(period, len(closes)):
            window_sum += closes[i] - closes[i - period]
            res.append(round(window_sum / period, 2))
        return res

    def _calculate_rsi_wilder(self, closes: list[float], period: int = 14) -> list[float]:
        if len(closes) <= period or period <= 0:
            return []
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(diff if diff > 0 else 0.0)
            losses.append(-diff if diff < 0 else 0.0)

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        res = []
        if avg_loss == 0:
            res.append(100.0 if avg_gain > 0 else 50.0)
        else:
            rs = avg_gain / avg_loss
            res.append(round(100.0 - (100.0 / (1.0 + rs)), 2))

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                res.append(100.0 if avg_gain > 0 else 50.0)
            else:
                rs = avg_gain / avg_loss
                res.append(round(100.0 - (100.0 / (1.0 + rs)), 2))
        return res

    def test_sma_calculation(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        sma3 = self._calculate_sma(prices, 3)
        self.assertEqual(sma3, [20.0, 30.0, 40.0])

        # Test SMA 20, 50, 200 with 250 price points
        long_prices = [100.0 + i for i in range(250)]
        sma20 = self._calculate_sma(long_prices, 20)
        self.assertEqual(len(sma20), 231)
        # Average of 100 to 119 = 109.5
        self.assertEqual(sma20[0], 109.5)

        sma50 = self._calculate_sma(long_prices, 50)
        self.assertEqual(len(sma50), 201)
        # Average of 100 to 149 = 124.5
        self.assertEqual(sma50[0], 124.5)

        sma200 = self._calculate_sma(long_prices, 200)
        self.assertEqual(len(sma200), 51)
        # Average of 100 to 299 = 199.5
        self.assertEqual(sma200[0], 199.5)

    def test_rsi_wilder_all_gains(self):
        prices = [100.0 + i * 2 for i in range(16)]
        rsi = self._calculate_rsi_wilder(prices, 14)
        self.assertEqual(len(rsi), 2)
        self.assertEqual(rsi[0], 100.0)
        self.assertEqual(rsi[1], 100.0)

    def test_rsi_wilder_all_losses(self):
        prices = [100.0 - i * 2 for i in range(16)]
        rsi = self._calculate_rsi_wilder(prices, 14)
        self.assertEqual(len(rsi), 2)
        self.assertEqual(rsi[0], 0.0)
        self.assertEqual(rsi[1], 0.0)

    def test_rsi_wilder_reference_series(self):
        # 16 standard textbook closing prices
        test_prices = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
        ]
        rsi = self._calculate_rsi_wilder(test_prices, 14)
        self.assertEqual(len(rsi), 2)
        # Standard initial RSI for this exact sequence is 70.46
        self.assertEqual(rsi[0], 70.46)
        # Second bar change is -0.28 (loss), Wilder smoothed RSI drops to 66.25
        self.assertAlmostEqual(rsi[1], 66.25, places=1)


if __name__ == "__main__":
    unittest.main()
