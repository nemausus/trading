from flask import Flask, render_template, request, jsonify
import firebase_admin
from firebase_admin import auth
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

# 1. EXPLICITLY set your exact project ID here
firebase_admin.initialize_app(options={
    'projectId': 'covered-calls-ab5d1' 
})

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
def secure_hello():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized - Missing Header'}), 401
    
    # .strip() ensures no trailing whitespace ruins the token
    token = auth_header.split('Bearer ')[1].strip() 
    
    try:
        decoded_token = auth.verify_id_token(token)
        user_email = decoded_token.get('email', 'Unknown User')
        return jsonify({'message': f'Secure Hello World! Welcome, {user_email}.'})
    except Exception as e:
        # Avoid leaking internal exception details back to the client
        app.logger.warning(f"Token verification failed: {e}")
        return jsonify({'error': 'Unauthorized - Invalid or expired token'}), 401