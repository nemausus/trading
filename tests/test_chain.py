"""
Unit tests for chain.py.

Run with:  python -m unittest tests/test_chain.py -v
"""

import unittest
from unittest.mock import patch

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import chain


class TestFetchOptionChain(unittest.TestCase):

    @patch("schwab_api.schwab_request")
    def test_fetch_option_chain_parsing(self, mock_schwab_request):
        mock_schwab_request.return_value = {
            "underlying": {"symbol": "AAPL", "last": 200.0, "change": 2.5, "percentChange": 1.26},
            "callExpDateMap": {
                "2026-08-21:50": {
                    "200.0": [
                        {
                            "symbol": "AAPL  271231C00200000",
                            "expirationDate": "2026-08-21T00:00:00.000+00:00",
                            "daysToExpiration": 50,
                            "strikePrice": 200.0,
                            "bid": 10.0,
                            "ask": 11.0,
                            "mark": 10.5,
                            "delta": 0.50,
                            "volatility": 25.0,
                            "totalVolume": 50,
                            "openInterest": 100,
                            "timeValue": 10.5,
                        }
                    ]
                }
            },
        }

        res = chain.fetch_option_chain("fake_token", "AAPL", "CALL")

        self.assertEqual(res["underlying"]["symbol"], "AAPL")
        self.assertEqual(res["underlying"]["price"], 200.0)
        self.assertEqual(len(res["chain"]), 1)

        opt = res["chain"][0]
        self.assertEqual(opt["symbol"], "AAPL  271231C00200000")
        self.assertEqual(opt["contractType"], "CALL")
        self.assertEqual(opt["strikePrice"], 200.0)
        self.assertEqual(opt["dte"], 50)
        self.assertEqual(opt["delta"], 0.50)
        self.assertAlmostEqual(opt["change"], 0.0)

    @patch("schwab_api.schwab_request")
    def test_fetch_option_chain_server_side_filtering(self, mock_schwab_request):
        mock_schwab_request.return_value = {
            "underlying": {"symbol": "AAPL", "last": 200.0},
            "callExpDateMap": {
                "2026-08-21:50": {
                    "200.0": [
                        {
                            "symbol": "C1",
                            "daysToExpiration": 5,
                            "delta": 0.20,
                            "strikePrice": 200.0,
                        },
                        {
                            "symbol": "C2",
                            "daysToExpiration": 30,
                            "delta": 0.25,
                            "strikePrice": 210.0,
                        },
                        {
                            "symbol": "C3",
                            "daysToExpiration": 45,
                            "delta": 0.50,
                            "strikePrice": 220.0,
                        },
                    ]
                }
            },
        }

        # Filter: min_dte=7, max_dte=60, min_delta=0.1, max_delta=0.3
        res = chain.fetch_option_chain(
            "fake_token", "AAPL", "CALL", min_dte=7, max_dte=60, min_delta=0.1, max_delta=0.3
        )

        self.assertEqual(res["totalContracts"], 3)
        self.assertEqual(len(res["chain"]), 1)
        self.assertEqual(res["chain"][0]["symbol"], "C2")

    def test_fetch_option_chain_validation_errors(self):
        """Verify ValueError is raised for negative DTE, out-of-range delta, or min > max."""
        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL", min_dte=-5)

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL", max_dte=5000)

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL", min_dte=60, max_dte=30)

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL", min_delta=-2.5)

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL", max_delta=1.5)

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL", min_delta=0.5, max_delta=0.2)

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "AAPL_WITH_EXCESSIVELY_LONG_SYMBOL_NAME_HERE")

        with self.assertRaises(ValueError):
            chain.fetch_option_chain("fake_token", "")

    def test_parse_exp_map_empty(self):
        self.assertEqual(chain._parse_exp_map({}, 200.0, "CALL"), [])
        self.assertEqual(chain._parse_exp_map(None, 200.0, "CALL"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
