"""
test_script_cli.py
~~~~~~~~~~~~~~~~~~
Unit tests for the admin CLI tool (script.py).
"""

import unittest
from unittest.mock import patch, MagicMock
import script


class TestScriptCLI(unittest.TestCase):

    @patch("script.firestore_db.get_db")
    def test_resolve_uid_auto_discovery(self, mock_get_db):
        mock_doc = MagicMock()
        mock_doc.id = "discovered_uid_123"
        mock_db = MagicMock()
        mock_db.collection.return_value.limit.return_value.stream.return_value = [mock_doc]
        mock_get_db.return_value = mock_db

        uid = script.resolve_uid(None)
        self.assertEqual(uid, "discovered_uid_123")

    def test_resolve_uid_explicit(self):
        uid = script.resolve_uid("explicit_uid_456")
        self.assertEqual(uid, "explicit_uid_456")

    def test_build_parser(self):
        parser = script.build_parser()

        args = parser.parse_args(
            ["--account", "acc2", "--symbol", "NVDA", "txns", "--limit", "25", "--unprocessed"]
        )
        self.assertEqual(args.account, "acc2")
        self.assertEqual(args.symbol, "NVDA")
        self.assertEqual(args.command, "txns")
        self.assertEqual(args.limit, 25)
        self.assertTrue(args.unprocessed)

        args_realized = parser.parse_args(["-s", "IBIT", "realized", "--json"])
        self.assertEqual(args_realized.symbol, "IBIT")
        self.assertEqual(args_realized.command, "realized")
        self.assertTrue(args_realized.json)

    @patch("script.firestore_db.get_realized_pl_for_accounts")
    def test_handle_realized_command_symbol_filter(self, mock_get_realized):
        mock_get_realized.return_value = [
            {"symbol": "NVDA  260828C00240000", "P/L": 100.0, "id": "rec1"},
            {"symbol": "IBIT  260911C00039000", "P/L": -50.0, "id": "rec2"},
            {"symbol": "NVDA", "P/L": 200.0, "id": "rec3"},
        ]
        with patch("sys.stdout"):
            script.handle_realized_command(
                uid="uid1",
                account_numbers=["hash1"],
                limit=10,
                symbol_filter="NVDA",
                output_json=False,
            )
        mock_get_realized.assert_called_once_with(
            uid="uid1",
            account_numbers=["hash1"],
            limit=10,
            from_date=None,
            to_date=None,
            trade_type=None,
            symbol="NVDA",
        )

    def test_primary_transfer_item_and_enrichment(self):
        txn_trade = {
            "transferItems": [
                {
                    "positionEffect": "OPENING",
                    "price": 2.5,
                    "amount": 2.0,
                    "instrument": {"assetType": "OPTION", "symbol": "AAPL  261219C00295000", "underlyingSymbol": "AAPL"},
                },
                {
                    "instrument": {"assetType": "CURRENCY", "symbol": "CURRENCY_USD"},
                },
            ]
        }
        primary = script.firestore_db._primary_transfer_item(txn_trade)
        self.assertIsNotNone(primary)
        self.assertEqual(primary["instrument"]["symbol"], "AAPL  261219C00295000")

        enriched = script.firestore_db.enrich_transaction(dict(txn_trade))
        self.assertEqual(enriched["symbol"], "AAPL  261219C00295000")
        self.assertEqual(enriched["underlyingSymbol"], "AAPL")
        self.assertEqual(enriched["assetType"], "OPTION")
        self.assertEqual(enriched["positionEffect"], "OPENING")
        self.assertEqual(enriched["price"], 2.5)
        self.assertEqual(enriched["amount"], 2.0)

        txn_dividend = {
            "transferItems": [
                {
                    "instrument": {"assetType": "CURRENCY", "symbol": "CURRENCY_USD"},
                }
            ]
        }
        primary_div = script.firestore_db._primary_transfer_item(txn_dividend)
        self.assertIsNotNone(primary_div)
        self.assertEqual(primary_div["instrument"]["symbol"], "CURRENCY_USD")

        enriched_div = script.firestore_db.enrich_transaction(dict(txn_dividend))
        self.assertEqual(enriched_div["symbol"], "—")

        self.assertIsNone(script.firestore_db._primary_transfer_item({}))
        self.assertIsNone(script.firestore_db._primary_transfer_item({"transferItems": []}))

    def test_matches_txn_symbol_ignores_currency(self):
        txn_trade = {
            "transferItems": [
                {
                    "positionEffect": "OPENING",
                    "instrument": {"assetType": "OPTION", "symbol": "AAPL  261219C00295000", "underlyingSymbol": "AAPL"},
                },
                {
                    "instrument": {"assetType": "CURRENCY", "symbol": "CURRENCY_USD"},
                },
            ]
        }
        # Searching for USD should NOT match the cash leg of an equity/option trade
        self.assertFalse(script.firestore_db._matches_txn_symbol(txn_trade, "USD"))
        # Searching for the security symbol SHOULD match
        self.assertTrue(script.firestore_db._matches_txn_symbol(txn_trade, "AAPL"))

    def test_build_parser_order(self):
        parser = script.build_parser()

        args = parser.parse_args(
            [
                "-s",
                "AAPL  260821C00205000",
                "order",
                "-q",
                "2",
                "-p",
                "3.50",
                "-i",
                "BTC",
                "--preview",
            ]
        )
        self.assertEqual(args.command, "order")
        self.assertEqual(args.symbol, "AAPL  260821C00205000")
        self.assertEqual(args.quantity, 2.0)
        self.assertEqual(args.price, "3.50")
        self.assertEqual(args.instruction, "BTC")
        self.assertTrue(args.preview)

        args_alias = parser.parse_args(
            [
                "-s",
                "NVDA",
                "place-order",
                "-q",
                "10",
                "-i",
                "BUY",
                "--order-type",
                "MARKET",
            ]
        )
        self.assertEqual(args_alias.command, "place-order")
        self.assertEqual(args_alias.symbol, "NVDA")
        self.assertEqual(args_alias.order_type, "MARKET")

    @patch("script.SchwabAuthManager")
    @patch("script.orders.execute_order")
    @patch("script.orders.build_single_order")
    def test_handle_order_command(self, mock_build, mock_execute, mock_auth_cls):
        mock_auth = MagicMock()
        mock_auth.refresh_user_tokens_if_needed.return_value = "valid_token"
        mock_auth_cls.return_value = mock_auth

        mock_build.return_value = {"orderType": "LIMIT", "orderLegCollection": []}
        mock_execute.return_value = {"orderValidationResult": "SUCCESS"}

        # Test preview
        with patch("sys.stdout"):
            script.handle_order_command(
                uid="uid1",
                acc_num="acc1",
                symbol="AAPL  260821C00205000",
                quantity=1,
                instruction="BTC",
                price="2.50",
                preview=True,
            )
        mock_build.assert_called_once_with(
            symbol="AAPL  260821C00205000",
            quantity=1,
            instruction="BTC",
            price="2.50",
            order_type="LIMIT",
            duration="GTC",
            session="NORMAL",
        )
        mock_execute.assert_called_once_with(
            access_token="valid_token",
            account_number="acc1",
            order_payload=mock_build.return_value,
            preview=True,
        )

        mock_build.reset_mock()
        mock_execute.reset_mock()
        mock_execute.return_value = {
            "success": True,
            "orderId": 123456,
            "location": "/orders/123456",
        }

        # Test place live
        with patch("sys.stdout"):
            script.handle_order_command(
                uid="uid1",
                acc_num="acc1",
                symbol="AAPL  260821C00205000",
                quantity=1,
                instruction="BTC",
                price="2.50",
                preview=False,
            )
        mock_execute.assert_called_once_with(
            access_token="valid_token",
            account_number="acc1",
            order_payload=mock_build.return_value,
            preview=False,
        )


if __name__ == "__main__":
    unittest.main()
