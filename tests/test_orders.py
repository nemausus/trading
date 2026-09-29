"""
test_orders.py
~~~~~~~~~~~~~~
Unit tests for the orders service module (orders.py).
"""

import unittest
from unittest.mock import patch, MagicMock

import orders
import constants


class TestOrders(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        constants.init_accounts()

    def test_format_price(self):
        self.assertEqual(orders.format_price(2.5), "2.50")
        self.assertEqual(orders.format_price("150.25"), "150.25")
        self.assertEqual(orders.format_price(0.05), "0.0500")
        self.assertEqual(orders.format_price(0.0), "0.00")
        self.assertEqual(orders.format_price(100), "100.00")

        with self.assertRaises(ValueError):
            orders.format_price(-1.0)
        with self.assertRaises(ValueError):
            orders.format_price("invalid")

    def test_is_occ_option_symbol(self):
        self.assertTrue(orders._is_occ_option_symbol("AAPL  260821C00205000"))
        self.assertTrue(orders._is_occ_option_symbol("SPX   261218P06000000"))
        self.assertFalse(orders._is_occ_option_symbol("AAPL"))
        self.assertFalse(orders._is_occ_option_symbol("GOOGL"))
        self.assertFalse(orders._is_occ_option_symbol(""))

    def test_build_single_order_option_btc(self):
        order = orders.build_single_order(
            symbol="AAPL  260821C00205000",
            quantity=2,
            instruction="BTC",
            price=2.50,
        )

        self.assertEqual(order["session"], "NORMAL")
        self.assertEqual(order["duration"], "GOOD_TILL_CANCEL")
        self.assertEqual(order["orderType"], "LIMIT")
        self.assertEqual(order["orderStrategyType"], "SINGLE")
        self.assertEqual(order["price"], "2.50")
        self.assertEqual(len(order["orderLegCollection"]), 1)

        leg = order["orderLegCollection"][0]
        self.assertEqual(leg["instruction"], "BUY_TO_CLOSE")
        self.assertEqual(leg["quantity"], 2.0)
        self.assertEqual(leg["instrument"]["assetType"], "OPTION")
        self.assertEqual(leg["instrument"]["symbol"], "AAPL  260821C00205000")

    def test_build_single_order_equity_buy_market(self):
        order = orders.build_single_order(
            symbol="AAPL",
            quantity=50,
            instruction="BUY",
            order_type="MARKET",
            duration="DAY",
        )

        self.assertEqual(order["session"], "NORMAL")
        self.assertEqual(order["duration"], "DAY")
        self.assertEqual(order["orderType"], "MARKET")
        self.assertNotIn("price", order)

        leg = order["orderLegCollection"][0]
        self.assertEqual(leg["instruction"], "BUY")
        self.assertEqual(leg["quantity"], 50.0)
        self.assertEqual(leg["instrument"]["assetType"], "EQUITY")
        self.assertEqual(leg["instrument"]["symbol"], "AAPL")

    def test_build_single_order_validation(self):
        # Missing symbol
        with self.assertRaises(ValueError):
            orders.build_single_order(symbol="", quantity=1, instruction="BTC", price=1.0)

        # Invalid quantity
        with self.assertRaises(ValueError):
            orders.build_single_order(symbol="AAPL", quantity=0, instruction="BUY", price=1.0)
        with self.assertRaises(ValueError):
            orders.build_single_order(symbol="AAPL", quantity=-5, instruction="BUY", price=1.0)

        # Unknown instruction
        with self.assertRaises(ValueError):
            orders.build_single_order(symbol="AAPL", quantity=1, instruction="INVALID", price=1.0)

        # Missing price on limit order
        with self.assertRaises(ValueError):
            orders.build_single_order(
                symbol="AAPL", quantity=1, instruction="BUY", order_type="LIMIT"
            )

    @patch("orders.schwab_api.place_order")
    @patch("orders.get_account_hash", return_value="HASH_TEST")
    def test_place_order_service(self, mock_resolve, mock_api_place):
        mock_api_place.return_value = {"success": True, "orderId": 12345}

        payload = orders.build_single_order(
            symbol="AAPL  260821C00205000",
            quantity=1,
            instruction="STO",
            price=3.50,
        )
        res = orders.place_order(
            access_token="token_abc",
            account_number=constants.get_all_account_numbers()[0],
            order_payload=payload,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["orderId"], 12345)
        mock_api_place.assert_called_once()
        args = mock_api_place.call_args[0]
        self.assertEqual(args[0], "token_abc")
        self.assertEqual(args[1], "HASH_TEST")
        self.assertEqual(args[2]["orderLegCollection"][0]["instruction"], "SELL_TO_OPEN")

    @patch("orders.schwab_api.preview_order")
    @patch("orders.get_account_hash", return_value="HASH_TEST")
    def test_preview_order_service(self, mock_resolve, mock_api_preview):
        mock_api_preview.return_value = {"orderValidationResult": "SUCCESS"}

        payload = orders.build_single_order(
            symbol="NVDA",
            quantity=10,
            instruction="BUY",
            price=120.0,
        )
        res = orders.preview_order(
            access_token="token_abc",
            account_number=constants.get_all_account_numbers()[1],
            order_payload=payload,
        )

        self.assertEqual(res["orderValidationResult"], "SUCCESS")
        mock_api_preview.assert_called_once()

    def test_build_roll_order(self):
        order = orders.build_roll_order(
            close_symbol="AAPL  260417C00200000",
            open_symbol="AAPL  260515C00205000",
            quantity=2,
            close_instruction="BTC",
            open_instruction="STO",
            price=0.25,
            order_type="NET_CREDIT",
        )

        self.assertEqual(order["complexOrderStrategyType"], "CUSTOM")
        self.assertEqual(order["orderStrategyType"], "SINGLE")
        self.assertEqual(order["orderType"], "NET_CREDIT")
        self.assertEqual(order["quantity"], 2.0)
        self.assertEqual(order["price"], "0.2500")
        self.assertEqual(len(order["orderLegCollection"]), 2)

        leg1 = order["orderLegCollection"][0]
        self.assertEqual(leg1["instruction"], "BUY_TO_CLOSE")
        self.assertEqual(leg1["quantity"], 2.0)
        self.assertEqual(leg1["instrument"]["symbol"], "AAPL  260417C00200000")

        leg2 = order["orderLegCollection"][1]
        self.assertEqual(leg2["instruction"], "SELL_TO_OPEN")
        self.assertEqual(leg2["quantity"], 2.0)
        self.assertEqual(leg2["instrument"]["symbol"], "AAPL  260515C00205000")

    def test_build_roll_order_validation(self):
        # Missing symbol
        with self.assertRaises(ValueError):
            orders.build_roll_order(
                close_symbol="",
                open_symbol="AAPL  260515C00205000",
                quantity=1,
                price=0.10,
            )
        # Invalid instruction
        with self.assertRaises(ValueError):
            orders.build_roll_order(
                close_symbol="AAPL  260417C00200000",
                open_symbol="AAPL  260515C00205000",
                quantity=1,
                close_instruction="INVALID",
                price=0.10,
            )
        # Missing price
        with self.assertRaises(ValueError):
            orders.build_roll_order(
                close_symbol="AAPL  260417C00200000",
                open_symbol="AAPL  260515C00205000",
                quantity=1,
                price=None,
            )


class TestOrderRoute(unittest.TestCase):

    def setUp(self):
        from app import app

        app.config["TESTING"] = True
        self.client = app.test_client()

    @patch("app.auth.verify_id_token", return_value={"uid": "test_user"})
    @patch("app.schwab_auth.refresh_user_tokens_if_needed", return_value="fake_schwab_token")
    @patch("orders.schwab_api.place_order")
    @patch("orders.get_account_hash", return_value="HASH_MOCK")
    def test_post_order_route_success(self, mock_resolve, mock_api_place, mock_token, mock_auth):
        mock_api_place.return_value = {
            "success": True,
            "orderId": 998877,
            "location": "/orders/998877",
        }

        payload = {
            "account_number": constants.get_all_account_numbers()[0],
            "symbol": "AAPL  260821C00205000",
            "quantity": 1,
            "instruction": "BTC",
            "price": 2.75,
        }
        res = self.client.post(
            "/api/schwab/order",
            json=payload,
            headers={"Authorization": "Bearer fake_id_token"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["orderId"], 998877)

    @patch("app.auth.verify_id_token", return_value={"uid": "test_user"})
    @patch("app.schwab_auth.refresh_user_tokens_if_needed", return_value="fake_schwab_token")
    @patch("orders.schwab_api.preview_order")
    @patch("orders.get_account_hash", return_value="HASH_MOCK")
    def test_post_order_preview_route_success(
        self, mock_resolve, mock_api_preview, mock_token, mock_auth
    ):
        mock_api_preview.return_value = {"orderValidationResult": "SUCCESS", "cost": 150.0}

        payload = {
            "account_number": constants.get_all_account_numbers()[1],
            "symbol": "NVDA",
            "quantity": 10,
            "instruction": "BUY",
            "price": 115.0,
            "preview": True,
        }
        res = self.client.post(
            "/api/schwab/orders",
            json=payload,
            headers={"Authorization": "Bearer fake_id_token"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["orderValidationResult"], "SUCCESS")

    @patch("app.auth.verify_id_token", return_value={"uid": "test_user"})
    @patch("app.schwab_auth.refresh_user_tokens_if_needed", return_value="fake_schwab_token")
    def test_post_order_route_validation_error(self, mock_token, mock_auth):
        # Missing symbol
        payload = {
            "quantity": 1,
            "instruction": "BTC",
            "price": 2.75,
        }
        res = self.client.post(
            "/api/schwab/order",
            json=payload,
            headers={"Authorization": "Bearer fake_id_token"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

    @patch("app.auth.verify_id_token", return_value={"uid": "test_user"})
    @patch("app.schwab_auth.refresh_user_tokens_if_needed", return_value="fake_schwab_token")
    @patch("orders.schwab_api.place_order")
    @patch("orders.get_account_hash", return_value="HASH_MOCK")
    def test_post_roll_order_route_success(
        self, mock_resolve, mock_api_place, mock_token, mock_auth
    ):
        mock_api_place.return_value = {
            "success": True,
            "orderId": 554433,
            "location": "/orders/554433",
        }

        payload = {
            "account_number": constants.get_all_account_numbers()[0],
            "roll": True,
            "close_symbol": "AAPL  260417C00200000",
            "open_symbol": "AAPL  260515C00205000",
            "quantity": 1,
            "close_instruction": "BTC",
            "open_instruction": "STO",
            "order_type": "NET_CREDIT",
            "price": 0.35,
        }
        res = self.client.post(
            "/api/schwab/order",
            json=payload,
            headers={"Authorization": "Bearer fake_id_token"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["orderId"], 554433)
        mock_api_place.assert_called_once()
        sent_payload = mock_api_place.call_args[0][2]
        self.assertEqual(sent_payload["complexOrderStrategyType"], "CUSTOM")
        self.assertEqual(sent_payload["orderType"], "NET_CREDIT")
        self.assertEqual(sent_payload["price"], "0.3500")
        self.assertEqual(len(sent_payload["orderLegCollection"]), 2)

    @patch("app.auth.verify_id_token", return_value={"uid": "test_user"})
    @patch("app.schwab_auth.refresh_user_tokens_if_needed", return_value="fake_schwab_token")
    def test_post_roll_order_route_rejects_symbol_fallback(self, mock_token, mock_auth):
        payload = {
            "account_number": constants.get_all_account_numbers()[0],
            "roll": True,
            "symbol": "AAPL  260417C00200000",
            "open_symbol": "AAPL  260515C00205000",
            "quantity": 1,
            "price": 0.35,
        }
        res = self.client.post(
            "/api/schwab/order",
            json=payload,
            headers={"Authorization": "Bearer fake_id_token"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("close_symbol", data["error"])

    @patch("app.auth.verify_id_token", return_value={"uid": "test_user"})
    @patch("app.schwab_auth.refresh_user_tokens_if_needed", return_value="fake_schwab_token")
    def test_post_roll_order_route_rejects_target_symbol_fallback(self, mock_token, mock_auth):
        payload = {
            "account_number": constants.get_all_account_numbers()[0],
            "roll": True,
            "close_symbol": "AAPL  260417C00200000",
            "target_symbol": "AAPL  260515C00205000",
            "quantity": 1,
            "price": 0.35,
        }
        res = self.client.post(
            "/api/schwab/order",
            json=payload,
            headers={"Authorization": "Bearer fake_id_token"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)
        self.assertIn("open_symbol", data["error"])


if __name__ == "__main__":

    unittest.main()
