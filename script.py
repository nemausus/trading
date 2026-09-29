#!/usr/bin/env python3
"""
script.py
~~~~~~~~~
Standalone administrative and debugging CLI script to inspect raw transactions
and realized P/L records stored in Firestore outside of the web application.

Reuses firestore_db.py, constants.py, and realized.py services directly.

Usage examples:
    python script.py --account ira txns --limit 100
    python script.py --account ind realized --limit 50
    python script.py --account all txns --unprocessed
    python script.py --account ind realized --json
"""

import argparse
import json
import os
import sys
from dotenv import load_dotenv

# Ensure environment variables from .env are loaded at startup
load_dotenv()

from option_symbol import is_option as _is_option_symbol
from schwab_auth import SchwabAuthManager
import constants
import firestore_db
import orders

constants.init_accounts()


def resolve_uid(uid_arg: str | None) -> str:
    """Resolve Firebase user ID from arguments, environment, or Firestore auto-discovery.

    Args:
        uid_arg: Optional user ID specified on CLI.

    Returns:
        Resolved Firebase user ID.

    Raises:
        RuntimeError: If UID cannot be resolved.
    """
    if uid_arg:
        return uid_arg

    env_uid = os.environ.get("DEFAULT_UID")
    if env_uid:
        return env_uid

    try:
        db = firestore_db.get_db()
        users = list(db.collection("users").limit(1).stream())
        if users:
            return users[0].id
    except Exception as err:
        raise RuntimeError(f"Failed to auto-discover user UID from Firestore: {err}") from err

    raise RuntimeError("No user UID specified and no users found in Firestore.")


def resolve_account_hashes(account_input: str | None) -> list[str]:
    """Resolve account argument into a list of encrypted account hashes.

    Args:
        account_input: 'ira', 'ind', 'all' or account number

    Returns:
        List of matching account hash strings.
    """
    if not account_input or account_input.lower() == "all":
        return constants.get_all_account_hashes()

    acc_hash = constants.resolve_account_hash(account_input)
    if acc_hash:
        return [acc_hash]

    if account_input in constants.accounts:
        return [constants.accounts.get(account_input).hash]

    return [constants.get_account_hash(account_input)]


def resolve_account_numbers(account_input: str | None) -> list[str]:
    """Resolve account argument into a list of account numbers.

    Args:
        account_input: 'ira', 'ind', 'all' or account number

    Returns:
        List of matching account number strings.
    """
    return constants.resolve_account_number(account_input)


def handle_txns_command(
    uid: str,
    account_numbers: list[str],
    limit: int,
    unprocessed_only: bool,
    symbol_filter: str | None,
    output_json: bool,
    from_date: str | None = None,
    to_date: str | None = None,
    txn_type: str | None = "TRADE",
) -> None:
    """Fetch and display raw transactions for specified account(s)."""
    if unprocessed_only:
        fetch_limit = limit * 10 if symbol_filter else limit
        txns = []
        for acc_num in account_numbers:
            txns.extend(firestore_db.get_unprocessed_transactions(uid, acc_num, limit=fetch_limit))
        txns.sort(key=lambda x: x.get("time", ""), reverse=True)
        if txn_type and txn_type.upper() != "ALL":
            txns = [t for t in txns if (t.get("type") or "").upper() == txn_type.upper()]
        if from_date:
            txns = [t for t in txns if (t.get("time") or "")[:10] >= from_date]
        if to_date:
            txns = [t for t in txns if (t.get("time") or "")[:10] <= to_date]
        if symbol_filter and symbol_filter.upper() != "ALL":
            txns = [t for t in txns if firestore_db._matches_txn_symbol(t, symbol_filter)]
        txns = txns[:limit]
    else:
        txns = firestore_db.get_transactions_for_accounts(
            uid=uid,
            account_numbers=account_numbers,
            limit=limit,
            from_date=from_date,
            to_date=to_date,
            txn_type=txn_type,
            symbol=symbol_filter,
        )

    if output_json:
        print(json.dumps(txns, indent=2, default=str))
        return

    if not txns:
        print("No transactions found.")
        return

    # Print summary table
    header = f"{'Activity ID':<15} {'Time':<12} {'Account':<8} {'Symbol':<24} {'PosEffect':<10} {'Amount':>8} {'Price':>10} {'NetAmount':>12} {'Processed':<10}"
    print(header)
    print("-" * len(header))

    for t in txns:
        act_id = str(t.get("activityId", "N/A"))[:15]
        time_str = str(t.get("time", ""))[:10]
        acc_num = t.get("accountNumber", "N/A")
        processed = str(t.get("processed", False))

        transfer_items = t.get("transferItems", [])
        if transfer_items:
            for item in transfer_items:
                inst = item.get("instrument", {}) or {}
                sym = inst.get("symbol", "N/A")[:24]
                pos_eff = item.get("positionEffect") or "N/A"
                amount = item.get("amount", 0.0)
                price = item.get("price", 0.0)
                net_amt = t.get("netAmount", 0.0)
                print(
                    f"{act_id:<15} {time_str:<12} {acc_num:<8} {sym:<24} {pos_eff:<10} {amount:>8.2f} {price:>10.2f} {net_amt:>12.2f} {processed:<10}"
                )
        else:
            net_amt = t.get("netAmount", 0.0)
            txn_type = t.get("type", "N/A")[:24]
            print(
                f"{act_id:<15} {time_str:<12} {acc_num:<8} {txn_type:<24} {'N/A':<10} {'0.00':>8} {'0.00':>10} {net_amt:>12.2f} {processed:<10}"
            )

    print(f"\nTotal: {len(txns)} transaction(s) listed.")


