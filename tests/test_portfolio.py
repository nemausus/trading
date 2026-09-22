"""
Unit tests for portfolio.py.

Run with:  python -m pytest tests/test_portfolio.py -v
"""
import datetime
import unittest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import portfolio as sp
from option_symbol import OptionSymbol


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------

def _make_equity_pos(symbol, long_qty=0, short_qty=0,
                     avg_price=100.0, market_value=None,
                     long_pl=0.0, short_pl=None):
    """Return a raw position dict as the Schwab API returns."""
    if market_value is None:
        market_value = avg_price * (long_qty - short_qty)
    return {
        'longQuantity': float(long_qty),
        'shortQuantity': float(short_qty),
        'averagePrice': avg_price,
        'marketValue': market_value,
        'longOpenProfitLoss': long_pl,
        'shortOpenProfitLoss': short_pl,
        'instrument': {'symbol': symbol, 'assetType': 'EQUITY'},
    }


def _make_option_pos(symbol, long_qty=0, short_qty=0,
                     avg_price=5.0, market_value=None,
                     long_pl=0.0, short_pl=None):
    if market_value is None:
        market_value = avg_price * (long_qty - short_qty) * 100
    return {
        'longQuantity': float(long_qty),
        'shortQuantity': float(short_qty),
        'averagePrice': avg_price,
        'marketValue': market_value,
        'longOpenProfitLoss': long_pl,
        'shortOpenProfitLoss': short_pl,
        'instrument': {'symbol': symbol, 'assetType': 'OPTION'},
    }


def _make_account(acc_num, positions,
                  cash=1000.0, net=200000.0, margin=0.0,
                  maint=0.0, equity=200000.0):
    return {
        'securitiesAccount': {
            'accountNumber': acc_num,
            'positions': positions,
            'currentBalances': {
                'cashBalance': cash,
                'liquidationValue': net,
                'marginBalance': margin,
                'maintenanceRequirement': maint,
                'equity': equity,
            }
        }
    }


# ---------------------------------------------------------------------------
# process_accounts_data — positions parsing
# ---------------------------------------------------------------------------

class TestProcessAccountsPositions(unittest.TestCase):
    """Tests that raw Schwab positions are correctly parsed."""

    def _run(self, accounts_json, quotes=None):
        """Helper: run process_accounts_data with mocked network calls."""
        with patch.object(sp, 'fetch_quotes', return_value=quotes or {}), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_single_equity_position(self):
        pos = _make_equity_pos('AAPL', long_qty=100, avg_price=150.0,
                               market_value=17000.0, long_pl=2000.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account])

        positions = result['positions']
        self.assertEqual(len(positions), 1)
        p = positions[0]
        self.assertEqual(p['symbol'], 'AAPL')
        self.assertEqual(p['quantity'], 100.0)
        self.assertAlmostEqual(p['cost/share'], 150.0)
        # cost = marketValue - P/L = 17000 - 2000 = 15000
        self.assertAlmostEqual(p['cost'], 15000.0)
        self.assertAlmostEqual(p['P/L'], 2000.0)
        # P/L% = 2000 / 15000 * 100
        self.assertAlmostEqual(p['P/L%'], 2000 / 15000 * 100)
        self.assertEqual(p['dte'], -1)   # equity has no DTE
        self.assertEqual(p['delta'], 0.0)
        self.assertEqual(p['mpr'], 0.0)

    def test_short_option_position(self):
        # Short call: shortQuantity=1, shortOpenProfitLoss=50 (gain)
        sym = 'AAPL  271231C00295000'
        pos = _make_option_pos(sym, short_qty=1, avg_price=5.0,
                               market_value=-400.0, short_pl=100.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account])

        p = result['positions'][0]
        self.assertEqual(p['quantity'], -1.0)   # short
        self.assertAlmostEqual(p['P/L'], 100.0)
        self.assertGreaterEqual(p['dte'], 0)

    def test_no_positions_account_skipped(self):
        account = {'securitiesAccount': {'accountNumber': 'ACC1', 'positions': [],
                   'currentBalances': {'cashBalance': 0, 'liquidationValue': 0,
                   'marginBalance': 0, 'maintenanceRequirement': 0, 'equity': 0}}}
        result = self._run([account])
        self.assertEqual(result['positions'], [])
        self.assertEqual(len(result['summaries']), 1)

    def test_missing_account_number_skipped(self):
        account = {'securitiesAccount': {'positions': []}}
        result = self._run([account])
        self.assertEqual(result['summaries'], [])

    def test_value_per_share_zero_quantity(self):
        """qty=0 edge case — should not divide by zero."""
        pos = _make_equity_pos('CASH', long_qty=0, market_value=0.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account])
        p = result['positions'][0]
        self.assertEqual(p['value/share'], 0.0)


