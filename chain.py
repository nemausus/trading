"""
chain.py
~~~~~~~~
Service module for the Option Chain tab.

Fetches and filters the Schwab option chain for an underlying symbol,
returning a structured response ready for the frontend.
"""

import datetime

from constants import SCHWAB_TZ, _fval
import schwab_api


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _offset_date(today: datetime.date, days: int | None) -> str | None:
    """Return (today + days).isoformat() or None when days is None."""
    return (today + datetime.timedelta(days=days)).isoformat() if days is not None else None


def _validate_range(name: str, value, *, lo, hi, typ) -> None:
    """Raise ValueError if *value* is not an instance of *typ* within [lo, hi]."""
    if not isinstance(value, typ) or not (lo <= value <= hi):
        typ_name = '/'.join(t.__name__ for t in typ) if isinstance(typ, tuple) else typ.__name__
        raise ValueError(
            f"Invalid {name}: {value}. Must be a {typ_name} between {lo} and {hi}."
        )


def _validate_chain_params(symbol: str, min_dte: int | None, max_dte: int | None,
                            min_delta: float | None, max_delta: float | None) -> None:
    """Validate DTE, Delta, and symbol parameters, raising ValueError for out-of-bounds values."""
    if not symbol or not isinstance(symbol, str) or len(symbol) > 4:
        raise ValueError(f"Invalid symbol: '{symbol}'. Must be an alphanumeric ticker up to 10 characters.")

    if min_dte is not None:
        _validate_range('min_dte', min_dte, lo=0, hi=1000, typ=int)
    if max_dte is not None:
        _validate_range('max_dte', max_dte, lo=0, hi=1000, typ=int)
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise ValueError(f"min_dte ({min_dte}) cannot be greater than max_dte ({max_dte}).")

    if min_delta is not None:
        _validate_range('min_delta', min_delta, lo=-1.0, hi=1.0, typ=(int, float))
    if max_delta is not None:
        _validate_range('max_delta', max_delta, lo=-1.0, hi=1.0, typ=(int, float))
    if min_delta is not None and max_delta is not None and min_delta > max_delta:
        raise ValueError(f"min_delta ({min_delta}) cannot be greater than max_delta ({max_delta}).")


def _parse_exp_map(exp_map: dict, stock_price: float, contract_type_label: str) -> list:
    """Flatten a Schwab callExpDateMap / putExpDateMap into a list of option dicts."""
    contracts = []
    if not exp_map or not isinstance(exp_map, dict):
        return contracts

    for exp_key, strike_map in exp_map.items():
        if not isinstance(strike_map, dict):
            continue
        for strike_key, contract_list in strike_map.items():
            if not isinstance(contract_list, list):
                continue
            for item in contract_list:
                if not isinstance(item, dict):
                    continue

                symbol = item.get('symbol', '')
                strike = float(item.get('strikePrice', 0.0))
                dte = int(item.get('daysToExpiration', 0))
                exp_date_raw = item.get('expirationDate', '')
                exp_date = exp_date_raw[:10] if exp_date_raw else ''

                bid = _fval(item, 'bid')
                ask = _fval(item, 'ask')
                mark = _fval(item, 'mark') or (bid + ask) / 2.0
                delta = _fval(item, 'delta')
                volatility = _fval(item, 'volatility')
                open_interest = int(item.get('openInterest', 0) or 0)
                time_value = _fval(item, 'timeValue')

                change_pct = (strike * 100.0 / stock_price - 100.0) if stock_price > 0 else 0.0
                be_price = strike + mark if delta > 0 else strike - mark
                be_change_pct = (be_price * 100.0 / stock_price - 100.0) if stock_price > 0 else 0.0

                denom = (stock_price if delta > 0 else strike) - mark
                mpr = (time_value * 3000.0 / (1 if dte == 0 else dte) / denom) if (dte >= 0 and denom > 0) else 0.0

                contracts.append({
                    'symbol': symbol,
                    'contractType': contract_type_label,
                    'strikePrice': strike,
                    'expirationDate': exp_date,
                    'dte': dte,
                    'mark': mark,
                    'delta': delta,
                    'volatility': volatility,
                    'openInterest': open_interest,
                    'change': change_pct,
                    'beChange': be_change_pct,
                    'mpr': mpr
                })
    return contracts


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_option_chain(
    access_token: str,
    symbol: str,
    contract_type: str = 'CALL',
    min_dte: int | None = None,
    max_dte: int | None = None,
    min_delta: float | None = None,
    max_delta: float | None = None,
) -> dict:
    """Fetch the option chain for *symbol*, filter by DTE and delta, and return structured data.

    Raises:
        ValueError: If any parameter fails validation.
        SchwabAPIError: If the Schwab API call fails.
    """
    _validate_chain_params(symbol, min_dte, max_dte, min_delta, max_delta)

    today = datetime.datetime.now(SCHWAB_TZ).date()
    from_date = _offset_date(today, min_dte)
    to_date = _offset_date(today, max_dte)
    ct = contract_type if contract_type in ('CALL', 'PUT', 'ALL') else 'ALL'

    data = schwab_api.get_option_chains(
        access_token, symbol,
        contract_type=ct,
        from_date=from_date,
        to_date=to_date,
        include_underlying_quote=True,
    )

    underlying_data = data.get('underlying', {})
    stock_price = float(underlying_data.get('last', 0.0) or underlying_data.get('mark', 0.0) or 0.0)

    underlying_info = {
        'symbol': symbol,
        'price': stock_price,
        'change': float(underlying_data.get('change', 0.0) or 0.0),
        'percentChange': float(underlying_data.get('percentChange', 0.0) or 0.0),
    }

    raw_chain = []
    if 'callExpDateMap' in data:
        raw_chain.extend(_parse_exp_map(data['callExpDateMap'], stock_price, 'CALL'))
    if 'putExpDateMap' in data:
        raw_chain.extend(_parse_exp_map(data['putExpDateMap'], stock_price, 'PUT'))

    total_contracts = len(raw_chain)

    filtered = [
        opt for opt in raw_chain
        if (min_dte is None or opt['dte'] >= min_dte)
        and (max_dte is None or opt['dte'] <= max_dte)
        and (min_delta is None or opt['delta'] >= min_delta)
        and (max_delta is None or opt['delta'] <= max_delta)
    ]
    filtered.sort(key=lambda x: (x['expirationDate'], x['strikePrice'], x['contractType']))

    return {
        'underlying': underlying_info,
        'chain': filtered,
        'totalContracts': total_contracts,
    }
