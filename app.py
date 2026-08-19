import logging
import os
import secrets
import datetime
import urllib.parse
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, make_response
from firebase_admin import auth
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import firestore_db
from constants import get_primary_account_hash
from schwab_auth import SchwabAuthManager
import schwab_portfolio
import schwab_transactions


schwab_auth = SchwabAuthManager()

# app must be defined before Talisman/Limiter and before decorators that reference it.
app = Flask(__name__)


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def require_firebase_auth(f):
    """Verify a Firebase Bearer token and pass the decoded payload to the view."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized - Missing Header'}), 401

        token = auth_header.split('Bearer ')[1].strip()
        try:
            decoded_token = auth.verify_id_token(token)
        except Exception as e:
            logging.warning("Token verification failed: %s", e)
            return jsonify({'error': 'Unauthorized - Invalid or expired token'}), 401
        return f(decoded_token, *args, **kwargs)
    return decorated_function


def require_schwab_token(f):
    """Resolve and inject a valid Schwab access token.

    Must be stacked *inside* @require_firebase_auth so that decoded_token is
    already available.  Injects ``access_token`` as the second positional
    argument to the wrapped view.
    """
    @wraps(f)
    def decorated(decoded_token, *args, **kwargs):
        uid = decoded_token.get('uid')
        if not uid:
            return jsonify({'error': 'Unauthorized - Missing uid'}), 401
        access_token = schwab_auth.refresh_user_tokens_if_needed(uid)
        if not access_token:
            return jsonify({'error': 'Schwab account not connected or failed to refresh session'}), 400
        return f(decoded_token, access_token, *args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Security middleware
# ---------------------------------------------------------------------------

# Configure Content Security Policy (CSP) to allow Firebase SDK loading
csp = {
    'default-src': '\'self\'',
    'script-src': [
        '\'self\'',
        'https://www.gstatic.com'
    ],
    'style-src': [
        '\'self\'',
        '\'unsafe-inline\''
    ],
    'connect-src': [
        '\'self\'',
        'https://*.googleapis.com',
        'https://*.firebaseapp.com'
    ]
}

# Apply Talisman for secure headers.
# HTTPS redirection is disabled in local debug or development environments.
Talisman(
    app,
    content_security_policy=csp,
    force_https=not (app.debug or os.environ.get('FLASK_ENV') == 'development')
)

# Initialize Flask-Limiter for rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


def redirect_error(message: str):
    err_msg = urllib.parse.quote(message)
    return redirect(f'/?schwab=error&message={err_msg}')


def _get_limit(default: int, cap: int) -> int:
    """Parse and cap the 'limit' query-string parameter."""
    return min(request.args.get('limit', default=default, type=int), cap)


@app.route('/api/auth/schwab', methods=['POST'])
@limiter.limit("5 per minute")
@require_firebase_auth
def schwab_authorize(decoded_token):
    uid = decoded_token['uid']

    # Generate secure random state
    state = secrets.token_urlsafe(16)

    # Store state -> uid in Firestore with expiration (10 minutes)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    firestore_db.save_schwab_auth_state(state, uid, expires_at)

    # Build Schwab authorization URL
    params = {
        'client_id': schwab_auth.client_id,
        'redirect_uri': schwab_auth.redirect_uri,
        'response_type': 'code',
        'state': state
    }
    auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?{urllib.parse.urlencode(params)}"

    response = jsonify({'url': auth_url})
    response.set_cookie('schwab_oauth_state', state, httponly=True, secure=True, samesite='Lax', max_age=600)
    return response


@app.route('/api/auth/schwab/callback')
@limiter.limit("10 per minute")
def schwab_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    cookie_state = request.cookies.get('schwab_oauth_state')

    if not code or not state:
        return redirect_error("Missing code or state from Schwab callback.")

    if not cookie_state or state != cookie_state:
        return redirect_error("CSRF token validation failed. Invalid or missing state cookie.")

    state_data = firestore_db.consume_schwab_auth_state(state)

    if not state_data:
        return redirect_error("Invalid or expired session state.")

    expires_at = state_data.get('expires_at')
    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_at and expires_at.replace(tzinfo=datetime.timezone.utc) < now:
        return redirect_error("Authentication request expired.")

    uid = state_data.get('uid')

    # Exchange code for tokens
    tokens = schwab_auth.exchange_code_for_tokens(code)
    if not tokens:
        return redirect_error("Failed to retrieve access tokens from Schwab.")

    # Save encrypted tokens
    schwab_auth.save_user_tokens(uid, tokens)

    # Clear the cookie
    response = make_response(redirect('/?schwab=success'))
    response.set_cookie('schwab_oauth_state', '', expires=0)
    return response


@app.route('/api/schwab/status')
@limiter.limit("30 per minute")
@require_firebase_auth
def schwab_status(decoded_token):
    uid = decoded_token['uid']
    tokens = schwab_auth.get_user_tokens(uid)
    connected = tokens is not None
    return jsonify({'connected': connected})


@app.route('/api/schwab/disconnect', methods=['POST'])
@limiter.limit("5 per minute")
@require_firebase_auth
def schwab_disconnect(decoded_token):
    uid = decoded_token['uid']
    schwab_auth.disconnect_user(uid)
    return jsonify({'message': 'Successfully disconnected from Schwab.'})


@app.route('/api/schwab/accounts')
@limiter.limit("10 per minute")
@require_firebase_auth
@require_schwab_token
def schwab_accounts(decoded_token, access_token):
    uid = decoded_token['uid']
    try:
        raw_accounts = schwab_portfolio.fetch_accounts_raw(access_token)
        parsed_data = schwab_portfolio.process_accounts_data(raw_accounts, access_token)
        return jsonify(parsed_data)
    except Exception as e:
        app.logger.error("Error fetching Schwab accounts for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to retrieve Schwab accounts'}), 502


@app.route('/api/schwab/chain')
@limiter.limit("30 per minute")
@require_firebase_auth
@require_schwab_token
def schwab_chain(decoded_token, access_token):
    uid = decoded_token['uid']

    symbol = request.args.get('symbol', 'AAPL').upper().strip()
    contract_type = request.args.get('contractType', 'CALL').upper().strip()
    min_dte = request.args.get('minDte', type=int)
    max_dte = request.args.get('maxDte', type=int)
    min_delta = request.args.get('minDelta', type=float)
    max_delta = request.args.get('maxDelta', type=float)

    try:
        chain_data = schwab_portfolio.fetch_option_chain(
            access_token, symbol, contract_type,
            min_dte=min_dte, max_dte=max_dte,
            min_delta=min_delta, max_delta=max_delta
        )
        return jsonify(chain_data)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        app.logger.error("Error fetching option chain for user %s symbol %s: %s", uid, symbol, e)
        return jsonify({'error': f'Failed to retrieve option chain for {symbol}'}), 502


@app.route('/api/schwab/boxes')
@limiter.limit("10 per minute")
@require_firebase_auth
@require_schwab_token
def schwab_boxes(decoded_token, access_token):
    uid = decoded_token['uid']

    from_date = request.args.get('fromDate')
    to_date = request.args.get('toDate')
    sizes_raw = request.args.get('sizes')

    sizes = None
    if sizes_raw:
        try:
            sizes = [int(s.strip()) for s in sizes_raw.split(',')]
        except ValueError:
            return jsonify({'error': 'Invalid sizes parameter. Must be comma-separated integers.'}), 400

    try:
        boxes = schwab_portfolio.fetch_spx_boxes(access_token, from_date, to_date, sizes)
        return jsonify({'boxes': boxes})
    except Exception as e:
        app.logger.error("Error fetching SPX boxes for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to retrieve SPX box spreads'}), 502


@app.route('/api/schwab/sync_transactions', methods=['POST'])
@limiter.limit("5 per minute")
@require_firebase_auth
@require_schwab_token
def schwab_sync_transactions(decoded_token, access_token):
    uid = decoded_token['uid']
    try:
        result = schwab_transactions.sync_transactions(uid, access_token)
        if 'error' in result:
            app.logger.error(
                "Transaction sync error for user %s: %s", uid, result['error']
            )
            return jsonify({'error': result['error']}), 502
        return jsonify(result)
    except Exception as e:
        app.logger.error("Error syncing transactions for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to sync transactions'}), 502


@app.route('/api/schwab/transactions')
@limiter.limit("30 per minute")
@require_firebase_auth
def schwab_get_transactions(decoded_token):
    uid = decoded_token['uid']
    try:
        account_hash = get_primary_account_hash()
        txns = firestore_db.get_transactions(uid, account_hash, _get_limit(100, 100))
        return jsonify({'transactions': txns, 'account_hash': account_hash})
    except EnvironmentError as e:
        app.logger.error("No primary account hash for user %s: %s", uid, e)
        return jsonify({'error': 'No primary account hash found'}), 400
    except Exception as e:
        app.logger.error("Error reading transactions for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to read transactions'}), 502


@app.route('/api/schwab/realized')
@limiter.limit("30 per minute")
@require_firebase_auth
def schwab_get_realized(decoded_token):
    uid = decoded_token['uid']
    try:
        account_hash = get_primary_account_hash()
        txns = firestore_db.get_transactions(uid, account_hash, _get_limit(1000, 1000))
        realized_txns = _calculate_realized_pl(txns)
        return jsonify({'realized_transactions': realized_txns, 'account_hash': account_hash})
    except EnvironmentError as e:
        app.logger.error("No primary account hash for user %s: %s", uid, e)
        return jsonify({'error': 'No primary account hash found'}), 400
    except Exception as e:
        app.logger.error("Error reading transactions for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to read transactions'}), 502


def _normalize_transactions(txns):
    """Normalize Firestore raw transactions into a flat representation suited for calculations.

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
        # Format time to ISO date string format like YYYY-MM-DD
        if time_str:
            time_str = time_str[:10]
        account_num = txn.get('accountNumber')

        transfer_items = txn.get('transferItems', [])
        for item in transfer_items:
            if not item:
                continue
            instrument = item.get('instrument', {}) or {}
            pos_effect = item.get('positionEffect')

            # Filter condition: positionEffect is not None, OR if DIVIDEND_OR_INTEREST and netAmount < 0
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

            # Determine short_or_long (sl)
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