def handle_realized_command(
    uid: str,
    account_numbers: list[str],
    limit: int,
    symbol_filter: str | None,
    output_json: bool,
    from_date: str | None = None,
    to_date: str | None = None,
    trade_type: str | None = None,
) -> None:
    """Fetch and display realized P/L records for specified account(s)."""
    records = firestore_db.get_realized_pl_for_accounts(
        uid=uid,
        account_numbers=account_numbers,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
        trade_type=trade_type,
        symbol=symbol_filter,
    )

    if output_json:
        print(json.dumps(records, indent=2, default=str))
        return

    if not records:
        print("No realized P/L records found.")
        return

    header = f"{'Record ID':<30} {'Account':<8} {'Type':<12} {'Symbol':<24} {'Buy Date':<10} {'Buy Price':>10} {'Sell Date':<10} {'Sell Price':>10} {'Amount':>8} {'P/L ($)':>12}"
    print(header)
    print("-" * len(header))

    total_pl = 0.0
    for r in records:
        rec_id = str(r.get("id", "N/A"))[:30]
        acc_num = r.get("accountNumber", "N/A")
        trade_type = r.get("trade_type", "N/A")[:12]
        sym = r.get("symbol", "N/A")[:24]
        buy_date = r.get("buy_date", "")[:10]
        buy_price = r.get("buy_price", 0.0)
        sell_date = r.get("sell_date", "")[:10]
        sell_price = r.get("sell_price", 0.0)
        amount = r.get("amount", 0.0)
        pl = r.get("P/L", 0.0)
        total_pl += pl

        print(
            f"{rec_id:<30} {acc_num:<8} {trade_type:<12} {sym:<24} {buy_date:<10} {buy_price:>10.2f} {sell_date:<10} {sell_price:>10.2f} {amount:>8.2f} {pl:>12.2f}"
        )

    print(f"\nTotal Realized P/L: ${total_pl:,.2f} across {len(records)} record(s).")


