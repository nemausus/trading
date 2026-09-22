"""
Unit tests for option_symbol.py.

Run with:  python -m pytest tests/test_option_symbol.py -v
"""
import datetime
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from option_symbol import OptionSymbol, _parse_expiration_date
import portfolio


# ---------------------------------------------------------------------------
# OptionSymbol
# ---------------------------------------------------------------------------

class TestOptionSymbol(unittest.TestCase):

    def test_parse_call(self):
        sym = OptionSymbol.parse_symbol('AAPL  271231C00295000')
        self.assertEqual(sym.underlying_symbol, 'AAPL')
        self.assertEqual(sym.contract_type, 'C')
        self.assertEqual(sym.strike_price, '295.00')
        self.assertEqual(sym.expiration_date, datetime.date(2027, 12, 31))

    def test_parse_put(self):
        sym = OptionSymbol.parse_symbol('NVDA  261219P00200000')
        self.assertEqual(sym.underlying_symbol, 'NVDA')
        self.assertEqual(sym.contract_type, 'P')
        self.assertEqual(sym.strike_price, '200.00')

    def test_parse_spx(self):
        # SPX symbols start with "SPX   " (6 chars)
        sym = OptionSymbol.parse_symbol('SPX   261219C05000000')
        self.assertEqual(sym.underlying_symbol, 'SPX')
        self.assertEqual(sym.contract_type, 'C')
        self.assertEqual(sym.strike_price, '5000.00')

    def test_parse_invalid_short(self):
        with self.assertRaises(ValueError):
            OptionSymbol.parse_symbol('AAPL')

    def test_dte_future(self):
        # expiration 30 days from today
        future = datetime.date.today() + datetime.timedelta(days=30)
        sym = OptionSymbol('AAPL', future, 'C', '200.00')
        self.assertEqual(sym.dte(ref_date=datetime.date.today()), 30)

    def test_dte_string_ref(self):
        future = datetime.date(2030, 1, 1)
        sym = OptionSymbol('AAPL', future, 'C', '200.00')
        self.assertEqual(sym.dte(ref_date='2029-12-01'), 31)

    def test_dte_expired(self):
        past = datetime.date.today() - datetime.timedelta(days=5)
        sym = OptionSymbol('AAPL', past, 'C', '200.00')
        self.assertEqual(sym.dte(ref_date=datetime.date.today()), -5)


# ---------------------------------------------------------------------------
# get_option_multiplier
# ---------------------------------------------------------------------------

class TestGetOptionMultiplier(unittest.TestCase):

    def test_equity(self):
        self.assertEqual(portfolio.get_option_multiplier('AAPL'), 1)

    def test_option(self):
        self.assertEqual(portfolio.get_option_multiplier('AAPL  271231C00295000'), 100)

    def test_four_char_equity(self):
        self.assertEqual(portfolio.get_option_multiplier('HOOD'), 1)

    def test_five_char(self):
        # 5-char symbols like "GOOGL" are equities — multiplier should be 1
        self.assertEqual(portfolio.get_option_multiplier('GOOGL'), 100)


# ---------------------------------------------------------------------------
# _parse_expiration_date
# ---------------------------------------------------------------------------

class TestParseExpirationDate(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(_parse_expiration_date('271231'),
                         datetime.date(2027, 12, 31))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            _parse_expiration_date('bad_date')


if __name__ == '__main__':
    unittest.main(verbosity=2)
