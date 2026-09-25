"""
Unit tests for realized.py module.
"""

import unittest
import realized as realized_pl


class TestRealizedPL(unittest.TestCase):

    def test_normalize_transactions_empty(self):
        self.assertEqual(realized_pl.normalize_transactions([]), [])

    def test_normalize_transactions_filtering_and_fields(self):
        txns = [
            {
                'type': 'TRADE',
                'netAmount': -1000.0,
                'time': '2026-06-01T12:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '123'},
                        'amount': 100.0,
                        'cost': 1000.0,
                        'price': 10.0,
                    }
                ]
            },
            {
                'type': 'DIVIDEND_OR_INTEREST',
                'netAmount': -15.5,
                'time': '2026-06-02T12:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': None,
                        'instrument': {'symbol': 'MARGIN', 'instrumentId': '456'},
                        'amount': 1.0,
                        'cost': 15.5,
                        'price': 15.5,
                    }
                ]
            },
            {
                # SPX transfers excluded
                'type': 'TRADE',
                'netAmount': -500.0,
                'time': '2026-06-03T12:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'instrument': {'symbol': 'SPX   261219C05000000', 'instrumentId': '789'},
                        'amount': 1.0,
                    }
                ]
            }
        ]

        normalized = realized_pl.normalize_transactions(txns)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]['symbol'], 'AAPL')
        self.assertEqual(normalized[0]['sl'], 'long')
        self.assertEqual(normalized[1]['positionEffect'], 'INTEREST')

    def test_calculate_realized_pl_fifo(self):
        txns = [
            {
                'type': 'TRADE',
                'netAmount': -2000.0,
                'time': '2026-01-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': 100.0,
                        'cost': 2000.0,
                        'price': 20.0,
                    }
                ]
            },
            {
                'type': 'TRADE',
                'netAmount': 2500.0,
                'time': '2026-02-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'CLOSING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': -100.0,
                        'cost': 2500.0,
                        'price': 25.0,
                    }
                ]
            }
        ]

        result = realized_pl.calculate_realized_pl(txns)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['symbol'], 'AAPL')
        self.assertEqual(result[0]['amount'], 100.0)
        self.assertEqual(result[0]['P/L'], 500.0)

    def test_calculate_realized_pl_dict_input(self):
        txns_dict = {'acc_hash_1': [
            {
                'type': 'TRADE',
                'netAmount': -2000.0,
                'time': '2026-01-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': 100.0,
                        'cost': 2000.0,
                        'price': 20.0,
                    }
                ]
            },
            {
                'type': 'TRADE',
                'netAmount': 2500.0,
                'time': '2026-02-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'CLOSING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': -100.0,
                        'cost': 2500.0,
                        'price': 25.0,
                    }
                ]
            }
        ]}
        txns = [txn for sublist in txns_dict.values() for txn in sublist]
        result = realized_pl.calculate_realized_pl(txns)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['symbol'], 'AAPL')
        self.assertEqual(result[0]['P/L'], 500.0)

    def test_calculate_realized_pl_with_status(self):
        txns = [
            {
                'activityId': 'act_open_1',
                'type': 'TRADE',
                'netAmount': -2000.0,
                'time': '2026-01-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': 100.0,
                        'cost': 2000.0,
                        'price': 20.0,
                    }
                ]
            },
            {
                'activityId': 'act_close_1',
                'type': 'TRADE',
                'netAmount': 2500.0,
                'time': '2026-02-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'CLOSING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': -100.0,
                        'cost': 2500.0,
                        'price': 25.0,
                    }
                ]
            }
        ]
        result, processed_ids = realized_pl.calculate_realized_pl_with_status(txns)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['symbol'], 'AAPL')
        self.assertEqual(result[0]['P/L'], 500.0)
        self.assertEqual(processed_ids, {'act_open_1', 'act_close_1'})

    def test_calculate_realized_pl_with_integer_activity_ids(self):
        txns = [
            {
                'activityId': 1001,
                'type': 'TRADE',
                'netAmount': -2000.0,
                'time': '2026-01-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': 100.0,
                        'cost': 2000.0,
                        'price': 20.0,
                    }
                ]
            },
            {
                'activityId': 1002,
                'type': 'TRADE',
                'netAmount': 2500.0,
                'time': '2026-02-01T10:00:00-07:00',
                'accountNumber': 'ACC1',
                'transferItems': [
                    {
                        'positionEffect': 'CLOSING',
                        'instrument': {'symbol': 'AAPL', 'instrumentId': '1'},
                        'amount': -100.0,
                        'cost': 2500.0,
                        'price': 25.0,
                    }
                ]
            }
        ]
        result, processed_ids = realized_pl.calculate_realized_pl_with_status(txns)
        self.assertEqual(len(result), 1)
        self.assertEqual(processed_ids, {'1001', '1002'})
        self.assertEqual(result[0]['id'], 'realized_1001_1002')

    def test_load_csv_realized_pl_missing_file(self):
        records = realized_pl.load_csv_realized_pl('/non/existent/path.csv')
        self.assertEqual(records, [])

    def test_format_csv_symbol(self):
        self.assertEqual(realized_pl._format_csv_symbol('META 09/11/2026 640.00 C'), 'META  260911C00640000')
        self.assertEqual(realized_pl._format_csv_symbol('IBIT 09/11/2026 39.00 C'), 'IBIT  260911C00039000')
        self.assertEqual(realized_pl._format_csv_symbol('NVDA 02/13/2026 197.50 C'), 'NVDA  260213C00197500')
        self.assertEqual(realized_pl._format_csv_symbol('QQQ'), 'QQQ')
        self.assertEqual(realized_pl._format_csv_symbol(''), '')

    def test_load_csv_realized_pl_valid(self):
        import tempfile
        csv_content = (
            "Realized Gain/Loss - Lot Details for Roth_Contributory_IRA as of Fri Aug 21 01:48:02 EDT 2026\n"
            "Symbol,Name,Closed Date,Opened Date,Quantity,Proceeds Per Share,Cost Per Share,Proceeds,Cost Basis (CB),Gain/Loss ($)\n"
            'IBIT 09/11/2026 39.00 C,CALL ISHR BITCOIN TR,08/21/2026,08/21/2026,4,$0.36,$2.81,$145.34,"$1,122.65",-$977.31\n'
        )
        with tempfile.NamedTemporaryFile('w+', suffix='.csv', delete=False) as tmp:
            tmp.write(csv_content)
            tmp.flush()
            tmp_path = tmp.name

        try:
            records = realized_pl.load_csv_realized_pl(tmp_path, account_number='TEST_ACC')
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['accountNumber'], 'TEST_ACC')
            self.assertEqual(records[0]['symbol'], 'IBIT  260911C00039000')
            self.assertEqual(records[0]['buy_date'], '2026-08-21')
            self.assertEqual(records[0]['sell_date'], '2026-08-21')
            self.assertEqual(records[0]['amount'], 4.0)
            self.assertEqual(records[0]['buy_price'], 2.81)
            self.assertEqual(records[0]['sell_price'], 0.36)
            self.assertEqual(records[0]['P/L'], -977.31)
        finally:
            import os
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_load_csv_realized_pl_default_path(self):
        records = realized_pl.load_csv_realized_pl()
        self.assertIsInstance(records, list)


    def test_categorize_realized_trade_stock(self):
        from firestore_db import _categorize_realized_trade
        self.assertEqual(_categorize_realized_trade({'symbol': 'QQQ', 'buy_price': 400.0, 'sell_price': 420.0, 'P/L': 2000.0}), 'Stock')
        self.assertEqual(_categorize_realized_trade({'symbol': 'SPY', 'buy_price': 500.0, 'sell_price': 480.0, 'P/L': -200.0}), 'Stock')
        self.assertEqual(_categorize_realized_trade({'symbol': 'MARGIN INTEREST', 'P/L': -15.0}), 'Margin Interest')

    def test_categorize_realized_trade_call_short(self):
        from firestore_db import _categorize_realized_trade
        self.assertEqual(_categorize_realized_trade({
            'symbol': 'MSFT  261002C00515000',
            'buy_price': 8.78,
            'sell_price': 2.32,
            'P/L': 644.66
        }), 'Call Short')
        self.assertEqual(_categorize_realized_trade({
            'symbol': 'META  260925C00635000',
            'buy_price': 7.30,
            'sell_price': 41.10,
            'P/L': -6762.69
        }), 'Call Short')

    def test_categorize_realized_trade_call_long(self):
        from firestore_db import _categorize_realized_trade
        self.assertEqual(_categorize_realized_trade({
            'symbol': 'BE    261016C00250000',
            'buy_price': 27.50,
            'sell_price': 35.00,
            'P/L': 748.61
        }), 'Call Long')
        self.assertEqual(_categorize_realized_trade({
            'symbol': 'NVDA  260821C00210000',
            'buy_price': 16.81,
            'sell_price': 7.59,
            'P/L': -3685.37
        }), 'Call Long')

    def test_categorize_realized_trade_put_short(self):
        from firestore_db import _categorize_realized_trade
        self.assertEqual(_categorize_realized_trade({
            'symbol': 'QQQ   260717P00708000',
            'buy_price': 13.10,
            'sell_price': 0.00,
            'P/L': 1309.31
        }), 'Put Short')

    def test_categorize_realized_trade_put_long(self):
        from firestore_db import _categorize_realized_trade
        self.assertEqual(_categorize_realized_trade({
            'symbol': 'NVDA  260123P00175000',
            'buy_price': 1.72,
            'sell_price': 1.84,
            'P/L': 32.03
        }), 'Put Long')

    def test_categorize_realized_trade_with_explicit_sl(self):
        from firestore_db import _categorize_realized_trade
        self.assertEqual(_categorize_realized_trade({'symbol': 'AAPL  261231C00200000', 'sl': 'short'}), 'Call Short')
        self.assertEqual(_categorize_realized_trade({'symbol': 'AAPL  261231C00200000', 'sl': 'long'}), 'Call Long')
        self.assertEqual(_categorize_realized_trade({'symbol': 'AAPL  261231P00200000', 'sl': 'short'}), 'Put Short')
        self.assertEqual(_categorize_realized_trade({'symbol': 'AAPL  261231P00200000', 'sl': 'long'}), 'Put Long')


if __name__ == '__main__':
    unittest.main()


