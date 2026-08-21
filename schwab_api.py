"""
schwab_api.py
~~~~~~~~~~~~~
Common HTTP utility for interacting with the Schwab API backend.
"""

from datetime import datetime
import json
import logging

import requests

from constants import SCHWAB_REQUEST_TIMEOUT


def _save_response_dump(url: str, data: dict | list) -> None:
    """Save raw response JSON to a file in responses/ directory for debugging."""
    filename = "responses/" + url.replace("/", "_").replace(":", "_") + ".json"
    with open(filename, 'w') as f:
        f.write(str(datetime.now()))
        f.write("\n")
        json.dump(data, f, indent=2)


def schwab_request(
    method: str,
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    data: dict | None = None,
    timeout: tuple[int, int] = SCHWAB_REQUEST_TIMEOUT,
    **kwargs
) -> dict | list:
    """
    Make an HTTP request to the Schwab backend with unified logging.

    Logs the request, executes the call, validates status via raise_for_status(),
    and returns parsed JSON response content.
    """
    logging.warning("Making Schwab API %s request to %s (params=%s)", method, url, params)

    resp = requests.request(
        method.upper(), url,
        headers=headers, params=params, data=data,
        timeout=timeout, **kwargs,
    )
    resp.raise_for_status()
    ret = resp.json()
    # _save_response_dump(url, ret)
    return ret