def _calculate_realized_pl(txns):
    """Calculate realized gain and losses using FIFO matching.

    Args:
        txns: List of raw transaction dictionaries from Firestore.

    Returns:
        List of realized gain/loss records.
    """
    rows = _normalize_transactions(txns)

    # Group transactions by key fields to consolidate partial fills
    aggregated = {}
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

    # Two-pass stable sort: first sort by positionEffect descending
    # ('OPENING' > 'INTEREST' > 'CLOSING' alphabetically) so that openings are
    # processed before closings within the same (account, time) group, then
    # re-sort ascending by (accountNumber, time). Python's sort is stable so
    # the positionEffect ordering is preserved within equal (account, time) keys.
    grouped_rows.sort(key=lambda x: x['positionEffect'] or '', reverse=True)
    grouped_rows.sort(key=lambda x: (x['accountNumber'] or '', x['time'] or ''))

    opened = {}  # Dictionary to store opened positions by account_symbol_sl key
    result = []

    for row in grouped_rows:
        key = f"{row['accountNumber']}_{row['symbol']}_{row['sl']}"

        if row['positionEffect'] == 'INTEREST':
            # Record the margin interest.
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
            # Add opening position to the queue
            if key in opened:
                opened[key].append(row)
            else:
                opened[key] = [row]
        elif row['positionEffect'] == 'CLOSING':  # CLOSING position
            # Match against opened positions using FIFO
            while key in opened and len(opened[key]) > 0:
                o = opened[key].pop(0)  # FIFO: take first opened position
                matched_quantity = min(o['amount'], row['amount'])

                # Record the realized gain/loss
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

                # Handle partial matches
                if o['amount'] > row['amount']:
                    # Opening position partially closed, put remainder back
                    o['amount'] = o['amount'] - row['amount']
                    o['netAmount'] = unit_net_o * o['amount']
                    opened[key].insert(0, o)  # Put back at front (FIFO)
                    break
                elif o['amount'] < row['amount']:
                    # Closing more than this opening, continue to next opening
                    row['amount'] = row['amount'] - o['amount']
                    row['netAmount'] = unit_net_row * row['amount']
                # If amounts are equal, both are fully matched

                # Clean up empty position queues
                if len(opened[key]) == 0:
                    opened.pop(key)

    result.sort(key=lambda x: x['sell_date'] or '', reverse=True)
    return result

