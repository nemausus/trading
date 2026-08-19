"""
realized_pl.py
~~~~~~~~~~~~~~
Service module for normalizing raw transactions and calculating realized
profit/loss using FIFO (First-In, First-Out) matching.
"""

import logging

logger = logging.getLogger(__name__)


def normalize_transactions(txns: list[dict]) -> list[dict]:
    """Normalize Firestore raw transactions into a flat representation for calculations.

    Args:
        txns: List of raw transaction dictionaries from Firestore.

    Returns:
        List of normalized transaction dictionaries.
    """
    rows = []
    for txn in txns:
        txn_type = txn.get('type')
        net_amount = txn.get('netAmount', 0.0)
        time_str = txn.get('time')
        if time_str:
            time_str = time_str[:10]
        account_num = txn.get('accountNumber')

        transfer_items = txn.get('transferItems', [])
        for item in transfer_items:
            if not item:
                continue
            instrument = item.get('instrument', {}) or {}
            pos_effect = item.get('positionEffect')

            is_valid = False
            if pos_effect is not None:
                is_valid = True
            elif txn_type == 'DIVIDEND_OR_INTEREST' and net_amount < 0:
                is_valid = True
                pos_effect = 'INTEREST'

            if not is_valid:
                continue

            symbol = instrument.get('symbol', '')
            if symbol.startswith('SPX'):
                continue
            instrument_id = instrument.get('instrumentId', '')
            amount = item.get('amount', 0.0)
            cost = item.get('cost', 0.0)
            price = item.get('price', 0.0)

            if ((amount < 0 and pos_effect == 'OPENING') or
                    (amount > 0 and pos_effect == 'CLOSING')):
                sl = 'short'
            else:
                sl = 'long'

            rows.append({
                'accountNumber': account_num,
                'time': time_str,
                'symbol': symbol,
                'instrumentId': instrument_id,
                'amount': amount,
                'cost': cost,
                'price': price,
                'netAmount': net_amount,
                'positionEffect': pos_effect,
                'sl': sl
            })
    return rows


def calculate_realized_pl(txns: list[dict]) -> list[dict]:
    """Calculate realized gain and losses using FIFO matching.

    Args:
        txns: List of raw transaction dictionaries from Firestore.

    Returns:
        List of realized gain/loss records sorted by sell_date descending.
    """
    rows = normalize_transactions(txns)

    # Group transactions by key fields to consolidate partial fills
    aggregated: dict = {}
    for r in rows:
        key = (
            r['accountNumber'],
            r['time'],
            r['symbol'],
            r['instrumentId'],
            r['positionEffect'],
            r['sl']
        )
        if key not in aggregated:
            aggregated[key] = {
                'amount_sum': r['amount'],
                'cost_sum': r['cost'],
                'price_list': [r['price']],
                'netAmount_sum': r['netAmount']
            }
        else:
            aggregated[key]['amount_sum'] += r['amount']
            aggregated[key]['cost_sum'] += r['cost']
            aggregated[key]['price_list'].append(r['price'])
            aggregated[key]['netAmount_sum'] += r['netAmount']

    grouped_rows = []
    for key, val in aggregated.items():
        avg_price = sum(val['price_list']) / len(val['price_list']) if val['price_list'] else 0.0
        grouped_rows.append({
            'accountNumber': key[0],
            'time': key[1],
            'symbol': key[2],
            'positionEffect': key[4],
            'sl': key[5],
            'amount': abs(val['amount_sum']),
            'cost': val['cost_sum'],
            'price': avg_price,
            'netAmount': val['netAmount_sum']
        })

    # Two-pass stable sort:
    # 1. Sort by positionEffect descending so OPENING processed before CLOSING.
    # 2. Sort by (accountNumber, time) ascending.
    grouped_rows.sort(key=lambda x: x['positionEffect'] or '', reverse=True)
    grouped_rows.sort(key=lambda x: (x['accountNumber'] or '', x['time'] or ''))

    opened: dict[str, list] = {}
    result = []

    for row in grouped_rows:
        key = f"{row['accountNumber']}_{row['symbol']}_{row['sl']}"

        if row['positionEffect'] == 'INTEREST':
            result.append({
                'accountNumber': row['accountNumber'],
                'amount': 1.0,
                'symbol': 'MARGIN INTEREST',
                'buy_date': row['time'],
                'buy_price': row['netAmount'],
                'sell_date': row['time'],
                'sell_price': 0.0,
                'P/L': row['netAmount']
            })
        elif row['positionEffect'] == 'OPENING':
            if key in opened:
                opened[key].append(row)
            else:
                opened[key] = [row]
        elif row['positionEffect'] == 'CLOSING':
            while key in opened and len(opened[key]) > 0:
                o = opened[key].pop(0)
                matched_quantity = min(o['amount'], row['amount'])

                unit_net_o = o['netAmount'] / o['amount'] if o['amount'] else 0.0
                unit_net_row = row['netAmount'] / row['amount'] if row['amount'] else 0.0
                realized_pl = (unit_net_o + unit_net_row) * matched_quantity

                result.append({
                    'accountNumber': o['accountNumber'],
                    'amount': matched_quantity,
                    'symbol': o['symbol'],
                    'buy_date': o['time'],
                    'buy_price': o['price'],
                    'sell_date': row['time'],
                    'sell_price': row['price'],
                    'P/L': realized_pl
                })

                if o['amount'] > row['amount']:
                    o['amount'] = o['amount'] - row['amount']
                    o['netAmount'] = unit_net_o * o['amount']
                    opened[key].insert(0, o)
                    break
                elif o['amount'] < row['amount']:
                    row['amount'] = row['amount'] - o['amount']
                    row['netAmount'] = unit_net_row * row['amount']

                if len(opened[key]) == 0:
                    opened.pop(key)

    result.sort(key=lambda x: x['sell_date'] or '', reverse=True)
    return result