def handle_migrate_accounts_command(
    uid: str,
    account_hashes: list[str],
    dry_run: bool = False,
) -> None:
    """Migrate Firestore account subcollections from hash-keyed to number-keyed documents.

    Copies all documents from:
        users/{uid}/accounts/{account_hash}/transactions/*
        users/{uid}/accounts/{account_hash}/realized_pl/*
    To:
        users/{uid}/accounts/{account_number}/transactions/*
        users/{uid}/accounts/{account_number}/realized_pl/*

    Existing data under the hash-keyed path is preserved (not deleted).

    Args:
        uid: Firebase user ID.
        account_hashes: List of account hashes to migrate.
        dry_run: If True, preview what would be copied without writing.
    """
    db = firestore_db.get_db()
    subcollections = ("transactions", "realized_pl")
    mode_label = "[DRY RUN]" if dry_run else "[LIVE]"
    print(f"=== {mode_label} Migrating Account Documents (hash -> number) ===")
    print(f"User: {uid}")
    print(f"Accounts: {len(account_hashes)}\n")

    total_copied = 0
    total_skipped = 0

    for acc_hash in account_hashes:
        acc_num = constants.get_account_number_for_hash(acc_hash)
        print(f"--- Account: {acc_num} (hash: {acc_hash[:12]}...) ---")

        for sub_name in subcollections:
            src_col = (
                db.collection("users")
                .document(uid)
                .collection("accounts")
                .document(acc_hash)
                .collection(sub_name)
            )
            dst_col = (
                db.collection("users")
                .document(uid)
                .collection("accounts")
                .document(acc_num)
                .collection(sub_name)
            )

            src_docs = list(src_col.stream())
            print(f"  {sub_name}: {len(src_docs)} document(s) in source.")

            if not src_docs:
                continue

            # Check which docs already exist in destination
            dst_refs = [dst_col.document(doc.id) for doc in src_docs]
            dst_snaps = db.get_all(dst_refs)
            existing_ids = {snap.id for snap in dst_snaps if snap.exists}

            to_copy = [(doc.id, doc.to_dict()) for doc in src_docs if doc.id not in existing_ids]
            skipped = len(src_docs) - len(to_copy)
            total_skipped += skipped

            if skipped:
                print(
                    f"  {sub_name}: {skipped} document(s) already exist in destination, skipping."
                )

            if not to_copy:
                print(f"  {sub_name}: nothing new to copy.")
                continue

            print(f"  {sub_name}: {len(to_copy)} document(s) to copy.")

            if not dry_run:
                batch_size = 500
                for i in range(0, len(to_copy), batch_size):
                    batch = db.batch()
                    chunk = to_copy[i : i + batch_size]
                    for doc_id, doc_data in chunk:
                        batch.set(dst_col.document(doc_id), doc_data)
                    batch.commit()
                total_copied += len(to_copy)
                print(f"  {sub_name}: copied {len(to_copy)} document(s).")
            else:
                total_copied += len(to_copy)
                print(f"  {sub_name}: [DRY RUN] would copy {len(to_copy)} document(s).")

        print()

    print(f"\nSummary:")
    print(f"  Documents copied  : {total_copied} {'(DRY RUN)' if dry_run else ''}")
    print(f"  Documents skipped : {total_skipped} (already existed)")


def _is_exception_record(doc_id: str, doc_data: dict) -> bool:
    """Check if record matches the explicit META 1/23/26 655C trade exception.

    Exception details:
        Opened: 2025-12-31 at $19.20
        Closed: 2026-01-23 at $7.99
        Contract: META 1/23/26 655C

    Args:
        doc_id: Firestore document ID.
        doc_data: Firestore document dictionary.

    Returns:
        True if this record is the protected META exception, False otherwise.
    """
    if "2025-12-31" in doc_id and "2026-01-23" in doc_id and "655" in doc_id:
        return True

    buy_date = str(doc_data.get("buy_date") or "")[:10]
    sell_date = str(doc_data.get("sell_date") or doc_data.get("close_date") or "")[:10]
    symbol = str(doc_data.get("symbol") or "")

    if (
        buy_date == "2025-12-31"
        and sell_date == "2026-01-23"
        and "META" in symbol
        and "655" in symbol
    ):
        return True

    return False


