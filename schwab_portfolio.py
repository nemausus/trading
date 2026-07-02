import datetime
import logging
import requests

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

OPTION_MULTIPLIER = 100
SCHWAB_REQUEST_TIMEOUT = (5, 30)
SCHWAB_TZ = datetime.timezone(-datetime.timedelta(hours=7, minutes=30))

# Instruction abbreviations shared by fetch_active_orders and callers
INS_MAP = {
    'BUY_TO_CLOSE': 'BTC',
    'SELL_TO_OPEN': 'STO',
    'BUY_TO_OPEN': 'BTO',
    'SELL_TO_CLOSE': 'STC',
    'GOOD_TILL_CANCEL': 'GTC',
}

# Position fields to copy onto merged orders
_ORDER_POSITION_FIELDS = ('quantity', 'cost/share', 'value/share',
                          'P/L', 'P/L%', 'dte', 'delta', 'mpr')

# Tickers excluded from the uncovered-long (Todo) list
_TODO_EXCLUDE = frozenset(('QQQM', 'VTI', 'SNOW', 'SPX'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    except Exception:
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

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    quotes: dict = {}

    for i in range(0, len(symbols), 200):
        chunk = ",".join(symbols[i:i + 200])
        try:
            res = requests.get(
                "https://api.schwabapi.com/marketdata/v1/quotes",
                headers=headers,
                params={'symbols': chunk},
                timeout=SCHWAB_REQUEST_TIMEOUT,
            )
            if res.status_code == 200:
                quotes.update(res.json())
            else:
                logging.error("Error fetching quotes: %s %s", res.status_code, res.text)
        except Exception as e:
            logging.error("Failed to fetch quotes: %s", e)

    return quotes


def fetch_active_orders(access_token: str, account_hashes: list) -> list:
    """Fetch open (no closeTime) orders for every account in *account_hashes*."""
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    from_date = to_iso_datetime_str(
        (datetime.datetime.now(SCHWAB_TZ) - datetime.timedelta(days=7)).date().isoformat()
    )
    active_orders: list = []

    for acc_hash in account_hashes:
        try:
            res = requests.get(
                f"https://api.schwabapi.com/trader/v1/accounts/{acc_hash}/orders",
                headers=headers,
                params={'fromEnteredTime': from_date,
                        'toEnteredTime': datetime.datetime.now(SCHWAB_TZ).isoformat()},
                timeout=SCHWAB_REQUEST_TIMEOUT,
            )
            if res.status_code != 200:
                continue
            orders_data = res.json()
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
                        'accountNumber': acc_hash,
                        'symbol':    leg.get('instrument', {}).get('symbol'),
                        'type':      INS_MAP.get(leg.get('instruction'), leg.get('instruction')),
                        'quantity':  leg.get('quantity'),
                        'price':     price,
                        'status':    status,
                        'duration':  duration,
                        'orderType': order_type,
                    })
        except Exception as e:
            logging.error("Error fetching orders for account %s: %s", acc_hash, e)

    return active_orders


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
    box_loan = sum(round(g['cost'] / 10000.0) * 10000.0 for g in grouped)
    return grouped, box_loan


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
                # CSP: short puts only (qty < 0, char at index 12 == 'P')
                if pos['quantity'] < 0 and len(symbol) > 12 and symbol[12] == 'P':
                    csp += float(opt.strike_price) * pos['quantity'] * 100.0
            except Exception as e:
                logging.error("Error enriching option %s: %s", symbol, e)
                pos['dte'] = -1
        else:
            pos['dte'] = -1

    return csp


def _compute_todo(positions: list) -> dict[str, str]:
    """
    Return a mapping {accountNumber: "Nx SYM, Mx SYM2"} for uncovered longs.
    Excludes tickers in _TODO_EXCLUDE.
    """
    # net[key] = contracts_long - contracts_short_call  (positive = uncovered)
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

    todo_by_account: dict[str, list] = {}
    for (acc, underlying), uncovered in net.items():
        if underlying not in _TODO_EXCLUDE and uncovered > 0:
            todo_by_account.setdefault(acc, []).append(f"{uncovered}x {underlying}")

    return {acc: ", ".join(items) for acc, items in todo_by_account.items()}


def _enrich_quotes(positions: list, quotes: dict) -> None:
    """Merge delta and MPR from *quotes* into *positions* in-place."""
    for pos in positions:
        symbol = pos['symbol']
        pos['delta'] = 0.0
        pos['mpr']   = 0.0

        quote_fields = quotes.get(symbol, {}).get('quote', {})
        if not quote_fields:
            continue

        pos['delta'] = quote_fields.get('delta', 0.0) or 0.0

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
    account_hashes: list = []

    for account in accounts_json:
        sec = account.get('securitiesAccount', {})
        acc_num = sec.get('accountNumber')
        if not acc_num:
            continue

        account_hashes.append(acc_num)

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

    # --- Todo (uncovered longs) ---
    todo_map = _compute_todo(global_positions)
    for summary in account_summaries:
        summary['Todo'] = todo_map.get(summary['accountNumber'], '')

    # --- Quotes → delta + MPR ---
    unique_symbols = list({p['symbol'] for p in global_positions})
    quotes = fetch_quotes(access_token, unique_symbols)
    _enrich_quotes(global_positions, quotes)

    # --- Active orders merged with positions ---
    pos_index = {(p['accountNumber'], p['symbol']): p for p in global_positions}
    active_orders = fetch_active_orders(access_token, account_hashes)
    merged_orders = []
    for order in active_orders:
        pos = pos_index.get((order['accountNumber'], order['symbol']), {})
        merged_orders.append({
            'accountNumber': order['accountNumber'],
            'symbol':        order['symbol'],
            'order':         f"{order['type']} {int(order['quantity'])} @ {order['price']}",
            **{f: pos.get(f) for f in _ORDER_POSITION_FIELDS},
        })

    global_positions.sort(key=lambda x: (x['accountNumber'], x['dte'], x['symbol']))

    return {
        'positions': global_positions,
        'summaries': account_summaries,
        'orders':    merged_orders,
    }