# ---------------------------------------------------------------------------
# process_accounts_data — SPX box loan grouping
# ---------------------------------------------------------------------------

class TestSPXBoxLoan(unittest.TestCase):

    def _run(self, accounts_json):
        with patch.object(sp, 'fetch_quotes', return_value={}), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_spx_positions_grouped(self):
        """Two SPX legs on the same expiry should be merged into one position."""
        long_leg  = _make_option_pos('SPX   261219C05000000', long_qty=1,
                                     market_value=10000.0, long_pl=500.0)
        short_leg = _make_option_pos('SPX   261219P05000000', short_qty=1,
                                     market_value=-8000.0, short_pl=200.0)
        account = _make_account('ACC1', [long_leg, short_leg])
        result = self._run([account])

        # Both share the same 12-char prefix 'SPX   261219'
        spx_pos = [p for p in result['positions'] if p['symbol'].startswith('SPX')]
        self.assertEqual(len(spx_pos), 1)
        self.assertEqual(spx_pos[0]['quantity'], 1)

    def test_box_loan_rounded_to_10k(self):
        """Box loan should round group cost to nearest $10,000."""
        long_leg = _make_option_pos('SPX   261219C05000000', long_qty=1,
                                    market_value=10000.0, long_pl=500.0)
        account = _make_account('ACC1', [long_leg], equity=100000.0)
        result = self._run([account])

        summary = result['summaries'][0]
        self.assertAlmostEqual(summary['BOX'], 10000.0)

    def test_box_loan_in_total_loan(self):
        long_leg = _make_option_pos('SPX   261219C05000000', long_qty=1,
                                    market_value=10000.0, long_pl=500.0)
        account = _make_account('ACC1', [long_leg], margin=5000.0)
        result = self._run([account])

        s = result['summaries'][0]
        self.assertAlmostEqual(s['Total Loan'], s['Margin'] + s['BOX'] + s['CSP'])


# ---------------------------------------------------------------------------
# process_accounts_data — CSP calculation
# ---------------------------------------------------------------------------

class TestCSP(unittest.TestCase):

    def _run(self, accounts_json):
        with patch.object(sp, 'fetch_quotes', return_value={}), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_short_put_csp(self):
        sym = 'NVDA  261219P00200000'
        pos = _make_option_pos(sym, short_qty=2, avg_price=5.0,
                               market_value=-1000.0, short_pl=0.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account])

        s = result['summaries'][0]
        self.assertAlmostEqual(s['CSP'], -40000.0)

    def test_long_put_not_counted(self):
        sym = 'NVDA  261219P00200000'
        pos = _make_option_pos(sym, long_qty=1, avg_price=5.0,
                               market_value=500.0, long_pl=0.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account])

        s = result['summaries'][0]
        self.assertAlmostEqual(s['CSP'], 0.0)

    def test_short_call_not_counted_as_csp(self):
        sym = 'AAPL  271231C00295000'
        pos = _make_option_pos(sym, short_qty=1, avg_price=5.0,
                               market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account])

        s = result['summaries'][0]
        self.assertAlmostEqual(s['CSP'], 0.0)


# ---------------------------------------------------------------------------
# process_accounts_data — Todo / uncovered longs
# ---------------------------------------------------------------------------

