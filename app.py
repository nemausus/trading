from flask import Flask, render_template, request, jsonify
import firebase_admin
from firebase_admin import auth

# 1. EXPLICITLY set your exact project ID here
firebase_admin.initialize_app(options={
    'projectId': 'covered-calls-ab5d1' 
})

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/hello')
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
        # 2. RETURN THE ACTUAL ERROR STRING back to the frontend
        return jsonify({'error': f'Token rejection reason: {str(e)}'}), 401