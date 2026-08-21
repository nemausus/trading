"""
Unit tests for realized_pl.py module.
"""

import unittest
import realized_pl


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


if __name__ == '__main__':
    unittest.main()