class TestTodoList(unittest.TestCase):

    def _run(self, accounts_json):
        with patch.object(sp, 'fetch_quotes', return_value={}), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_uncovered_stock(self):
        """100 shares of AAPL, no covered call → Todo should mention AAPL."""
        equity = _make_equity_pos('AAPL', long_qty=100, avg_price=200.0,
                                  market_value=20000.0, long_pl=0.0)
        account = _make_account('ACC1', [equity])
        result = self._run([account])

        todo = result['summaries'][0]['Todo']
        self.assertIn('AAPL', todo)
        self.assertIn('1x', todo)

    def test_covered_stock(self):
        """100 shares of AAPL + 1 short call → fully covered, no Todo."""
        equity = _make_equity_pos('AAPL', long_qty=100, avg_price=200.0,
                                  market_value=20000.0)
        call = _make_option_pos('AAPL  271231C00295000', short_qty=1,
                                market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [equity, call])
        result = self._run([account])

        todo = result['summaries'][0]['Todo']
        self.assertNotIn('AAPL', todo)

    def test_partially_covered(self):
        """200 shares of AAPL + 1 short call → 1 contract still uncovered."""
        equity = _make_equity_pos('AAPL', long_qty=200, avg_price=200.0,
                                  market_value=40000.0)
        call = _make_option_pos('AAPL  271231C00295000', short_qty=1,
                                market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [equity, call])
        result = self._run([account])

        todo = result['summaries'][0]['Todo']
        self.assertIn('AAPL', todo)
        self.assertIn('1x', todo)

    def test_excluded_tickers_not_in_todo(self):
        """QQQM, VTI, SNOW, SPX should never appear in the Todo list."""
        for ticker in ('QQQM', 'VTI', 'SNOW'):
            equity = _make_equity_pos(ticker, long_qty=100, avg_price=100.0,
                                      market_value=10000.0)
            account = _make_account('ACC1', [equity])
            result = self._run([account])
            todo = result['summaries'][0]['Todo']
            self.assertNotIn(ticker, todo, f"{ticker} should be excluded from Todo")

    def test_long_call_counted_as_long(self):
        """A long call option (1 contract) counts as 1 unit toward longs."""
        call = _make_option_pos('AAPL  271231C00295000', long_qty=1,
                                market_value=500.0, long_pl=0.0)
        account = _make_account('ACC1', [call])
        result = self._run([account])

        todo = result['summaries'][0]['Todo']
        self.assertIn('AAPL', todo)
        self.assertIn('1x', todo)


# ---------------------------------------------------------------------------
# process_accounts_data — MPR and delta via quotes
# ---------------------------------------------------------------------------

class TestMPRAndDelta(unittest.TestCase):

    def _make_quotes(self, symbol, bid, underlying, delta):
        return {symbol: {'quote': {
            'bidPrice': bid,
            'underlyingPrice': underlying,
            'delta': delta,
        }}}

    def _run(self, accounts_json, quotes):
        with patch.object(sp, 'fetch_quotes', return_value=quotes), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_delta_set_from_quotes(self):
        sym = 'AAPL  271231C00295000'
        pos = _make_option_pos(sym, short_qty=1, market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [pos])
        quotes = self._make_quotes(sym, bid=6.0, underlying=290.0, delta=0.35)
        result = self._run([account], quotes)

        p = result['positions'][0]
        self.assertAlmostEqual(p['delta'], 0.35)

    def test_mpr_call_otm(self):
        """OTM call: timeValue = bid (all extrinsic), MPR = bid*3000/dte/underlying."""
        sym = 'AAPL  271231C00295000'
        pos = _make_option_pos(sym, short_qty=1, market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [pos])

        quotes = self._make_quotes(sym, bid=5.0, underlying=280.0, delta=0.35)
        result = self._run([account], quotes)

        p = result['positions'][0]
        opt = OptionSymbol.parse_symbol(sym)
        dte = opt.dte()
        if dte > 0:
            expected_mpr = (5.0 * 3000.0) / dte / 280.0
            self.assertAlmostEqual(p['mpr'], expected_mpr, places=4)

    def test_mpr_itm_call_removes_intrinsic(self):
        """ITM call: intrinsic = underlying - strike is subtracted from bid."""
        sym = 'AAPL  271231C00200000'  # strike 200, underlying 250 → ITM
        pos = _make_option_pos(sym, short_qty=1, market_value=-5000.0, short_pl=0.0)
        account = _make_account('ACC1', [pos])

        quotes = self._make_quotes(sym, bid=55.0, underlying=250.0, delta=0.9)
        result = self._run([account], quotes)

        p = result['positions'][0]
        opt = OptionSymbol.parse_symbol(sym)
        dte = opt.dte()
        if dte > 0:
            expected_mpr = (5.0 * 3000.0) / dte / 250.0
            self.assertAlmostEqual(p['mpr'], expected_mpr, places=4)

    def test_equity_no_mpr(self):
        pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        account = _make_account('ACC1', [pos])
        quotes = {'AAPL': {'quote': {'bidPrice': 200.0, 'delta': 0.0}}}
        result = self._run([account], quotes)

        p = result['positions'][0]
        self.assertEqual(p['mpr'], 0.0)

    def test_no_mpr_when_dte_zero(self):
        """MPR should be 0 when DTE is 0 or negative (avoid division by zero)."""
        today = datetime.datetime.now(sp.SCHWAB_TZ).date()
        exp_str = today.strftime('%y%m%d')
        sym = f'AAPL  {exp_str}C00200000'
        pos = _make_option_pos(sym, short_qty=1, market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [pos])

        quotes = self._make_quotes(sym, bid=5.0, underlying=200.0, delta=0.5)
        result = self._run([account], quotes)

        p = result['positions'][0]
        self.assertEqual(p['mpr'], 0.0)


