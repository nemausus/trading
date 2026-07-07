"""
constants.py
~~~~~~~~~~~~
Shared constants for the Schwab API integration.

Centralising these prevents drift between modules that previously
defined their own copies.
"""

import datetime

# (connect timeout, read timeout) in seconds for all outbound Schwab requests.
SCHWAB_REQUEST_TIMEOUT: tuple[int, int] = (5, 30)

# Schwab's API reports times in Mountain Standard Time (UTC-7:30).
SCHWAB_TZ: datetime.timezone = datetime.timezone(
    -datetime.timedelta(hours=7, minutes=30)
)
