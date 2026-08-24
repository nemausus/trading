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
    @patch('script.constants.get_primary_account_hash')
    @patch('script.constants.get_secondary_account_hash')
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


if __name__ == '__main__':
    unittest.main()
