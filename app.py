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
from constants import get_all_account_hashes, get_primary_account_hash
from schwab_auth import SchwabAuthManager
import schwab_portfolio
import schwab_transactions
import realized_pl


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
        results = []
        for acc_hash in get_all_account_hashes():
            result = schwab_transactions.sync_transactions(uid, access_token, acc_hash)
            if 'error' in result:
                app.logger.error(
                    "Transaction sync error for user %s: %s", uid, result['error']
                )
                return jsonify({'error': result['error']}), 502
            results.append(result)
        return jsonify({'results': results})
    except Exception as e:
        app.logger.error("Error syncing transactions for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to sync transactions'}), 502


@app.route('/api/schwab/transactions')
@limiter.limit("30 per minute")
@require_firebase_auth
def schwab_get_transactions(decoded_token):
    uid = decoded_token['uid']
    try:
        account_hashes = get_all_account_hashes()
        txns = firestore_db.get_transactions_for_accounts(uid, account_hashes, _get_limit(100, 100))
        for t in txns:
            if isinstance(t, dict):
                t.pop('account_hash', None)
                t.pop('accountHash', None)
        return jsonify({'transactions': txns})
    except Exception as e:
        app.logger.error("Error reading transactions for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to read transactions'}), 502


@app.route('/api/schwab/realized')
@limiter.limit("30 per minute")
@require_firebase_auth
def schwab_get_realized(decoded_token):
    uid = decoded_token['uid']
    try:
        account_hashes = get_all_account_hashes()
        txns = firestore_db.get_transactions_for_accounts(uid, account_hashes, _get_limit(1000, 1000))
        realized = realized_pl.calculate_realized_pl(txns)
        for r in realized:
            if isinstance(r, dict):
                r.pop('account_hash', None)
                r.pop('accountHash', None)
        return jsonify({'realized_transactions': realized})
    except Exception as e:
        app.logger.error("Error reading transactions for user %s: %s", uid, e)
        return jsonify({'error': 'Failed to read transactions'}), 502



