"""
schwab_api.py
~~~~~~~~~~~~~
Common HTTP utility for interacting with the Schwab API backend.
"""

import json
import logging
import requests
from constants import SCHWAB_REQUEST_TIMEOUT


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
    method_upper = method.upper()
    if params:
        logging.info("Making Schwab API %s request to %s (params=%s)", method_upper, url, params)
    else:
        logging.info("Making Schwab API %s request to %s", method_upper, url)

    if method_upper == "GET":
        resp = requests.get(url, headers=headers, params=params, timeout=timeout, **kwargs)
    elif method_upper == "POST":
        resp = requests.post(url, headers=headers, data=data, params=params, timeout=timeout, **kwargs)
    else:
        resp = requests.request(method_upper, url, headers=headers, params=params, data=data, timeout=timeout, **kwargs)

    resp.raise_for_status()
    ret = resp.json()
    # filename = "responses/" + url.replace("/", "_").replace(":", "_") + ".json"
    # with open(filename, "w") as f:
    #     json.dump(ret, f, indent=2)
    return ret
