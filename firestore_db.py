import os
import datetime
import firebase_admin
from firebase_admin import firestore

# Initialize Firebase Admin SDK if not already initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(options={
        'projectId': 'covered-calls-ab5d1'
    })

def get_db():
    """Returns the Firestore client, using the custom database ID if specified."""
    return firestore.client(database_id='covered-calls-db')

def save_schwab_auth_state(state: str, uid: str, expires_at: datetime.datetime) -> None:
    """Stores the OAuth state -> uid mapping with an expiration time."""
    db = get_db()
    db.collection('schwab_auth_states').document(state).set({
        'uid': uid,
        'expires_at': expires_at
    })

def consume_schwab_auth_state(state: str) -> dict | None:
    """Transactionally retrieves and deletes the OAuth state to prevent replay attacks."""
    db = get_db()
    state_ref = db.collection('schwab_auth_states').document(state)

    @firestore.transactional
    def consume_state(transaction, doc_ref):
        snapshot = doc_ref.get(transaction=transaction)
        if snapshot.exists:
            transaction.delete(doc_ref)
            return snapshot.to_dict()
        return None

    transaction = db.transaction()
    return consume_state(transaction, state_ref)

def save_user_schwab_credentials(uid: str, encrypted_data: str) -> None:
    """Saves the encrypted Schwab credentials to the user's document."""
    db = get_db()
    user_ref = db.collection('users').document(uid)
    user_ref.set({
        'schwab_credentials': encrypted_data,
        'schwab_connected': True,
        'schwab_updated_at': firestore.SERVER_TIMESTAMP
    }, merge=True)

def get_user_schwab_credentials(uid: str) -> str | None:
    """Retrieves the encrypted Schwab credentials for a user."""
    db = get_db()
    user_doc = db.collection('users').document(uid).get()
    if not user_doc.exists:
        return None
    return user_doc.to_dict().get('schwab_credentials')

def delete_user_schwab_credentials(uid: str) -> None:
    """Deletes Schwab credentials and sets connected status to False."""
    db = get_db()
    user_ref = db.collection('users').document(uid)
    user_ref.update({
        'schwab_credentials': firestore.DELETE_FIELD,
        'schwab_connected': False,
        'schwab_updated_at': firestore.SERVER_TIMESTAMP
    })
