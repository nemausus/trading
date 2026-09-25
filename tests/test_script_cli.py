"""
test_script_cli.py
~~~~~~~~~~~~~~~~~~
Unit tests for the admin CLI tool (script.py).
"""

import unittest
from unittest.mock import patch, MagicMock
import script


class TestScriptCLI(unittest.TestCase):

    @patch('script.constants.get_all_account_hashes')
    @patch('script.constants.get_account_hash')
    def test_resolve_account_hashes(self, mock_get_hash, mock_sec, mock_pri, mock_all):
        mock_all.return_value = ['hash1', 'hash2']
        mock_pri.return_value = 'hash_primary'
        mock_sec.return_value = 'hash_secondary'
        mock_get_hash.return_value = 'hash_suffix'

        self.assertEqual(script.resolve_account_hashes('all'), ['hash1', 'hash2'])
        self.assertEqual(script.resolve_account_hashes(None), ['hash1', 'hash2'])
        self.assertEqual(script.resolve_account_hashes('primary'), ['hash_primary'])
        self.assertEqual(script.resolve_account_hashes('ind'), ['hash_primary'])
        self.assertEqual(script.resolve_account_hashes('secondary'), ['hash_secondary'])
        self.assertEqual(script.resolve_account_hashes('ira'), ['hash_secondary'])

        mock_get_hash.assert_not_called()
        res = script.resolve_account_hashes('acc2')
        self.assertEqual(res, ['hash_suffix'])
        mock_get_hash.assert_called_once_with('acc2')

    @patch('script.firestore_db.get_db')
    def test_resolve_uid_auto_discovery(self, mock_get_db):
        mock_doc = MagicMock()
        mock_doc.id = 'discovered_uid_123'
        mock_db = MagicMock()
        mock_db.collection.return_value.limit.return_value.stream.return_value = [mock_doc]
        mock_get_db.return_value = mock_db

        uid = script.resolve_uid(None)
        self.assertEqual(uid, 'discovered_uid_123')

    def test_resolve_uid_explicit(self):
        uid = script.resolve_uid('explicit_uid_456')
        self.assertEqual(uid, 'explicit_uid_456')

    def test_build_parser(self):
        parser = script.build_parser()

        args = parser.parse_args(['--account', 'acc2', '--symbol', 'NVDA', 'txns', '--limit', '25', '--unprocessed'])
        self.assertEqual(args.account, 'acc2')
        self.assertEqual(args.symbol, 'NVDA')
        self.assertEqual(args.command, 'txns')
        self.assertEqual(args.limit, 25)
        self.assertTrue(args.unprocessed)

        args_realized = parser.parse_args(['-s', 'IBIT', 'realized', '--json'])
        self.assertEqual(args_realized.symbol, 'IBIT')
        self.assertEqual(args_realized.command, 'realized')
        self.assertTrue(args_realized.json)

    @patch('script.firestore_db.get_realized_pl_for_accounts')
    def test_handle_realized_command_symbol_filter(self, mock_get_realized):
        mock_get_realized.return_value = [
            {'symbol': 'NVDA  260828C00240000', 'P/L': 100.0, 'id': 'rec1'},
            {'symbol': 'IBIT  260911C00039000', 'P/L': -50.0, 'id': 'rec2'},
            {'symbol': 'NVDA', 'P/L': 200.0, 'id': 'rec3'},
        ]
        with patch('sys.stdout'):
            script.handle_realized_command(
                uid='uid1',
                account_hashes=['hash1'],
                limit=10,
                symbol_filter='NVDA',
                output_json=False
            )
        mock_get_realized.assert_called_once_with('uid1', ['hash1'], limit=100)

    def test_is_option_symbol(self):
        self.assertTrue(script._is_option_symbol('NVDA  260821C00210000'))
        self.assertTrue(script._is_option_symbol('META  270115C00800000'))
        self.assertTrue(script._is_option_symbol('UNH   260821C00330000'))
        self.assertTrue(script._is_option_symbol('META 1/23/26 655 C'))
        self.assertFalse(script._is_option_symbol('QQQ'))
        self.assertFalse(script._is_option_symbol('BTC'))
        self.assertFalse(script._is_option_symbol('AAPL'))
        self.assertFalse(script._is_option_symbol('MARGIN INTEREST'))
        self.assertFalse(script._is_option_symbol(''))

    def test_is_exception_record(self):
        ex_id = 'csv_11112222_2025-12-31_2026-01-23_META  260123C00655000_10.0'
        ex_data = {
            'buy_date': '2025-12-31',
            'sell_date': '2026-01-23',
            'symbol': 'META  260123C00655000',
            'buy_price': 19.20,
            'sell_price': 7.99,
        }
        self.assertTrue(script._is_exception_record(ex_id, ex_data))

        # Normal record should not be marked as exception
        normal_id = 'csv_11112222_2026-08-18_2026-08-18_NVDA  260821C00210000_4.0'
        normal_data = {
            'buy_date': '2026-08-18',
            'sell_date': '2026-08-18',
            'symbol': 'NVDA  260821C00210000',
            'buy_price': 16.81,
            'sell_price': 7.59,
        }
        self.assertFalse(script._is_exception_record(normal_id, normal_data))

    def test_build_parser_fix_realized(self):
        parser = script.build_parser()
        args = parser.parse_args(['fix-realized', '--account', 'acc2', '--dry-run'])
        self.assertEqual(args.command, 'fix-realized')
        self.assertEqual(args.sub_account, 'acc2')
        self.assertTrue(args.dry_run)
        self.assertEqual(args.start_date, '2026-01-01')
        self.assertEqual(args.end_date, '2026-08-18')

    @patch('script.constants.get_account_number_for_hash', return_value='11112222')
    @patch('script.firestore_db._realized_pl_collection')
    @patch('script.firestore_db.get_db')
    def test_handle_fix_realized_command_live_and_dry_run(self, mock_get_db, mock_get_col, mock_get_acc_num):
        mock_db = MagicMock()
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch
        mock_get_db.return_value = mock_db

        # Prepare mock documents: 1 option to update, 1 stock to skip, 1 exception to skip, 1 outside date
        doc_opt = MagicMock()
        doc_opt.id = 'csv_11112222_2026-08-18_2026-08-18_NVDA  260821C00210000_4.0'
        doc_opt.reference = 'ref_opt'
        doc_opt.to_dict.return_value = {
            'symbol': 'NVDA  260821C00210000',
            'sell_date': '2026-08-18',
            'buy_date': '2026-08-18',
            'buy_price': 16.81,
            'sell_price': 7.59,
        }

        doc_stock = MagicMock()
        doc_stock.id = 'csv_11112222_2026-06-24_QQQ_2.0'
        doc_stock.reference = 'ref_stock'
        doc_stock.to_dict.return_value = {
            'symbol': 'QQQ',
            'sell_date': '2026-06-24',
            'buy_date': '2026-03-26',
            'buy_price': 575.66,
            'sell_price': 710.12,
        }

        doc_ex = MagicMock()
        doc_ex.id = 'csv_11112222_2025-12-31_2026-01-23_META  260123C00655000_10.0'
        doc_ex.reference = 'ref_ex'
        doc_ex.to_dict.return_value = {
            'symbol': 'META  260123C00655000',
            'sell_date': '2026-01-23',
            'buy_date': '2025-12-31',
            'buy_price': 19.20,
            'sell_price': 7.99,
        }

        doc_outside = MagicMock()
        doc_outside.id = 'realized_after_aug18'
        doc_outside.reference = 'ref_outside'
        doc_outside.to_dict.return_value = {
            'symbol': 'NVDA  261002C00240000',
            'sell_date': '2026-09-11',
            'buy_date': '2026-09-02',
            'buy_price': 2.80,
            'sell_price': 1.09,
        }

        mock_col = MagicMock()
        mock_col.stream.return_value = [doc_opt, doc_stock, doc_ex, doc_outside]
        mock_get_col.return_value = mock_col

        # Test Dry Run
        with patch('sys.stdout'):
            script.handle_fix_realized_command(
                uid='uid1',
                account_hashes=['hash_acc2'],
                start_date='2026-01-01',
                end_date='2026-08-18',
                dry_run=True,
            )
        mock_batch.commit.assert_not_called()

        # Test Live Run
        with patch('sys.stdout'):
            script.handle_fix_realized_command(
                uid='uid1',
                account_hashes=['hash_acc2'],
                start_date='2026-01-01',
                end_date='2026-08-18',
                dry_run=False,
            )
        mock_batch.set.assert_called_once_with(
            'ref_opt',
            {'buy_price': 7.59, 'sell_price': 16.81},
            merge=True
        )
        mock_batch.commit.assert_called_once()

    def test_build_parser_order(self):
        parser = script.build_parser()

        args = parser.parse_args([
            'order',
            '-s', 'AAPL  260821C00205000',
            '-q', '2',
            '-p', '3.50',
            '-i', 'BTC',
            '--preview',
        ])
        self.assertEqual(args.command, 'order')
        self.assertEqual(args.symbol, 'AAPL  260821C00205000')
        self.assertEqual(args.quantity, 2.0)
        self.assertEqual(args.price, '3.50')
        self.assertEqual(args.instruction, 'BTC')
        self.assertTrue(args.preview)

        args_alias = parser.parse_args([
            'place-order',
            '-s', 'NVDA',
            '-q', '10',
            '-i', 'BUY',
            '--order-type', 'MARKET',
        ])
        self.assertEqual(args_alias.command, 'place-order')
        self.assertEqual(args_alias.symbol, 'NVDA')
        self.assertEqual(args_alias.order_type, 'MARKET')

    @patch('script.SchwabAuthManager')
    @patch('script.orders.execute_order')
    @patch('script.orders.build_single_order')
    @patch('script.constants.get_account_number_for_hash', return_value='acc1')
    def test_handle_order_command(self, mock_acc_num, mock_build, mock_execute, mock_auth_cls):
        mock_auth = MagicMock()
        mock_auth.refresh_user_tokens_if_needed.return_value = 'valid_token'
        mock_auth_cls.return_value = mock_auth

        mock_build.return_value = {'orderType': 'LIMIT', 'orderLegCollection': []}
        mock_execute.return_value = {'orderValidationResult': 'SUCCESS'}

        # Test preview
        with patch('sys.stdout'):
            script.handle_order_command(
                uid='uid1',
                account_hash='hash123',
                symbol='AAPL  260821C00205000',
                quantity=1,
                instruction='BTC',
                price='2.50',
                preview=True,
            )
        mock_build.assert_called_once_with(
            symbol='AAPL  260821C00205000',
            quantity=1,
            instruction='BTC',
            price='2.50',
            order_type='LIMIT',
            duration='GTC',
            session='NORMAL',
        )
        mock_execute.assert_called_once_with(
            access_token='valid_token',
            account='hash123',
            order_payload=mock_build.return_value,
            preview=True,
        )

        mock_build.reset_mock()
        mock_execute.reset_mock()
        mock_execute.return_value = {'success': True, 'orderId': 123456, 'location': '/orders/123456'}

        # Test place live
        with patch('sys.stdout'):
            script.handle_order_command(
                uid='uid1',
                account_hash='hash123',
                symbol='AAPL  260821C00205000',
                quantity=1,
                instruction='BTC',
                price='2.50',
                preview=False,
            )
        mock_execute.assert_called_once_with(
            access_token='valid_token',
            account='hash123',
            order_payload=mock_build.return_value,
            preview=False,
        )


if __name__ == '__main__':
    unittest.main()

