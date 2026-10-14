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

    return [constants.get_account_hash_for_number(account_input)]


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
