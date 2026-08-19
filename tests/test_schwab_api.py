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


if __name__ == '__main__':
    unittest.main()