def handle_fix_realized_command(
    uid: str,
    account_hashes: list[str],
    start_date: str = "2026-01-01",
    end_date: str = "2026-08-18",
    dry_run: bool = False,
) -> None:
    """Fix realized transactions for options by swapping buy_price and sell_price (close_price).

    Args:
        uid: Firebase user ID.
        account_hashes: Target account hashes.
        start_date: Inclusive start close date (YYYY-MM-DD).
        end_date: Inclusive end close date (YYYY-MM-DD).
        dry_run: If True, preview candidates without committing changes to Firestore.
    """
    db = firestore_db.get_db()
    total_candidates = 0
    total_updated = 0
    total_skipped_exception = 0
    total_skipped_stock = 0
    total_skipped_date = 0

    mode_label = "[DRY RUN - PREVIEW ONLY]" if dry_run else "[LIVE UPDATE]"
    print(f"=== {mode_label} Fixing Realized Option Transactions ===")
    print(f"Target Date Range: {start_date} to {end_date} (inclusive)")
    print(f"Target Accounts: {len(account_hashes)} account(s)\n")

    for acc_hash in account_hashes:
        acc_num = constants.get_account_number_for_hash(acc_hash) or acc_hash
        col = firestore_db._realized_pl_collection(db, uid, acc_num)
        docs = list(col.stream())
        print(f"Account {acc_num}: Retrieved {len(docs)} total realized record(s) from Firestore.")

        updates = []
        for doc in docs:
            d = doc.to_dict()
            doc_id = doc.id
            close_date = str(d.get("sell_date") or d.get("close_date") or "")[:10]
            symbol = d.get("symbol", "")

            if not (start_date <= close_date <= end_date):
                total_skipped_date += 1
                continue

            if not _is_option_symbol(symbol):
                total_skipped_stock += 1
                continue

            if _is_exception_record(doc_id, d):
                print(
                    f"  [PROTECTED EXCEPTION] Skipping {doc_id} ({symbol}, close date: {close_date})"
                )
                total_skipped_exception += 1
                continue

            total_candidates += 1
            old_buy = float(d.get("buy_price") or 0.0)
            old_close = float(d.get("sell_price") or 0.0)

            new_buy = old_close
            new_close = old_buy

            payload = {
                "buy_price": new_buy,
                "sell_price": new_close,
            }

            updates.append(
                (
                    doc.reference,
                    doc_id,
                    symbol,
                    close_date,
                    old_buy,
                    new_buy,
                    old_close,
                    new_close,
                    payload,
                )
            )

        if updates:
            header = f"{'Doc ID':<58} {'Symbol':<24} {'Close Date':<12} {'Buy Price (Old -> New)':<26} {'Close Price (Old -> New)':<26}"
            print(f"\n{header}")
            print("-" * len(header))

            for _, doc_id, sym, c_date, old_b, new_b, old_c, new_c, _ in updates:
                buy_change = f"${old_b:.2f} -> ${new_b:.2f}"
                close_change = f"${old_c:.2f} -> ${new_c:.2f}"
                print(f"{doc_id:<58} {sym:<24} {c_date:<12} {buy_change:<26} {close_change:<26}")

            if not dry_run:
                batch_size = 500
                for i in range(0, len(updates), batch_size):
                    batch = db.batch()
                    chunk = updates[i : i + batch_size]
                    for doc_ref, _, _, _, _, _, _, _, payload in chunk:
                        batch.set(doc_ref, payload, merge=True)
                    batch.commit()
                total_updated += len(updates)
                print(
                    f"\nSuccessfully committed {len(updates)} record update(s) to Firestore for account {acc_num}."
                )
            else:
                print(
                    f"\n[DRY RUN] Would update {len(updates)} record(s) for account {acc_num}. No writes performed."
                )
        else:
            print(f"Account {acc_num}: No option records matched criteria for update.")

    print(f"\nSummary:")
    print(f"  Option candidates to fix : {total_candidates}")
    print(f"  Records updated          : {total_updated} {'(DRY RUN)' if dry_run else ''}")
    print(f"  Exceptions preserved     : {total_skipped_exception}")
    print(f"  Stocks excluded          : {total_skipped_stock}")
    print(f"  Outside date window      : {total_skipped_date}")


