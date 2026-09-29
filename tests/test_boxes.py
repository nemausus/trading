"""
Unit tests for boxes.py.

Run with:  python -m unittest tests/test_boxes.py -v
"""

import unittest
from unittest.mock import patch

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import boxes


class TestBoxes(unittest.TestCase):

    @patch("boxes.schwab_api.get_option_chains")
    def test_fetch_spx_boxes_success(self, mock_get_chains):
        # Setup mock chain with 1 monthly SPX box spread:
        # Expiration: 2026-12-18, DTE: 60
        # Lower strike: 5000 (Call mark: 120, Put mark: 20, OI: 100)
        # Higher strike: 5100 (Call mark: 40, Put mark: 45, OI: 100)
        # size = 100
        # net_credit = (120 - 40) + (45 - 20) = 80 + 25 = 105. Wait, net credit > size gives negative rate or net_credit = 98 gives positive rate.
        # Let's say: lower Call 120, higher Call 40 -> 80.
        # higher Put 38, lower Put 20 -> 18.
        # net_credit = 80 + 18 = 98.
        mock_get_chains.return_value = {
            "callExpDateMap": {
                "2026-12-18:60": {
                    "5000.0": [
                        {
                            "symbol": "SPX   261218C05000000",
                            "expirationDate": "2026-12-18T00:00:00.000+00:00",
                            "daysToExpiration": 60,
                            "strikePrice": 5000.0,
                            "bid": 119.0,
                            "ask": 121.0,
                            "mark": 120.0,
                            "openInterest": 100,
                        }
                    ],
                    "5100.0": [
                        {
                            "symbol": "SPX   261218C05100000",
                            "expirationDate": "2026-12-18T00:00:00.000+00:00",
                            "daysToExpiration": 60,
                            "strikePrice": 5100.0,
                            "bid": 39.0,
                            "ask": 41.0,
                            "mark": 40.0,
                            "openInterest": 150,
                        }
                    ],
                }
            },
            "putExpDateMap": {
                "2026-12-18:60": {
                    "5000.0": [
                        {
                            "symbol": "SPX   261218P05000000",
                            "expirationDate": "2026-12-18T00:00:00.000+00:00",
                            "daysToExpiration": 60,
                            "strikePrice": 5000.0,
                            "bid": 19.0,
                            "ask": 21.0,
                            "mark": 20.0,
                            "openInterest": 120,
                        }
                    ],
                    "5100.0": [
                        {
                            "symbol": "SPX   261218P05100000",
                            "expirationDate": "2026-12-18T00:00:00.000+00:00",
                            "daysToExpiration": 60,
                            "strikePrice": 5100.0,
                            "bid": 37.0,
                            "ask": 39.0,
                            "mark": 38.0,
                            "openInterest": 130,
                        }
                    ],
                }
            },
        }

        res = boxes.fetch_spx_boxes("fake_token", "2026-10-01", "2026-12-31", sizes=[100])

        self.assertEqual(len(res), 1)
        b = res[0]
        self.assertEqual(b["expirationDate"], "2026-12-18")
        self.assertEqual(b["dte"], 60)
        self.assertEqual(b["btoPut"], 5000.0)
        self.assertEqual(b["stoPut"], 5100.0)
        self.assertEqual(b["stoCall"], 5000.0)
        self.assertEqual(b["btoCall"], 5100.0)
        self.assertEqual(b["size"], 100)
        self.assertAlmostEqual(b["netCredit"], 98.0)
        self.assertEqual(b["liquidity"], 100 + 150 + 120 + 130)
        expected_rate = ((100 - 98.0) / 98.0) * (365.0 / 60) * 100.0
        self.assertAlmostEqual(b["rate"], expected_rate)

    @patch("boxes.schwab_api.get_option_chains")
    def test_spxw_weeklies_excluded(self, mock_get_chains):
        # Weekly contract symbol SPXW should be excluded
        mock_get_chains.return_value = {
            "callExpDateMap": {
                "2026-12-18:60": {
                    "5000.0": [
                        {
                            "symbol": "SPXW  261218C05000000",
                            "expirationDate": "2026-12-18T00:00:00.000+00:00",
                            "daysToExpiration": 60,
                            "strikePrice": 5000.0,
                            "bid": 119.0,
                            "ask": 121.0,
                            "mark": 120.0,
                            "openInterest": 100,
                        }
                    ],
                }
            },
            "putExpDateMap": {},
        }
        res = boxes.fetch_spx_boxes("fake_token", None, None, sizes=[100])
        self.assertEqual(len(res), 0)

    @patch("boxes.schwab_api.get_option_chains")
    def test_zero_open_interest_excluded(self, mock_get_chains):
        mock_get_chains.return_value = {
            "callExpDateMap": {
                "2026-12-18:60": {
                    "5000.0": [
                        {
                            "symbol": "SPX   261218C05000000",
                            "expirationDate": "2026-12-18T00:00:00.000+00:00",
                            "daysToExpiration": 60,
                            "strikePrice": 5000.0,
                            "mark": 120.0,
                            "openInterest": 0,
                        }
                    ],
                }
            },
            "putExpDateMap": {},
        }
        res = boxes.fetch_spx_boxes("fake_token", None, None, sizes=[100])
        self.assertEqual(len(res), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
