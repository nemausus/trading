from constants import get_account_hash
import datetime
import logging
import requests

from constants import SCHWAB_REQUEST_TIMEOUT, SCHWAB_TZ
from schwab_api import schwab_request

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

OPTION_MULTIPLIER = 100

# Instruction abbreviations shared by fetch_active_orders and callers
INS_MAP = {
    'BUY_TO_CLOSE': 'BTC',
    'SELL_TO_OPEN': 'STO',
    'BUY_TO_OPEN': 'BTO',
    'SELL_TO_CLOSE': 'STC',
    'GOOD_TILL_CANCEL': 'GTC',
}

# Rounding unit for SPX box spread notional (boxes are sized in $10k increments).
_SPX_BOX_ROUNDING = 10_000.0

# Tickers excluded from the uncovered-long (Todo) list
_TODO_EXCLUDE = frozenset(('QQQM', 'VTI', 'SNOW', 'SPX'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schwab_headers(access_token: str) -> dict:
    """Return standard Schwab Bearer auth headers for API calls."""
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


def _fval(d: dict, key: str, default: float = 0.0) -> float:
    """Safely read a float from *d*, treating None and missing as *default*."""
    return float(d.get(key, default) or default)

def _parse_expiration_date(expiration_date: str) -> datetime.date:
    try:
        dt = datetime.datetime.strptime(expiration_date, '%y%m%d')
        return dt.date()
    except ValueError as e:
        raise ValueError(
            'expiration date must follow format '
            '[two digit year][Month with leading zero]'
            '[Day with leading zero] Found: ' + str(expiration_date)
        ) from e


def is_option(symbol: str) -> bool:
    """Return True if *symbol* looks like an option (>4 characters)."""
    return len(symbol) > 4


def get_option_multiplier(symbol: str) -> int:
    """Return 100 for options, 1 for equities."""
    return OPTION_MULTIPLIER if is_option(symbol) else 1


def _base_symbol(symbol: str) -> str:
    """Extract the underlying ticker from an option or equity symbol."""
    return symbol if not is_option(symbol) else symbol.split(' ')[0].rstrip()


def to_iso_datetime_str(d: str | None) -> str:
    """Convert a YYYY-MM-DD string (or None) to a timezone-aware ISO string."""
    if d is None:
        return datetime.datetime.now(SCHWAB_TZ).isoformat()
    try:
        dt = datetime.datetime.strptime(d, '%Y-%m-%d').replace(tzinfo=SCHWAB_TZ)
        return dt.isoformat()
    except Exception as exc:
        logging.warning("Could not parse date '%s', defaulting to now: %s", d, exc)
        return datetime.datetime.now(SCHWAB_TZ).isoformat()


# ---------------------------------------------------------------------------
# OptionSymbol
# ---------------------------------------------------------------------------

class OptionSymbol:
    """Parse and represent a Schwab OCC option symbol."""

    def __init__(self, underlying_symbol: str, expiration_date: datetime.date,
                 contract_type: str, strike_price: str):
        self.underlying_symbol = underlying_symbol
        self.expiration_date = expiration_date  # datetime.date
        self.contract_type = contract_type      # 'C' or 'P'
        self.strike_price = strike_price        # decimal string, e.g. "295.00"

    @classmethod
    def parse_symbol(cls, symbol: str) -> 'OptionSymbol':
        """Parse an OCC option symbol string."""
        if not symbol or len(symbol) < 13:
            raise ValueError(f"Invalid option symbol format: {symbol}")

        underlying = symbol[:6].rstrip()
        rest = symbol[6:]

        if 'P' in rest:
            expiration_date_str, strike_str = rest.split('P', 1)
            contract_type = 'P'
        elif 'C' in rest:
            expiration_date_str, strike_str = rest.split('C', 1)
            contract_type = 'C'
        else:
            expiration_date_str, strike_str, contract_type = rest, "1000", 'C'

        try:
            strike = f"{int(strike_str) / 1000.0:.2f}"
        except Exception:
            strike = "0.00"

        return cls(underlying, _parse_expiration_date(expiration_date_str),
                   contract_type, strike)

    def dte(self, ref_date=None) -> int:
        """Days to expiration from *ref_date* (defaults to today in Schwab TZ)."""
        if ref_date is None:
            ref_date = datetime.datetime.now(SCHWAB_TZ).date()
        elif isinstance(ref_date, str):
            ref_date = datetime.date.fromisoformat(ref_date[:10])
        return int((self.expiration_date - ref_date).days)


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def fetch_quotes(access_token: str, symbols: list) -> dict:
    """Fetch real-time quotes for *symbols* in chunks of 200."""
    if not symbols:
        return {}

    headers = _schwab_headers(access_token)
    quotes: dict = {}

    for i in range(0, len(symbols), 200):
        chunk = ",".join(symbols[i:i + 200])
        try:
            data = schwab_request(
                "GET",
                "https://api.schwabapi.com/marketdata/v1/quotes",
                headers=headers,
                params={'symbols': chunk},
            )
            if isinstance(data, dict):
                quotes.update(data)
        except Exception as e:
            logging.error("Failed to fetch quotes: %s", e)

    return quotes


def fetch_active_orders(access_token: str, account_nums: list) -> list:
    """Fetch open (no closeTime) orders for every account in *account_hashes*."""
    headers = _schwab_headers(access_token)
    from_date = to_iso_datetime_str(
        (datetime.datetime.now(SCHWAB_TZ) - datetime.timedelta(days=7)).date().isoformat()
    )
    active_orders: list = []

    for acc_num in account_nums:
        acc_hash = get_account_hash(acc_num)
        try:
            orders_data = schwab_request(
                "GET",
                f"https://api.schwabapi.com/trader/v1/accounts/{acc_hash}/orders",
                headers=headers,
                params={'fromEnteredTime': from_date,
                        'toEnteredTime': datetime.datetime.now(SCHWAB_TZ).isoformat()},
            )
            if not isinstance(orders_data, list):
                continue

            for order in orders_data:
                if order.get('closeTime') is not None:
                    continue
                price     = order.get('price')
                status    = INS_MAP.get(order.get('status'), order.get('status'))
                duration  = INS_MAP.get(order.get('duration'), order.get('duration'))
                order_type = INS_MAP.get(order.get('orderType'), order.get('orderType'))

                for leg in order.get('orderLegCollection', []):
                    active_orders.append({
                        'accountNumber': acc_num,
                        'symbol':    leg.get('instrument', {}).get('symbol'),
                        'type':      INS_MAP.get(leg.get('instruction'), leg.get('instruction')),
                        'quantity':  leg.get('quantity'),
                        'price':     price,
                        'status':    status,
                        'duration':  duration,
                        'orderType': order_type,
                    })
        except Exception as e:
            logging.error("Error fetching orders for account %s: %s", acc_num, e)

    return active_orders


def _parse_exp_map(exp_map: dict, stock_price: float, contract_type_label: str) -> list:
    """Helper to flatten Schwab callExpDateMap / putExpDateMap structures into a list of option dicts."""
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
                volume = int(item.get('totalVolume', 0) or 0)
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


def _validate_range(name: str, value, *, lo, hi, typ) -> None:
    """Raise ValueError if *value* is not an instance of *typ* within [lo, hi]."""
    if not isinstance(value, typ) or not (lo <= value <= hi):
        typ_name = '/'.join(t.__name__ for t in typ) if isinstance(typ, tuple) else typ.__name__
        raise ValueError(
            f"Invalid {name}: {value}. Must be a {typ_name} between {lo} and {hi}."
        )


def _validate_chain_params(symbol: str, min_dte: int | None, max_dte: int | None,
                            min_delta: float | None, max_delta: float | None) -> None:
    """Validate DTE, Delta, and symbol parameters, raising ValueError for malicious or out-of-bounds values."""
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


def _fetch_chains(access_token: str, params: dict) -> dict | None:
    """GET /marketdata/v1/chains and return parsed JSON, or None on error."""
    headers = _schwab_headers(access_token)
    url = "https://api.schwabapi.com/marketdata/v1/chains"
    try:
        return schwab_request("GET", url, headers=headers, params=params)
    except requests.exceptions.RequestException as e:
        logging.error("Network error fetching chains: %s", e)
        return None


def fetch_option_chain(access_token: str, symbol: str, contract_type: str = 'CALL',
                       min_dte: int | None = None, max_dte: int | None = None,
                       min_delta: float | None = None, max_delta: float | None = None) -> dict:
    """Fetch options chain from Schwab API, filter by DTE and delta, and return structured format."""
    _validate_chain_params(symbol, min_dte, max_dte, min_delta, max_delta)

    today = datetime.datetime.now(SCHWAB_TZ).date()

    from_date = (today + datetime.timedelta(days=min_dte)).isoformat() if min_dte is not None and min_dte >= 0 else None
    to_date = (today + datetime.timedelta(days=max_dte)).isoformat() if max_dte is not None and max_dte >= 0 else None

    params = {
        'symbol': symbol,
        'contractType': contract_type if contract_type in ('CALL', 'PUT', 'ALL') else 'ALL',
        'includeUnderlyingQuote': True
    }
    if from_date:
        params['fromDate'] = from_date
    if to_date:
        params['toDate'] = to_date

    empty = {
        'underlying': {'symbol': symbol, 'price': 0.0, 'change': 0.0, 'percentChange': 0.0},
        'chain': [],
        'totalContracts': 0
    }
    data = _fetch_chains(access_token, params)
    if data is None:
        return empty

    underlying_data = data.get('underlying', {})
    stock_price = float(underlying_data.get('last', 0.0) or underlying_data.get('mark', 0.0) or 0.0)

    underlying_info = {
        'symbol': symbol,
        'price': stock_price,
        'change': float(underlying_data.get('change', 0.0) or 0.0),
        'percentChange': float(underlying_data.get('percentChange', 0.0) or 0.0)
    }

    chain = []
    if 'callExpDateMap' in data:
        chain.extend(_parse_exp_map(data['callExpDateMap'], stock_price, 'CALL'))
    if 'putExpDateMap' in data:
        chain.extend(_parse_exp_map(data['putExpDateMap'], stock_price, 'PUT'))

    total_contracts = len(chain)

    filtered_chain = [
        opt for opt in chain
        if (min_dte is None or opt['dte'] >= min_dte)
        and (max_dte is None or opt['dte'] <= max_dte)
        and (min_delta is None or opt['delta'] >= min_delta)
        and (max_delta is None or opt['delta'] <= max_delta)
    ]

    filtered_chain.sort(key=lambda x: (x['expirationDate'], x['strikePrice'], x['contractType']))

    return {
        'underlying': underlying_info,
        'chain': filtered_chain,
        'totalContracts': total_contracts
    }

def fetch_spx_boxes(access_token: str, from_date: str | None, to_date: str | None, sizes: list[int] | None = None) -> list[dict]:
    """Fetch SPX option chains and identify box spreads."""
    params = {
        'symbol': '$SPX',
        'contractType': 'ALL',
        'includeUnderlyingQuote': False
    }
    if from_date:
        params['fromDate'] = from_date
    if to_date:
        params['toDate'] = to_date

    data = _fetch_chains(access_token, params)
    if data is None:
        return []

    calls_map = data.get('callExpDateMap', {})
    puts_map = data.get('putExpDateMap', {})

    # Reuse _parse_exp_map to extract mark/dte/openInterest uniformly.
    # stock_price=0.0 because includeUnderlyingQuote is False;
    # change/beChange/mpr are not used in box spread calculations.
    all_contracts = (
        _parse_exp_map(calls_map, 0.0, 'CALL') +
        _parse_exp_map(puts_map,  0.0, 'PUT')
    )

    # Keep only monthly SPX contracts (exclude SPXW weeklies) with open interest.
    monthly = [
        c for c in all_contracts
        if c['symbol'].startswith('SPX  ') and c['openInterest'] > 0
    ]

    # Index by (expiration_date, strike) -> {contract_type: {mark, oi, dte}}
    options_by_exp_strike: dict = {}
    for c in monthly:
        key = (c['expirationDate'], c['strikePrice'])
        if key not in options_by_exp_strike:
            options_by_exp_strike[key] = {}
        options_by_exp_strike[key][c['contractType']] = {
            'mark': c['mark'],
            'oi':   c['openInterest'],
            'dte':  c['dte'],
        }

    boxes = []
    if sizes is None or not sizes:
        sizes = [100, 200, 500, 1000]

    for (exp_date, lower_strike), legs in options_by_exp_strike.items():
        if 'CALL' not in legs or 'PUT' not in legs:
            continue

        lower_call = legs['CALL']
        lower_put  = legs['PUT']
        dte = lower_call['dte']
        if dte <= 0:
            continue

        for size in sizes:
            higher_strike = lower_strike + size
            higher_key = (exp_date, higher_strike)

            if higher_key not in options_by_exp_strike:
                continue

            higher_legs = options_by_exp_strike[higher_key]
            if 'CALL' not in higher_legs or 'PUT' not in higher_legs:
                continue

            higher_call = higher_legs['CALL']
            higher_put  = higher_legs['PUT']

            liquidity = lower_call['oi'] + lower_put['oi'] + higher_call['oi'] + higher_put['oi']
            net_credit = (lower_call['mark'] - higher_call['mark']) + (higher_put['mark'] - lower_put['mark'])

            if net_credit <= 0:
                continue

            rate = (((size - net_credit) / net_credit) * (365.0 / dte) * 100.0)

            boxes.append({
                'expirationDate': exp_date,
                'dte':       dte,
                'btoPut':    lower_strike,
                'stoPut':    higher_strike,
                'stoCall':   lower_strike,
                'btoCall':   higher_strike,
                'netCredit': net_credit,
                'rate':      rate,
                'size':      size,
                'liquidity': liquidity,
            })

    boxes.sort(key=lambda x: x['liquidity'], reverse=True)
    return boxes[:15]


# ---------------------------------------------------------------------------
# Network helpers — accounts
# ---------------------------------------------------------------------------

SCHWAB_TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"


def fetch_accounts_raw(access_token: str) -> list:
    """Fetch raw account data (with positions) from the Schwab Trader API."""
    headers = _schwab_headers(access_token)
    return schwab_request(
        "GET",
        f"{SCHWAB_TRADER_BASE_URL}/accounts",
        headers=headers,
        params={"fields": "positions"},
    )


# ---------------------------------------------------------------------------
# Private computation helpers
# ---------------------------------------------------------------------------

def _parse_position(pos: dict, acc_num: str) -> dict | None:
    """Convert one raw Schwab position into our internal dict."""
    symbol    = pos.get('instrument', {}).get('symbol')
    asset_type = pos.get('instrument', {}).get('assetType')
    if not symbol:
        return None

    long_qty  = pos.get('longQuantity', 0.0)
    short_qty = pos.get('shortQuantity', 0.0)
    qty       = long_qty - short_qty

    market_value = pos.get('marketValue', 0.0)
    pl = (pos.get('shortOpenProfitLoss') or 0.0) + (pos.get('longOpenProfitLoss') or 0.0)
    cost = market_value - pl

    multiplier  = get_option_multiplier(symbol)
    value_share = (market_value / qty / multiplier) if qty != 0 else 0.0

    return {
        'accountNumber': acc_num,
        'symbol':        symbol,
        'assetType':     asset_type,
        'quantity':      qty,
        'cost/share':    pos.get('averagePrice', 0.0),
        'value/share':   value_share,
        'marketValue':   market_value,
        'P/L':           pl,
        'cost':          cost,
    }


def _group_spx(spx_positions: list, acc_num: str) -> tuple[list, float]:
    """Merge SPX legs by 12-char prefix and compute the box loan."""
    groups: dict[str, dict] = {}
    for pos in spx_positions:
        key = pos['symbol'][:12]
        if key not in groups:
            groups[key] = {
                'accountNumber': acc_num,
                'symbol':        key,
                'assetType':     'OPTION',
                'quantity':      1,
                'cost':          0.0,
                'marketValue':   0.0,
                'cost/share':    0.0,
                'value/share':   0.0,
                'P/L':           0.0,
            }
        g = groups[key]
        g['cost']        += pos['cost']
        g['marketValue'] += pos['marketValue']
        g['P/L']         += pos['P/L']

    grouped = list(groups.values())
    box_loan = sum(
        round(g['cost'] / _SPX_BOX_ROUNDING) * _SPX_BOX_ROUNDING for g in grouped
    )
    return grouped, box_loan


def _is_short_put(pos: dict) -> bool:
    """Return True if *pos* is a short put position (negative qty, put contract)."""
    symbol = pos['symbol']
    return pos['quantity'] < 0 and len(symbol) > 12 and symbol[12] == 'P'


def _enrich_positions(positions: list) -> float:
    """
    Add P/L%, dte, and CSP contribution to each position in-place.
    Returns the total CSP (cash-secured put liability).
    """
    csp = 0.0
    for pos in positions:
        symbol = pos['symbol']
        cost   = pos['cost']
        pl     = pos['P/L']
        pos['P/L%'] = (pl / abs(cost) * 100.0) if cost != 0 else 0.0

        if is_option(symbol) and len(symbol) > 10:
            try:
                opt = OptionSymbol.parse_symbol(symbol)
                pos['dte'] = opt.dte()
                # CSP: short puts only
                if _is_short_put(pos):
                    csp += float(opt.strike_price) * pos['quantity'] * 100.0
            except Exception as e:
                logging.error("Error enriching option %s: %s", symbol, e)
                pos['dte'] = -1
        else:
            pos['dte'] = -1

    return csp


def _compute_todo(positions: list, quotes: dict | None = None) -> dict[str, str]:
    """
    Return a mapping {accountNumber: "action1, action2"} for action items:
    1. STO # x symbol (markPercentChange of underlying) for uncovered stocks/ETFs
    2. BTC # x option symbol (total gain) for sold calls with P/L% >= 60%
    Excludes tickers in _TODO_EXCLUDE.
    """
    if quotes is None:
        quotes = {}

    underlying_mark_pct: dict[str, float] = {}
    for pos in positions:
        sym = pos['symbol']
        if not is_option(sym):
            underlying_mark_pct[sym] = pos.get('markPercentChange', 0.0)

    for sym, q_data in quotes.items():
        if not is_option(sym) and sym not in underlying_mark_pct:
            q_fields = q_data.get('quote', {}) if isinstance(q_data, dict) else {}
            underlying_mark_pct[sym] = float(q_fields.get('markPercentChange', 0.0) or 0.0)

    for pos in positions:
        pos['action'] = ''

    # Dictionary to collect action strings per account
    actions_by_account: dict[str, list] = {}

    net: dict[tuple, int] = {}
    for pos in positions:
        acc        = pos['accountNumber']
        symbol     = pos['symbol']
        qty        = pos['quantity']
        underlying = _base_symbol(symbol)
        key        = (acc, underlying)

        is_put = len(symbol) > 12 and symbol[12] == 'P'
        qty = 0 if is_put else int(qty * get_option_multiplier(symbol) / 100)
        net[key] = net.get(key, 0) + qty

    for (acc, underlying), uncovered in net.items():
        if underlying not in _TODO_EXCLUDE and uncovered > 0:
            pct = underlying_mark_pct.get(underlying, 0.0)
            pct_str = f"{pct:+.2f}%"
            actions_by_account.setdefault(acc, []).append(
                f"STO {underlying} ({pct_str})"
            )
            for pos in positions:
                if (pos['accountNumber'] == acc and
                    not is_option(pos['symbol']) and
                    _base_symbol(pos['symbol']) == underlying and
                    pos['quantity'] > 0):
                    pos['action'] = f"STO {underlying}"

    # 2. Sold call options rules: BTC (P/L% >= 60% or delta < 0.10) and ROLLOUT (delta > 0.50)
    for pos in positions:
        acc    = pos['accountNumber']
        symbol = pos['symbol']
        qty    = pos['quantity']
        pl_pct = pos.get('P/L%', 0.0)
        delta  = pos.get('delta', 0.0)
        dte    = pos.get('dte', -1)
        mpr    = pos.get('mpr', 0.0)

        if is_option(symbol) and qty < 0:
            try:
                opt = OptionSymbol.parse_symbol(symbol)
                if opt.contract_type == 'C':

                    # BTC rule: total gain >= 60% OR (0.0 < delta < 0.10)
                    if pl_pct >= 60.0 or (0.0 < delta < 0.10):
                        actions_by_account.setdefault(acc, []).append(
                            f"BTC {symbol} ({delta:.2f}, {dte}d, {mpr:.2f}%)"
                        )
                        pos['action'] = f"BTC {symbol}"

                    if delta > 0.50:
                        actions_by_account.setdefault(acc, []).append(
                            f"ROLL {symbol} ({delta:.2f}, {dte}d, {mpr:.2f}%)"
                        )
                        pos['action'] = f"ROLL {symbol}"
            except Exception as e:
                logging.warning("Could not parse option symbol %s for action check: %s", symbol, e)

    return {acc: "; ".join(items) for acc, items in actions_by_account.items()}


def _enrich_quotes(positions: list, quotes: dict) -> None:
    """Merge delta, MPR, and markPercentChange from *quotes* into *positions* in-place."""
    for pos in positions:
        symbol = pos['symbol']
        pos['delta'] = 0.0
        pos['mpr']   = 0.0
        pos['markPercentChange'] = 0.0

        quote_fields = quotes.get(symbol, {}).get('quote', {})
        if not quote_fields:
            continue

        pos['delta'] = quote_fields.get('delta', 0.0) or 0.0
        pos['markPercentChange'] = float(quote_fields.get('markPercentChange', 0.0) or 0.0)

        if len(symbol) > 12:
            try:
                bid = quote_fields.get('bidPrice', 0.0) or 0.0
                up  = quote_fields.get('underlyingPrice', 0.0) or 0.0
                opt = OptionSymbol.parse_symbol(symbol)
                dte = opt.dte()
                strike = float(opt.strike_price)

                if opt.contract_type == 'C':
                    time_value = bid - max(0.0, up - strike)
                else:
                    time_value = bid - max(0.0, strike - up)

                if dte > 0 and up > 0:
                    pos['mpr'] = (time_value * 3000.0) / dte / up
            except Exception as e:
                logging.error("Error calculating MPR for %s: %s", symbol, e)



# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_accounts_data(accounts_json: list, access_token: str) -> dict:
    """
    Parse raw Schwab account JSON, enrich with quotes and orders,
    and return a structured dashboard payload.
    """
    global_positions: list = []
    account_summaries: list = []
    account_nums: list = []

    for account in accounts_json:
        sec = account.get('securitiesAccount', {})
        acc_num = sec.get('accountNumber')
        if not acc_num:
            continue
        account_nums.append(acc_num)

        # --- Parse raw positions ---
        parsed = [p for p in
                  (_parse_position(raw, acc_num) for raw in sec.get('positions', []))
                  if p is not None]

        # --- Group SPX box spreads ---
        spx     = [p for p in parsed if p['symbol'].startswith('SPX')]
        non_spx = [p for p in parsed if not p['symbol'].startswith('SPX')]
        grouped_spx, box_loan = _group_spx(spx, acc_num)
        account_positions = non_spx + grouped_spx

        # --- Add P/L%, DTE, and compute CSP in one pass ---
        csp = _enrich_positions(account_positions)

        # --- Balance fields ---
        bal    = sec.get('currentBalances', {})
        cash   = bal.get('cashBalance', 0.0)
        net    = bal.get('liquidationValue', 0.0)
        margin = bal.get('marginBalance', 0.0)
        maint  = bal.get('maintenanceRequirement', 0.0)
        equity = bal.get('equity', 0.0)

        risk = 100.0 + (2250.0 * box_loan / equity / 7.0 if equity else 0.0)

        account_summaries.append({
            'accountNumber': acc_num,
            'Short P/L':    sum(p['P/L']         for p in account_positions if p['quantity'] < 0),
            'Short Value':  sum(p['marketValue']  for p in account_positions if p['quantity'] < 0),
            'Cash':         cash,
            'Total':        sum(p['marketValue']  for p in account_positions),
            'Net':          net,
            'Margin':       margin,
            'CSP':          csp,
            'BOX':          box_loan,
            'MaintReq':     maint,
            'Risk':         risk,
            'Total Loan':   margin + box_loan + csp,
            'Todo':         '',   # filled in below
        })
        global_positions.extend(account_positions)

    # --- Quotes → delta + MPR + markPercentChange ---
    unique_symbols = list({p['symbol'] for p in global_positions})
    quotes = fetch_quotes(access_token, unique_symbols)
    _enrich_quotes(global_positions, quotes)

    # --- Actions (STO & BTC rules) ---
    todo_map = _compute_todo(global_positions, quotes)
    for summary in account_summaries:
        summary['Todo'] = todo_map.get(summary['accountNumber'], '')

    # --- Active orders ---
    active_orders = fetch_active_orders(access_token, account_nums)
    global_positions.sort(key=lambda x: (x['accountNumber'], x['dte'], x['symbol']))

    return {
        'positions': global_positions,
        'summaries': account_summaries,
        'orders':    active_orders,
    }
