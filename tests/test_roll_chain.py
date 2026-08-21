"""
Unit tests for roll_chain.py module.
"""

import unittest
import roll_chain


class TestRollChain(unittest.TestCase):

    def test_extract_underlying_symbol(self):
        self.assertEqual(roll_chain.extract_underlying_symbol('IBIT  261002C00040000'), 'IBIT')
        self.assertEqual(roll_chain.extract_underlying_symbol('META 09/11/2026 640.00 C'), 'META')
        self.assertEqual(roll_chain.extract_underlying_symbol('AAPL'), 'AAPL')
        self.assertEqual(roll_chain.extract_underlying_symbol(''), '')

    def test_filter_transactions_by_underlying(self):
        txns = [
            {
                'activityId': '1',
                'transferItems': [
                    {
                        'instrument': {
                            'assetType': 'OPTION',
                            'underlyingSymbol': 'IBIT',
                            'symbol': 'IBIT  260911C00039000'
                        }
                    }
                ]
            },
            {
                'activityId': '2',
                'transferItems': [
                    {
                        'instrument': {
                            'assetType': 'OPTION',
                            'underlyingSymbol': 'AAPL',
                            'symbol': 'AAPL  260821C00295000'
                        }
                    }
                ]
            }
        ]
        ibit_txns = roll_chain.filter_transactions_by_underlying(txns, 'IBIT')
        self.assertEqual(len(ibit_txns), 1)
        self.assertEqual(ibit_txns[0]['activityId'], '1')

    def test_build_roll_chain_single_roll(self):
        txns = [
            {
                'activityId': 101,
                'orderId': 999,
                'time': '2026-08-20T19:00:18+0000',
                'netAmount': -1122.65,
                'transferItems': [
                    {
                        'positionEffect': 'CLOSING',
                        'amount': 4.0,
                        'price': 2.80,
                        'cost': -1120.0,
                        'instrument': {
                            'assetType': 'OPTION',
                            'underlyingSymbol': 'IBIT',
                            'symbol': 'IBIT  260911C00039000'
                        }
                    }
                ]
            },
            {
                'activityId': 102,
                'orderId': 999,
                'time': '2026-08-20T19:00:18+0000',
                'netAmount': 1149.32,
                'transferItems': [
                    {
                        'positionEffect': 'OPENING',
                        'amount': -4.0,
                        'price': 2.88,
                        'cost': 1152.0,
                        'instrument': {
                            'assetType': 'OPTION',
                            'underlyingSymbol': 'IBIT',
                            'symbol': 'IBIT  261002C00040000'
                        }
                    }
                ]
            }
        ]

        result = roll_chain.build_roll_chain(txns, 'IBIT  261002C00040000')
        self.assertEqual(result['underlying'], 'IBIT')
        self.assertEqual(result['summary']['total_legs'], 2)
        self.assertTrue(result['summary']['is_rolled'])
        self.assertAlmostEqual(result['summary']['total_net_amount'], 26.67, places=2)

        chain = result['chain']
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[1]['symbol'], 'IBIT  261002C00040000')
        self.assertEqual(chain[1]['action'], 'STO')
        self.assertEqual(chain[1]['rolled_from_symbol'], 'IBIT  260911C00039000')
        self.assertAlmostEqual(chain[1]['roll_net_amount'], 26.67, places=2)

    def test_build_roll_chain_empty_symbol(self):
        result = roll_chain.build_roll_chain([], '')
        self.assertEqual(result['chain'], [])
        self.assertEqual(result['summary']['total_legs'], 0)


if __name__ == '__main__':
    unittest.main()
