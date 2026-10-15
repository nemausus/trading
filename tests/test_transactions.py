import unittest
from unittest.mock import patch

import transactions


class TestTransactions(unittest.TestCase):
    """Unit tests for transactions.py."""

    @patch("transactions.firestore_db.save_transactions")
    @patch("transactions.firestore_db.get_existing_activity_ids")
    @patch("transactions._fetch_transactions_raw")
    @patch("transactions.firestore_db.get_latest_transaction_time")
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


class TestFirestoreTransactionsRaw(unittest.TestCase):
    """Unit tests for raw=True parameter in firestore_db transaction functions."""

    @patch("firestore_db._txn_collection")
    @patch("firestore_db.get_db")
    def test_get_transactions_raw_vs_default(self, mock_get_db, mock_txn_col):
        import firestore_db

        class MockDoc:
            def __init__(self, doc_id, data):
                self.id = doc_id
                self._data = data

            def to_dict(self):
                return dict(self._data)

        raw_item = {
            "activityId": "123",
            "time": "2026-06-01T12:00:00Z",
            "fetched_at": "TIMESTAMP_OBJ",
            "transferItems": [
                {
                    "positionEffect": "OPENING",
                    "price": 5.0,
                    "amount": 10.0,
                    "instrument": {"symbol": "AAPL", "assetType": "EQUITY"},
                }
            ],
        }
        mock_txn_col.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            MockDoc("123", raw_item)
        ]

        # When raw=True
        res_raw = firestore_db.get_transactions("uid1", "acc1", limit=10, raw=True)
        self.assertEqual(len(res_raw), 1)
        self.assertIn("fetched_at", res_raw[0])
        self.assertNotIn("symbol", res_raw[0])

        # When raw=False (default)
        mock_txn_col.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            MockDoc("123", raw_item)
        ]
        res_default = firestore_db.get_transactions("uid1", "acc1", limit=10, raw=False)
        self.assertEqual(len(res_default), 1)
        self.assertEqual(res_default[0].get("symbol"), "AAPL")

    @patch("firestore_db._realized_pl_collection")
    @patch("firestore_db.get_db")
    def test_get_realized_pl_transactions_raw_vs_default(self, mock_get_db, mock_realized_col):
        import firestore_db

        class MockDoc:
            def __init__(self, doc_id, data):
                self.id = doc_id
                self._data = data

            def to_dict(self):
                return dict(self._data)

        raw_record = {
            "id": "rec1",
            "sell_date": "2026-06-01",
            "created_at": "TIMESTAMP_OBJ",
            "symbol": "AAPL",
            "amount": 100,
            "P/L": 500.0,
        }
        mock_realized_col.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            MockDoc("rec1", raw_record)
        ]

        # When raw=True
        res_raw = firestore_db.get_realized_pl_transactions("uid1", "acc1", limit=10, raw=True)
        self.assertEqual(len(res_raw), 1)
        self.assertIn("created_at", res_raw[0])
        self.assertNotIn("trade_type", res_raw[0])

        # When raw=False (default)
        mock_realized_col.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            MockDoc("rec1", raw_record)
        ]
        res_default = firestore_db.get_realized_pl_transactions("uid1", "acc1", limit=10, raw=False)
        self.assertEqual(len(res_default), 1)
        self.assertNotIn("created_at", res_default[0])
        self.assertEqual(res_default[0].get("trade_type"), "Stock")


if __name__ == "__main__":
    unittest.main()