def handle_order_command(
    uid: str,
    account_hash: str,
    symbol: str,
    quantity: float,
    instruction: str,
    price: str | None,
    preview: bool,
    order_type: str = "LIMIT",
    duration: str = "GTC",
    session: str = "NORMAL",
) -> None:
    """Submit or preview an order on Charles Schwab via the CLI."""
    schwab_auth = SchwabAuthManager()
    access_token = schwab_auth.refresh_user_tokens_if_needed(uid)
    if not access_token:
        print(
            f"Error: Schwab account not connected or failed to refresh token for user {uid}.",
            file=sys.stderr,
        )
        sys.exit(1)

    acc_num = constants.get_account_number_for_hash(account_hash) or "unknown"
    action_label = "Previewing" if preview else "Placing"
    print(f"\n{action_label} order for account {acc_num} ({account_hash[:10]}...):")
    print(f"  Symbol      : {symbol}")
    print(f"  Quantity    : {quantity}")
    print(f"  Instruction : {instruction}")
    print(f"  Price       : {price or 'MARKET'}")
    print(f"  Type        : {order_type}")
    print(f"  Duration    : {duration}")
    print(f"  Session     : {session}")

    try:
        order_payload = orders.build_single_order(
            symbol=symbol,
            quantity=quantity,
            instruction=instruction,
            price=price,
            order_type=order_type,
            duration=duration,
            session=session,
        )

        res = orders.execute_order(
            access_token=access_token,
            account_number=acc_num,
            order_payload=order_payload,
            preview=preview,
        )

        if preview:
            print("\nPreview Evaluation Result:")
            print(json.dumps(res, indent=2))
        else:
            print(f"\nSuccessfully placed order! Order ID: {res.get('orderId')}")
            if res.get("location"):
                print(f"Location: {res['location']}")
    except Exception as e:
        print(f"\nOrder failed: {e}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for the CLI script."""
    parser = argparse.ArgumentParser(
        description="Administrative CLI tool for querying Firestore transactions and realized P/L data."
    )
    parser.add_argument(
        "--account",
        type=str,
        default="all",
        help="Account name ('ind', 'ira', 'all') or account number.",
    )
    parser.add_argument(
        "-s", "--symbol", type=str, help="Filter by ticker or underlying symbol (e.g. NVDA, IBIT)."
    )
    parser.add_argument(
        "--uid", type=str, help="Firebase User ID (auto-discovered from Firestore if omitted)."
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # txns subcommand
    txns_parser = subparsers.add_parser(
        "txns", aliases=["transactions"], help="List raw transactions from Firestore."
    )
    txns_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of transactions to return (default: 100).",
    )
    txns_parser.add_argument(
        "--unprocessed", action="store_true", help="Only return unprocessed raw transactions."
    )
    txns_parser.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Filter transactions from date (YYYY-MM-DD, inclusive).",
    )
    txns_parser.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="Filter transactions to date (YYYY-MM-DD, inclusive).",
    )
    txns_parser.add_argument(
        "--type",
        "--txn-type",
        dest="txn_type",
        type=str,
        default="TRADE",
        help="Filter by transaction type (default: TRADE, use 'ALL' for all).",
    )
    txns_parser.add_argument("--json", action="store_true", help="Output results in JSON format.")

    # realized subcommand
    realized_parser = subparsers.add_parser(
        "realized", help="List realized P/L records from Firestore."
    )
    realized_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of realized records to return (default: 100).",
    )
    realized_parser.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Filter realized records from sell date (YYYY-MM-DD, inclusive).",
    )
    realized_parser.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="Filter realized records to sell date (YYYY-MM-DD, inclusive).",
    )
    realized_parser.add_argument(
        "--type",
        "--trade-type",
        dest="trade_type",
        type=str,
        default="ALL",
        help="Filter by trade type (default: ALL).",
    )
    realized_parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format."
    )

    # fix-realized subcommand
    fix_parser = subparsers.add_parser(
        "fix-realized",
        help="Fix realized option transactions by swapping buy_price and sell_price (close_price).",
    )
    fix_parser.add_argument(
        "--account",
        dest="sub_account",
        type=str,
        default=None,
        help="Account number or name (e.g. acc2, ira).",
    )
    fix_parser.add_argument(
        "--start-date",
        type=str,
        default="2026-01-01",
        help="Start close date (inclusive, YYYY-MM-DD, default: 2026-01-01).",
    )
    fix_parser.add_argument(
        "--end-date",
        type=str,
        default="2026-08-18",
        help="End close date (inclusive, YYYY-MM-DD, default: 2026-08-18).",
    )
    fix_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview transactions that would be fixed without updating Firestore.",
    )

    # migrate-accounts subcommand
    migrate_parser = subparsers.add_parser(
        "migrate-accounts",
        help="Migrate Firestore account data from hash-keyed to number-keyed documents.",
    )
    migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Preview migration without writing to Firestore."
    )

    # order subcommand
    order_parser = subparsers.add_parser(
        "order", aliases=["place-order"], help="Place or preview an order on Charles Schwab."
    )
    order_parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        required=True,
        help="Ticker or OCC option symbol (e.g. AAPL, 'AAPL  260821C00205000').",
    )
    order_parser.add_argument(
        "-q",
        "--quantity",
        type=float,
        required=True,
        help="Order quantity (number of contracts or shares).",
    )
    order_parser.add_argument(
        "-p", "--price", type=str, help="Limit price for the order (required for LIMIT orders)."
    )
    order_parser.add_argument(
        "-i",
        "--instruction",
        type=str,
        required=True,
        choices=["BTO", "BTC", "STO", "STC", "BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER"],
        help="Order instruction (e.g. BTC, STO, BTO, STC, BUY, SELL).",
    )
    order_parser.add_argument(
        "--preview", action="store_true", help="Preview the order instead of submitting live."
    )
    order_parser.add_argument(
        "--order-type",
        "--type",
        dest="order_type",
        default="LIMIT",
        choices=["LIMIT", "MARKET", "NET_DEBIT", "NET_CREDIT"],
        help="Order type (default: LIMIT).",
    )
    order_parser.add_argument(
        "--duration",
        default="GTC",
        choices=["GTC", "DAY", "FOK", "IOC"],
        help="Order duration (default: GTC).",
    )
    order_parser.add_argument(
        "--session",
        default="NORMAL",
        choices=["NORMAL", "AM", "PM", "SEAMLESS"],
        help="Trading session (default: NORMAL).",
    )

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    account_input = args.account
    if args.command == "fix-realized":
        assert account_input == "ira"

    try:
        uid = resolve_uid(args.uid)
        account_numbers = resolve_account_numbers(account_input)
        account_hashes = resolve_account_hashes(account_input)
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.command in ("txns", "transactions"):
        handle_txns_command(
            uid=uid,
            account_numbers=account_numbers,
            limit=args.limit,
            unprocessed_only=args.unprocessed,
            symbol_filter=args.symbol,
            output_json=args.json,
            from_date=getattr(args, "from_date", None),
            to_date=getattr(args, "to_date", None),
            txn_type=getattr(args, "txn_type", "TRADE"),
        )
    elif args.command == "realized":
        handle_realized_command(
            uid=uid,
            account_numbers=account_numbers,
            limit=args.limit,
            symbol_filter=args.symbol,
            output_json=args.json,
            from_date=getattr(args, "from_date", None),
            to_date=getattr(args, "to_date", None),
            trade_type=getattr(args, "trade_type", None),
        )
    elif args.command == "fix-realized":
        handle_fix_realized_command(
            uid=uid,
            account_hashes=account_hashes,
            start_date=args.start_date,
            end_date=args.end_date,
            dry_run=args.dry_run,
        )
    elif args.command == "migrate-accounts":
        handle_migrate_accounts_command(
            uid=uid,
            account_hashes=account_hashes,
            dry_run=args.dry_run,
        )
    elif args.command == "order":
        is_preview = args.preview
        assert len(account_hashes) == 1
        handle_order_command(
            uid=uid,
            account_hash=account_hashes[0],
            symbol=args.symbol,
            quantity=args.quantity,
            instruction=args.instruction,
            price=args.price,
            preview=is_preview,
            order_type=args.order_type,
            duration=args.duration,
            session=args.session,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
