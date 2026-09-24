"""
Unit tests for schwab_api.py.
"""

import unittest
from unittest.mock import patch, MagicMock

import schwab_api as sa


class TestSchwabApi(unittest.TestCase):

    @patch('requests.request')
    def test_schwab_request_get(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'status': 'ok'}
        mock_request.return_value = mock_resp

        res = sa.schwab_request("GET", "https://api.schwabapi.com/test", params={'a': '1'})
        self.assertEqual(res, {'status': 'ok'})
        mock_request.assert_called_once_with(
            "GET", "https://api.schwabapi.com/test",
            headers=None, params={'a': '1'}, data=None,
            timeout=sa.SCHWAB_REQUEST_TIMEOUT,
        )
        mock_resp.raise_for_status.assert_called_once()

    @patch('requests.request')
    def test_schwab_request_post(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'access_token': 'abc'}
        mock_request.return_value = mock_resp

        res = sa.schwab_request("POST", "https://api.schwabapi.com/test", data={'grant_type': 'authorization_code'})
        self.assertEqual(res, {'access_token': 'abc'})
        mock_request.assert_called_once_with(
            "POST", "https://api.schwabapi.com/test",
            headers=None, params=None, data={'grant_type': 'authorization_code'},
            timeout=sa.SCHWAB_REQUEST_TIMEOUT,
        )
        mock_resp.raise_for_status.assert_called_once()

    @patch('requests.request')
    def test_place_order(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.headers = {
            'Location': 'https://api.schwabapi.com/trader/v1/accounts/HASH123/orders/987654321'
        }
        mock_resp.text = ''
        mock_request.return_value = mock_resp

        order_data = {'orderType': 'LIMIT', 'session': 'NORMAL'}
        res = sa.place_order('token123', 'HASH123', order_data)

        self.assertTrue(res['success'])
        self.assertEqual(res['orderId'], 987654321)
        self.assertEqual(res['location'], 'https://api.schwabapi.com/trader/v1/accounts/HASH123/orders/987654321')
        self.assertEqual(res['order'], order_data)

        mock_request.assert_called_once_with(
            "POST",
            f"{sa.SCHWAB_TRADER_BASE_URL}/accounts/HASH123/orders",
            headers=sa._headers('token123'),
            params={'accountNumber': 'HASH123'},
            data=None,
            json=order_data,
            timeout=sa.SCHWAB_REQUEST_TIMEOUT,
        )

    @patch('requests.request')
    def test_preview_order(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.text = '{"orderValidationResult": "SUCCESS"}'
        mock_resp.json.return_value = {'orderValidationResult': 'SUCCESS'}
        mock_request.return_value = mock_resp

        order_data = {'orderType': 'LIMIT'}
        res = sa.preview_order('token123', 'HASH123', order_data)

        self.assertEqual(res, {'orderValidationResult': 'SUCCESS'})
        mock_request.assert_called_once_with(
            "POST",
            f"{sa.SCHWAB_TRADER_BASE_URL}/accounts/HASH123/previewOrder",
            headers=sa._headers('token123'),
            params={'accountNumber': 'HASH123'},
            data=None,
            json=order_data,
            timeout=sa.SCHWAB_REQUEST_TIMEOUT,
        )

    def test_place_order_validation(self):
        with self.assertRaises(ValueError):
            sa.place_order('', 'HASH123', {'a': 1})
        with self.assertRaises(ValueError):
            sa.place_order('token123', '', {'a': 1})
        with self.assertRaises(ValueError):
            sa.place_order('token123', 'HASH123', {})

    def test_preview_order_validation(self):
        with self.assertRaises(ValueError):
            sa.preview_order('token123', '', {'a': 1})
        with self.assertRaises(ValueError):
            sa.preview_order('token123', 'HASH123', {})


if __name__ == '__main__':
    unittest.main()