# ---------------------------------------------------------------------------
# process_accounts_data — order merging
# ---------------------------------------------------------------------------

class TestOrderMerging(unittest.TestCase):

    def _run(self, accounts_json, active_orders):
        with patch.object(sp, 'fetch_quotes', return_value={}), \
             patch.object(sp, 'fetch_active_orders', return_value=active_orders):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_order_fields(self):
        pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        account = _make_account('ACC1', [pos])
        orders = [{'accountNumber': 'ACC1', 'symbol': 'AAPL',
                   'type': 'STC', 'quantity': 1.0, 'price': 205.0,
                   'status': 'WORKING', 'duration': 'GTC', 'orderType': 'LIMIT'}]
        result = self._run([account], orders)

        self.assertEqual(len(result['orders']), 1)
        o = result['orders'][0]
        self.assertEqual(o['type'], 'STC')
        self.assertEqual(o['price'], 205.0)

    def test_order_with_no_matching_position(self):
        """Orders for symbols not in positions should still appear in orders list."""
        account = _make_account('ACC1', [])
        orders = [{'accountNumber': 'ACC1', 'symbol': 'TSLA',
                   'type': 'BTO', 'quantity': 1.0, 'price': 300.0,
                   'status': 'WORKING', 'duration': 'GTC', 'orderType': 'LIMIT'}]
        result = self._run([account], orders)

        self.assertEqual(len(result['orders']), 1)
        o = result['orders'][0]
        self.assertEqual(o['symbol'], 'TSLA')
        self.assertEqual(o['quantity'], 1.0)

    def test_no_orders(self):
        pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        account = _make_account('ACC1', [pos])
        result = self._run([account], [])
        self.assertEqual(result['orders'], [])


# ---------------------------------------------------------------------------
# process_accounts_data — summary fields
# ---------------------------------------------------------------------------

class TestAccountSummary(unittest.TestCase):

    def _run(self, accounts_json):
        with patch.object(sp, 'fetch_quotes', return_value={}), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_summary_fields_present(self):
        pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        account = _make_account('ACC1', [pos], cash=500.0, net=20500.0,
                                margin=0.0, maint=0.0, equity=20500.0)
        result = self._run([account])
        s = result['summaries'][0]

        for field in ('accountNumber', 'Short P/L', 'Short Value', 'Cash',
                      'Total', 'Net', 'Margin', 'CSP', 'BOX', 'MaintReq',
                      'Risk', 'Total Loan', 'Todo'):
            self.assertIn(field, s, f"Missing summary field: {field}")

    def test_risk_formula(self):
        """Risk = 100 + 2250 * box_loan / equity / 7."""
        spx_pos = _make_option_pos('SPX   261219C05000000', long_qty=1,
                                   market_value=10000.0, long_pl=0.0)
        account = _make_account('ACC1', [spx_pos], equity=100000.0)
        result = self._run([account])
        s = result['summaries'][0]

        expected_risk = 100.0 + (2250.0 * 10000.0) / 100000.0 / 7.0
        self.assertAlmostEqual(s['Risk'], expected_risk, places=4)

    def test_risk_no_box_loan(self):
        """With no SPX positions, risk should be exactly 100.0."""
        pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        account = _make_account('ACC1', [pos], equity=20000.0)
        result = self._run([account])
        self.assertAlmostEqual(result['summaries'][0]['Risk'], 100.0)

    def test_cash_from_balances(self):
        pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        account = _make_account('ACC1', [pos], cash=1234.56)
        result = self._run([account])
        self.assertAlmostEqual(result['summaries'][0]['Cash'], 1234.56)

    def test_todo_actions_sto_and_btc(self):
        """Test STO rule for uncovered stocks and BTC rule for sold calls (P/L% >= 60% or delta < 0.10)."""
        equity_pos = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        winning_call = _make_option_pos('AAPL  271231C00295000', short_qty=1, avg_price=5.0,
                                        market_value=-100.0, short_pl=400.0)
        low_delta_call = _make_option_pos('NVDA  271231C00300000', short_qty=1, avg_price=5.0,
                                          market_value=-400.0, short_pl=100.0)

        account = _make_account('ACC1', [equity_pos, winning_call, low_delta_call])

        quotes = {
            'AAPL': {'quote': {'markPercentChange': 1.25}},
            'NVDA': {'quote': {'markPercentChange': -0.50}},
            'AAPL  271231C00295000': {'quote': {'delta': 0.20}},
            'NVDA  271231C00300000': {'quote': {'delta': 0.05}},
        }

        with patch.object(sp, 'fetch_quotes', return_value=quotes), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            result = sp.process_accounts_data([account], 'fake_token')

        summary = result['summaries'][0]
        todo_text = summary['Todo']

        self.assertIn('BTC 1x AAPL  271231C00295000 (0.20,', todo_text)
        self.assertIn('BTC 1x NVDA  271231C00300000 (0.05,', todo_text)

    def test_todo_actions_uncovered_sto(self):
        """Test STO rule triggers for uncovered stock position."""
        msft_pos = _make_equity_pos('MSFT', long_qty=200, market_value=40000.0)
        account = _make_account('ACC1', [msft_pos])

        quotes = {'MSFT': {'quote': {'markPercentChange': 2.50}}}

        with patch.object(sp, 'fetch_quotes', return_value=quotes), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            result = sp.process_accounts_data([account], 'fake_token')

        summary = result['summaries'][0]
        self.assertEqual(summary['Todo'], 'STO 2x MSFT (+2.50%)')

    def test_todo_actions_rollout(self):
        """Test ROLLOUT rule triggers when sold call delta > 0.50."""
        short_call = _make_option_pos('AAPL  271231C00295000', short_qty=1, avg_price=5.0,
                                       market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [short_call])

        quotes = {
            'AAPL  271231C00295000': {
                'quote': {
                    'delta': 0.65,
                    'bidPrice': 5.0,
                    'underlyingPrice': 300.0
                }
            }
        }

        with patch.object(sp, 'fetch_quotes', return_value=quotes), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            result = sp.process_accounts_data([account], 'fake_token')

        summary = result['summaries'][0]
        self.assertIn('ROLLOUT 1x AAPL  271231C00295000 (0.65,', summary['Todo'])


