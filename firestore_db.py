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


def _chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

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

def _account_subcollection(db, uid: str, account_hash: str, name: str):
    """Returns a Firestore CollectionReference nested under a user's account."""
    return (
        db.collection('users')
        .document(uid)
        .collection('accounts')
        .document(account_hash)
        .collection(name)
    )


def _txn_collection(db, uid: str, account_hash: str):
    """Returns the Firestore CollectionReference for a user's transactions."""
    return _account_subcollection(db, uid, account_hash, 'transactions')


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


def get_transactions_for_accounts(uid: str, account_hashes: list[str], limit: int) -> list[dict]:
    """
    Returns stored transactions for multiple accounts, ordered by time descending,
    up to *limit* records across all specified accounts.
    """
    return sorted(
        (t for h in account_hashes for t in get_transactions(uid, h, limit)),
        key=lambda x: x.get('time', ''),
        reverse=True,
    )


def get_unprocessed_transactions(
    uid: str,
    account_hash: str,
    limit: int = 1000,
) -> list[dict]:
    """
    Returns unprocessed raw transactions for the given user/account, ordered by
    time ascending (oldest first for FIFO matching), up to *limit* records.
    """
    db = get_db()
    col = _txn_collection(db, uid, account_hash)
    docs = col.where('processed', '==', False).stream()
    unprocessed = []
    for doc in docs:
        data = doc.to_dict()
        if 'activityId' not in data:
            data['activityId'] = doc.id
        data.pop('fetched_at', None)
        unprocessed.append(data)
    unprocessed.sort(key=lambda x: x.get('time', ''))
    return unprocessed[:limit]



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

    for chunk in _chunks(docs, _BATCH_SIZE):
        batch = db.batch()
        for txn in chunk:
            activity_id = str(txn['activityId'])
            doc_ref = col.document(activity_id)
            payload = dict(txn)
            if 'processed' not in payload:
                payload['processed'] = False
            payload['fetched_at'] = firestore.SERVER_TIMESTAMP
            batch.set(doc_ref, payload)
        batch.commit()


# ---------------------------------------------------------------------------
# Realized P/L helpers
# ---------------------------------------------------------------------------

def _realized_pl_collection(db, uid: str, account_hash: str):
    """Returns the Firestore CollectionReference for a user's realized P/L records."""
    return _account_subcollection(db, uid, account_hash, 'realized_pl')


def _categorize_realized_trade(doc: dict) -> str:
    """Categorize a realized trade record into one of the standard types:
    1) Stock
    2) Call Short (sold call option to open and bought to close)
    3) Call Long (bought call option to open and sold to close)
    4) Put Short (sold put option to open and bought to close)
    5) Put Long (bought put option to open and sold to close)
    Or 'Margin Interest' for interest charges.
    """
    symbol = (doc.get('symbol') or '').strip()
    if not symbol:
        return 'Stock'

    sym_upper = symbol.upper()
    if sym_upper in ('MARGIN INTEREST', 'INTEREST', 'MARGIN'):
        return 'Margin Interest'

    # Check for option symbol
    contract_type = None
    if len(symbol) >= 15:
        rest = symbol[6:].strip()
        c_idx = rest.find('C')
        p_idx = rest.find('P')
        if c_idx >= 6 and rest[:c_idx].isdigit():
            contract_type = 'C'
        elif p_idx >= 6 and rest[:p_idx].isdigit():
            contract_type = 'P'

    if not contract_type:
        parts = symbol.split()
        if len(parts) == 4 and parts[3].upper() in ('C', 'P') and '/' in parts[1]:
            contract_type = parts[3].upper()

    if not contract_type:
        return 'Stock'

    sl = (doc.get('sl') or '').lower()
    if sl == 'short':
        return 'Call Short' if contract_type == 'C' else 'Put Short'
    elif sl == 'long':
        return 'Call Long' if contract_type == 'C' else 'Put Long'

    # Deduce from open price (buy_price), close price (sell_price), and P/L
    buy_price = float(doc.get('buy_price') or 0.0)
    sell_price = float(doc.get('sell_price') or 0.0)
    pl = float(doc.get('P/L') or 0.0)

    delta = sell_price - buy_price
    if delta > 0:
        is_short = (pl < 0)
    elif delta < 0:
        is_short = (pl > 0)
    else:
        is_short = (pl >= 0)

    if contract_type == 'C':
        return 'Call Short' if is_short else 'Call Long'
    return 'Put Short' if is_short else 'Put Long'


def get_realized_pl_transactions(
    uid: str,
    account_hash: str,
    limit: int,
) -> list[dict]:
    """
    Returns stored realized P/L transactions for the given user/account,
    ordered by sell_date descending, up to *limit* records.
    """
    db = get_db()
    col = _realized_pl_collection(db, uid, account_hash)
    docs = col.order_by('sell_date', direction='DESCENDING').limit(limit).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data.pop('created_at', None)
        data['trade_type'] = data.get('trade_type') or _categorize_realized_trade(data)
        results.append(data)
    return results


def get_realized_pl_for_accounts(
    uid: str,
    account_hashes: list[str],
    limit: int,
) -> list[dict]:
    """
    Returns stored realized P/L transactions for multiple accounts, ordered by
    sell_date descending, up to *limit* records across specified accounts.
    """
    return sorted(
        (r for h in account_hashes for r in get_realized_pl_transactions(uid, h, limit)),
        key=lambda x: x.get('sell_date', ''),
        reverse=True,
    )


def save_realized_pl_transactions(
    uid: str,
    account_hash: str,
    docs: list[dict],
) -> None:
    """
    Batch-write realized P/L documents to Firestore.

    Each document is stored at:
        users/{uid}/accounts/{account_hash}/realized_pl/{doc_id}
    """
    if not docs:
        return
    db = get_db()
    col = _realized_pl_collection(db, uid, account_hash)

    for chunk in _chunks(docs, _BATCH_SIZE):
        batch = db.batch()
        for idx, item in enumerate(chunk):
            doc_id = item.get('id') or (
                f"realized_{item.get('accountNumber', '')}_"
                f"{item.get('symbol', '')}_{item.get('buy_date', '')}_"
                f"{item.get('sell_date', '')}_{idx}"
            )
            doc_ref = col.document(str(doc_id))
            payload = dict(item)
            payload['created_at'] = firestore.SERVER_TIMESTAMP
            batch.set(doc_ref, payload, merge=True)
        batch.commit()


def mark_transactions_processed(
    uid: str,
    account_hash: str,
    activity_ids: set[str] | list[str],
) -> None:
    """
    Update raw transaction documents in Firestore to mark them as processed.
    """
    if not activity_ids:
        return
    db = get_db()
    col = _txn_collection(db, uid, account_hash)
    for chunk in _chunks(list(activity_ids), _BATCH_SIZE):
        batch = db.batch()
        for aid in chunk:
            doc_ref = col.document(str(aid))
            batch.update(doc_ref, {'processed': True})
        batch.commit()

