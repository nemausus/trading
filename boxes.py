"""
boxes.py
~~~~~~~~
Service module for the SPX Box Spreads tab.

Fetches SPX option chains and identifies synthetic box spreads,
returning the top results sorted by liquidity.
"""

import logging

import schwab_api
from chain import _parse_exp_map


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_SPX_BOX_ROUNDING = 10_000.0
_DEFAULT_SIZES = [100, 200, 500, 1000]
_TOP_N_RESULTS = 15


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_spx_boxes(
    access_token: str,
    from_date: str | None,
    to_date: str | None,
    sizes: list[int] | None = None,
) -> list[dict]:
    """Fetch SPX option chains and identify box spreads.

    Args:
        access_token: Valid Schwab Bearer access token.
        from_date:    ISO date lower bound (or None).
        to_date:      ISO date upper bound (or None).
        sizes:        List of box widths in points (default [100, 200, 500, 1000]).

    Returns:
        Up to 15 box-spread dicts sorted by liquidity descending.

    Raises:
        SchwabAPIError: If the Schwab API call fails.
    """
    data = schwab_api.get_option_chains(
        access_token, '$SPX',
        contract_type='ALL',
        from_date=from_date,
        to_date=to_date,
        include_underlying_quote=False,
    )

    all_contracts = (
        _parse_exp_map(data.get('callExpDateMap', {}), 0.0, 'CALL') +
        _parse_exp_map(data.get('putExpDateMap', {}),  0.0, 'PUT')
    )

    # Keep only monthly SPX contracts (exclude SPXW weeklies) with open interest.
    monthly = [
        c for c in all_contracts
        if c['symbol'].startswith('SPX  ') and c['openInterest'] > 0
    ]

    # Index by (expiration_date, strike) -> {contract_type: {mark, oi, dte}}
    by_exp_strike: dict = {}
    for c in monthly:
        key = (c['expirationDate'], c['strikePrice'])
        by_exp_strike.setdefault(key, {})[c['contractType']] = {
            'mark': c['mark'],
            'oi':   c['openInterest'],
            'dte':  c['dte'],
        }

    active_sizes = sizes if sizes else _DEFAULT_SIZES
    boxes = []

    for (exp_date, lower_strike), legs in by_exp_strike.items():
        if 'CALL' not in legs or 'PUT' not in legs:
            continue

        lower_call = legs['CALL']
        lower_put  = legs['PUT']
        dte = lower_call['dte']
        if dte <= 0:
            continue

        for size in active_sizes:
            higher_key = (exp_date, lower_strike + size)
            higher_legs = by_exp_strike.get(higher_key, {})
            if 'CALL' not in higher_legs or 'PUT' not in higher_legs:
                continue

            higher_call = higher_legs['CALL']
            higher_put  = higher_legs['PUT']

            liquidity = lower_call['oi'] + lower_put['oi'] + higher_call['oi'] + higher_put['oi']
            net_credit = (
                (lower_call['mark'] - higher_call['mark']) +
                (higher_put['mark']  - lower_put['mark'])
            )

            if net_credit <= 0:
                continue

            rate = ((size - net_credit) / net_credit) * (365.0 / dte) * 100.0

            boxes.append({
                'expirationDate': exp_date,
                'dte':       dte,
                'btoPut':    lower_strike,
                'stoPut':    lower_strike + size,
                'stoCall':   lower_strike,
                'btoCall':   lower_strike + size,
                'netCredit': net_credit,
                'rate':      rate,
                'size':      size,
                'liquidity': liquidity,
            })

    boxes.sort(key=lambda x: x['liquidity'], reverse=True)
    return boxes[:_TOP_N_RESULTS]
