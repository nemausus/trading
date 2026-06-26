from flask import Flask, render_template, request, jsonify, redirect
import firebase_admin
from firebase_admin import auth, firestore
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import secrets
import datetime
import requests
from functools import wraps
from schwab_auth import SchwabAuthManager

# 1. EXPLICITLY set your exact project ID here
firebase_admin.initialize_app(options={
    'projectId': 'covered-calls-ab5d1'
})

schwab_auth = SchwabAuthManager()

def require_firebase_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized - Missing Header'}), 401

        token = auth_header.split('Bearer ')[1].strip()
        try:
            decoded_token = auth.verify_id_token(token)
        except Exception as e:
            app.logger.warning(f"Token verification failed: {e}")
            return jsonify({'error': 'Unauthorized - Invalid or expired token'}), 401
        return f(decoded_token, *args, **kwargs)
    return decorated_function

app = Flask(__name__)

# Configure Content Security Policy (CSP) to allow Firebase SDK loading
csp = {
    'default-src': '\'self\'',
    'script-src': [
        '\'self\'',
        '\'unsafe-inline\'',
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hello')
@limiter.limit("10 per minute")
@require_firebase_auth
def secure_hello(decoded_token):
    user_email = decoded_token.get('email', 'Unknown User')
    ind_account = os.environ.get('IND_ACCOUNT')
    return jsonify({'message': f'Secure Hello World! Welcome, {user_email}. {ind_account}'})

@app.route('/api/auth/schwab', methods=['POST'])
@limiter.limit("5 per minute")
@require_firebase_auth
def schwab_authorize(decoded_token):
    uid = decoded_token['uid']

    # Generate secure random state
    state = secrets.token_urlsafe(16)

    # Store state -> uid in Firestore with expiration (10 minutes)
    db = firestore.client()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
    db.collection('schwab_auth_states').document(state).set({
        'uid': uid,
        'expires_at': expires_at
    })

    # Build Schwab authorization URL
    params = {
        'client_id': schwab_auth.client_id,
        'redirect_uri': schwab_auth.redirect_uri,
        'response_type': 'code',
        'state': state
    }
    import urllib.parse
    auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?{urllib.parse.urlencode(params)}"

    return jsonify({'url': auth_url})

@app.route('/api/auth/schwab/callback')
@limiter.limit("10 per minute")
def schwab_callback():
    code = request.args.get('code')
    state = request.args.get('state')

    import urllib.parse

    if not code or not state:
        err_msg = urllib.parse.quote("Missing code or state from Schwab callback.")
        return redirect(f'/?schwab=error&message={err_msg}')

    db = firestore.client()
    state_ref = db.collection('schwab_auth_states').document(state)
    state_doc = state_ref.get()

    if not state_doc.exists:
        err_msg = urllib.parse.quote("Invalid or expired session state.")
        return redirect(f'/?schwab=error&message={err_msg}')

    state_data = state_doc.to_dict()
    expires_at = state_data.get('expires_at')
    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_at and expires_at.replace(tzinfo=datetime.timezone.utc) < now:
        state_ref.delete()
        err_msg = urllib.parse.quote("Authentication request expired.")
        return redirect(f'/?schwab=error&message={err_msg}')

    uid = state_data.get('uid')
    state_ref.delete()  # Clean up state token

    # Exchange code for tokens
    tokens = schwab_auth.exchange_code_for_tokens(code)
    if not tokens:
        err_msg = urllib.parse.quote("Failed to retrieve access tokens from Schwab.")
        return redirect(f'/?schwab=error&message={err_msg}')

    # Save encrypted tokens
    schwab_auth.save_user_tokens(uid, tokens)

    return redirect('/?schwab=success')

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
def schwab_accounts(decoded_token):
    uid = decoded_token['uid']

    # Get a valid, decrypted, auto-refreshed access token
    access_token = schwab_auth.refresh_user_tokens_if_needed(uid)
    if not access_token:
        return jsonify({'error': 'Schwab account not connected or failed to refresh session'}), 400

    # Make API call to Schwab
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        response = requests.get("https://api.schwabapi.com/trader/v1/accounts", headers=headers)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        app.logger.error(f"Error fetching Schwab accounts for user {uid}: {e}")
        return jsonify({'error': 'Failed to retrieve Schwab accounts'}), 502