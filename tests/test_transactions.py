import unittest
from unittest.mock import patch

import transactions


class TestTransactions(unittest.TestCase):
    """Unit tests for transactions.py."""

    @patch('transactions.firestore_db.save_transactions')
    @patch('transactions.firestore_db.get_existing_activity_ids')
    @patch('transactions._fetch_transactions_raw')
    @patch('transactions.firestore_db.get_latest_transaction_time')
    def test_sync_transactions_success(
        self,
        mock_get_latest_time,
        mock_fetch_raw,
        mock_get_existing,
        mock_save,
    ):
        """Syncs transactions for specified account successfully."""
        mock_get_latest_time.return_value = "2026-01-01T10:00:00-07:30"
        raw_txns = [
            {"activityId": 101, "amount": 10},
            {"activityId": 102, "amount": 20},
        ]
        mock_fetch_raw.return_value = raw_txns
        mock_get_existing.return_value = {"101"}

        res = transactions.sync_transactions("user123", "token_abc", "acc1")

        self.assertEqual(res["new_count"], 1)
        self.assertEqual(res["account_number"], "acc1")
        self.assertNotIn("account_hash", res)
        mock_save.assert_called_once_with("user123", "acc1", [{"activityId": 102, "amount": 20}])


if __name__ == '__main__':
    unittest.main()
