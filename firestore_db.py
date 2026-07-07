import os
import datetime
import firebase_admin
from firebase_admin import firestore

# Initialize Firebase Admin SDK if not already initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(options={
        'projectId': 'covered-calls-ab5d1'
    })

# Firestore batch write limit.
_BATCH_SIZE = 500

# Lazy singleton — the Firestore client is thread-safe and intended to be reused.
_db = None


def get_db():
    """Returns the Firestore client, using the custom database ID if specified."""
    global _db
    if _db is None:
        _db = firestore.client(database_id='covered-calls-db')
    return _db


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


# ---------------------------------------------------------------------------
# Transaction helpers
# ---------------------------------------------------------------------------

def _txn_collection(db, uid: str, account_hash: str):
    """Returns the Firestore CollectionReference for a user's transactions."""
    return (
        db.collection('users')
        .document(uid)
        .collection('accounts')
        .document(account_hash)
        .collection('transactions')
    )


def get_transactions(
    uid: str,
    account_hash: str,
    limit: int,
) -> list[dict]:
    """
    Returns stored transactions for the given user/account, ordered by
    time descending (most recent first), up to *limit* records.

    Each returned dict contains the raw Firestore document data with the
    document ID added as ``activityId`` (string).
    """
    db = get_db()
    col = _txn_collection(db, uid, account_hash)
    docs = col.order_by('time', direction='DESCENDING').limit(limit).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        # Ensure activityId is present as a string (it's also the doc ID)
        if 'activityId' not in data:
            data['activityId'] = doc.id
        # Firestore SERVER_TIMESTAMP is not JSON-serialisable; drop it
        data.pop('fetched_at', None)
        results.append(data)
    return results


def get_primary_account_hash() -> str | None:
    """
    Returns the primary account hash from environment variables.
    """
    return os.environ.get('IND_ACCOUNT')

def get_secondary_account_hash() -> str | None:
    """
    Returns the secondary account hash from environment variables.
    """
    return os.environ.get('IRA_ACCOUNT')


def get_latest_transaction_time(uid: str, account_hash: str) -> str | None:
    """
    Returns the ``time`` field of the most recently stored transaction for the
    given user and account, or ``None`` if no transactions are stored yet.
    """
    db = get_db()
    col = _txn_collection(db, uid, account_hash)
    docs = col.order_by('time', direction='DESCENDING').limit(1).stream()
    for doc in docs:
        return doc.to_dict().get('time')
    return None


def get_existing_activity_ids(
    uid: str,
    account_hash: str,
    activity_ids: list[str],
) -> set[str]:
    """
    Returns the subset of *activity_ids* that already exist in Firestore.

    Uses a single batched ``get_all`` call instead of N individual reads,
    making it efficient even for large transaction backtills.
    """
    if not activity_ids:
        return set()
    db = get_db()
    col = _txn_collection(db, uid, account_hash)
    doc_refs = [col.document(str(aid)) for aid in activity_ids]
    snaps = db.get_all(doc_refs)
    return {snap.id for snap in snaps if snap.exists}


def save_transactions(
    uid: str,
    account_hash: str,
    docs: list[dict],
) -> None:
    """
    Batch-write transaction documents to Firestore.

    Each document is stored at:
        users/{uid}/accounts/{account_hash}/transactions/{activityId}

    The ``activityId`` field is used as the document ID (natural dedup key).
    A ``fetched_at`` server timestamp is injected into every document.

    Writes are chunked into batches of 500 to respect Firestore limits.
    """
    if not docs:
        return
    db = get_db()
    col = _txn_collection(db, uid, account_hash)

    for i in range(0, len(docs), _BATCH_SIZE):
        batch = db.batch()
        for txn in docs[i:i + _BATCH_SIZE]:
            activity_id = str(txn['activityId'])
            doc_ref = col.document(activity_id)
            payload = dict(txn)
            payload['fetched_at'] = firestore.SERVER_TIMESTAMP
            batch.set(doc_ref, payload)
        batch.commit()