# ---------------------------------------------------------------------------
# sort order of positions
# ---------------------------------------------------------------------------

class TestPositionSort(unittest.TestCase):

    def _run(self, accounts_json):
        with patch.object(sp, 'fetch_quotes', return_value={}), \
             patch.object(sp, 'fetch_active_orders', return_value=[]):
            return sp.process_accounts_data(accounts_json, 'fake_token')

    def test_equities_before_options_in_sort(self):
        """Equities have dte=-1, options have dte>0; positions sorted by (acc, dte, sym)."""
        equity = _make_equity_pos('AAPL', long_qty=100, market_value=20000.0)
        call = _make_option_pos('AAPL  271231C00295000', short_qty=1,
                                market_value=-500.0, short_pl=0.0)
        account = _make_account('ACC1', [equity, call])
        result = self._run([account])

        positions = result['positions']
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0]['symbol'], 'AAPL')
        self.assertEqual(positions[1]['symbol'], 'AAPL  271231C00295000')


# ---------------------------------------------------------------------------
# _enrich_quotes
# ---------------------------------------------------------------------------

class TestEnrichQuotes(unittest.TestCase):

    def test_enrich_quotes_mark_percent_change(self):
        stock_pos = {'symbol': 'AAPL', 'quantity': 100, 'cost': 10000.0, 'P/L': 500.0}
        option_pos = {'symbol': 'AAPL  271231C00295000', 'quantity': -1, 'cost': -500.0, 'P/L': 100.0}
        positions = [stock_pos, option_pos]

        quotes = {
            'AAPL': {
                'quote': {
                    'delta': 0.0,
                    'markPercentChange': 1.25
                }
            },
            'AAPL  271231C00295000': {
                'quote': {
                    'delta': 0.45,
                    'bidPrice': 5.0,
                    'underlyingPrice': 290.0,
                    'markPercentChange': 0.50
                }
            }
        }

        sp._enrich_quotes(positions, quotes)

        self.assertIn('markPercentChange', stock_pos)
        self.assertEqual(stock_pos['markPercentChange'], 1.25)

        self.assertIn('markPercentChange', option_pos)
        self.assertEqual(option_pos['markPercentChange'], 0.50)

    def test_enrich_quotes_missing_quote_stock(self):
        stock_pos = {'symbol': 'MSFT', 'quantity': 50, 'cost': 5000.0, 'P/L': 0.0}
        sp._enrich_quotes([stock_pos], {})

        self.assertIn('markPercentChange', stock_pos)
        self.assertEqual(stock_pos['markPercentChange'], 0.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
