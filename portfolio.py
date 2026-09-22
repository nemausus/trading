import datetime
import logging

from constants import SCHWAB_TZ, get_account_hash, _fval
import schwab_api
from schwab_api import SchwabAPIError
from option_symbol import (
    OptionSymbol,
    _parse_expiration_date,
    is_option,
    get_option_multiplier,
    base_symbol,
)

# Backward-compatibility alias
_base_symbol = base_symbol

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Instruction abbreviations shared by fetch_active_orders and callers
INS_MAP = {
    'BUY_TO_CLOSE': 'BTC',
    'SELL_TO_OPEN': 'STO',
    'BUY_TO_OPEN': 'BTO',
    'SELL_TO_CLOSE': 'STC',
    'GOOD_TILL_CANCEL': 'GTC',
}


# Rounding unit for SPX box spread loan calculation ($10k increments).
_SPX_BOX_ROUNDING = 10_000.0

# Tickers excluded from the uncovered-long (Todo) list
_TODO_EXCLUDE = frozenset(('QQQM', 'VTI', 'SNOW', 'SPX'))

# Strategy thresholds for action recommendations
_BTC_PROFIT_TAKE_PCT = 60.0
_BTC_DELTA_LOW_THRESHOLD = 0.10
_ROLLOUT_DELTA_HIGH_THRESHOLD = 0.50
_MPR_ANNUALIZATION_FACTOR = 3000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# Network helpers
# ---------------------------------------------------------------------------

def fetch_quotes(access_token: str, symbols: list) -> dict:
    """Fetch real-time quotes for *symbols*."""
    if not symbols:
        return {}

    assert len(symbols) < 100, f"Too many symbols to fetch at once: {len(symbols)}"

    data = schwab_api.get_quotes(access_token, symbols)
    return data if isinstance(data, dict) else {}


def fetch_active_orders(access_token: str, account_nums: list) -> list:
    """Fetch open (no closeTime) orders for every account in *account_nums*."""
    from_date = to_iso_datetime_str(
        (datetime.datetime.now(SCHWAB_TZ) - datetime.timedelta(days=7)).date().isoformat()
    )
    to_date = datetime.datetime.now(SCHWAB_TZ).isoformat()
    active_orders: list = []

    for acc_num in account_nums:
        acc_hash = get_account_hash(acc_num)
        try:
            orders_data = schwab_api.get_orders(
                access_token,
                acc_hash,
                from_entered_time=from_date,
                to_entered_time=to_date,
            )
            if not isinstance(orders_data, list):
                continue

            for order in orders_data:
                if order.get('closeTime') is not None:
                    continue
                price      = order.get('price')
                status     = INS_MAP.get(order.get('status'), order.get('status'))
                duration   = INS_MAP.get(order.get('duration'), order.get('duration'))
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
        except SchwabAPIError as e:
            logging.error("Error fetching orders for account %s: %s", acc_num, e)

    return active_orders


# ---------------------------------------------------------------------------
# Network helpers — accounts
# ---------------------------------------------------------------------------


def fetch_accounts_raw(access_token: str) -> list:
    """Fetch raw account data (with positions) from the Schwab Trader API."""
    return schwab_api.get_accounts(access_token, fields="positions")


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
    symbol = pos.get('symbol', '')
    if pos.get('quantity', 0.0) >= 0 or not is_option(symbol):
        return False
    try:
        opt = OptionSymbol.parse_symbol(symbol)
        return opt.contract_type == 'P'
    except Exception:
        return False


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

        if is_option(symbol) and len(symbol) > 12:
            try:
                opt = OptionSymbol.parse_symbol(symbol)
                pos['dte'] = opt.dte()
                # CSP: short puts only
                if _is_short_put(pos):
                    csp += float(opt.strike_price) * pos['quantity'] * 100.0
            except Exception as e:
                logging.error("Error enriching option %s: %s", symbol, e)
                pos['dte'] = -1
        elif len(symbol) == 12 and symbol.startswith('SPX'):
            try:
                exp_date = _parse_expiration_date(symbol[6:12])
                today = datetime.datetime.now(SCHWAB_TZ).date()
                pos['dte'] = int((exp_date - today).days)
            except Exception as e:
                logging.error("Error enriching SPX box %s: %s", symbol, e)
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

        is_put = False
        if is_option(symbol):
            try:
                opt = OptionSymbol.parse_symbol(symbol)
                is_put = (opt.contract_type == 'P')
            except Exception:
                pass

        qty = 0 if is_put else int(qty * get_option_multiplier(symbol) / 100)
        net[key] = net.get(key, 0) + qty

    for (acc, underlying), uncovered in net.items():
        if underlying not in _TODO_EXCLUDE and uncovered > 0:
            pct = underlying_mark_pct.get(underlying, 0.0)
            pct_str = f"{pct:+.2f}%"
            actions_by_account.setdefault(acc, []).append(
                f"STO {uncovered}x {underlying} ({pct_str})"
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
                    opt_qty_str = f"{abs(int(qty))}x "

                    # BTC rule: total gain >= 60% OR (0.0 < delta < 0.10)
                    if pl_pct >= _BTC_PROFIT_TAKE_PCT or (0.0 < delta < _BTC_DELTA_LOW_THRESHOLD):
                        actions_by_account.setdefault(acc, []).append(
                            _opt_action_str('BTC', opt_qty_str, symbol, delta, dte, mpr)
                        )
                        pos['action'] = f"BTC {symbol}"

                    if delta > _ROLLOUT_DELTA_HIGH_THRESHOLD:
                        actions_by_account.setdefault(acc, []).append(
                            _opt_action_str('ROLLOUT', opt_qty_str, symbol, delta, dte, mpr)
                        )
                        pos['action'] = f"ROLL {symbol}"
            except Exception as e:
                logging.warning("Could not parse option symbol %s for action check: %s", symbol, e)


    return {acc: "; ".join(items) for acc, items in actions_by_account.items()}


def _opt_action_str(prefix: str, qty_str: str, symbol: str, delta: float, dte: int, mpr: float) -> str:
    """Format a BTC/ROLLOUT action string for display in the Todo field."""
    return f"{prefix} {qty_str}{symbol} ({delta:.2f}, {dte}d, {mpr:.2f}%)"


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

        pos['delta'] = _fval(quote_fields, 'delta')
        pos['markPercentChange'] = _fval(quote_fields, 'markPercentChange')

        if is_option(symbol):
            try:
                bid = _fval(quote_fields, 'bidPrice')
                up  = _fval(quote_fields, 'underlyingPrice')
                opt = OptionSymbol.parse_symbol(symbol)
                dte = opt.dte()
                strike = float(opt.strike_price)

                if opt.contract_type == 'C':
                    time_value = bid - max(0.0, up - strike)
                else:
                    time_value = bid - max(0.0, strike - up)

                if dte > 0 and up > 0:
                    pos['mpr'] = (time_value * _MPR_ANNUALIZATION_FACTOR) / dte / up
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
