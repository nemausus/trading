from flask import Flask, render_template, request, jsonify
import firebase_admin
from firebase_admin import auth

# Initializes using Cloud Run's native credentials
firebase_admin.initialize_app()
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hello')
def secure_hello():
    # Extract the token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401

    token = auth_header.split('Bearer ')[1]

    try:
        # Validate the token with Google's servers
        decoded_token = auth.verify_id_token(token)
        user_email = decoded_token.get('email', 'Unknown User')
        return jsonify({'message': f'Secure Hello World! Welcome, {user_email}.'})
    except Exception as e:
        return jsonify({'error': 'Invalid or expired token'}), 401
