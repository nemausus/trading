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
    python script.py --account ind txns --json
    python script.py --account ind calc-realized --dry-run
    python script.py --account all calc-realized
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
import realized

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
            txns.extend(
                firestore_db.get_unprocessed_transactions(
                    uid, acc_num, limit=fetch_limit, raw=output_json
                )
            )
        txns.sort(key=lambda x: x.get("time", ""), reverse=True)
        if txn_type and txn_type.upper() != "ALL":
            txns = [t for t in txns if (t.get("type") or "").upper() == txn_type.upper()]
        if from_date:
            txns = [t for t in txns if (t.get("time") or "")[:10] >= from_date]
        if to_date:
            txns = [t for t in txns if (t.get("time") or "")[:10] <= to_date]
        if symbol_filter and symbol_filter.upper() != "ALL":
            txns = [t for t in txns if firestore_db._matches_txn_symbol(dict(t), symbol_filter)]
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
            raw=output_json,
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
        net_amt = t.get("netAmount", 0.0)

        sym = str(t.get("symbol") or "—")[:24]
        if sym == "—" and t.get("type"):
            sym = str(t.get("type"))[:24]
        pos_eff = t.get("positionEffect") or "N/A"
        amount = t.get("amount", 0.0)
        price = t.get("price", 0.0)

        print(
            f"{act_id:<15} {time_str:<12} {acc_num:<8} {sym:<24} {pos_eff:<10} {amount:>8.2f} {price:>10.2f} {net_amt:>12.2f} {processed:<10}"
        )

    print(f"\nTotal: {len(txns)} transaction(s) listed.")


def _print_realized_table(records: list[dict]) -> float:
    """Print an ASCII table of realized P/L records and return total P/L."""
    if not records:
        print("No realized P/L records found.")
        return 0.0

    header = f"{'Record ID':<30} {'Account':<8} {'Type':<12} {'Symbol':<24} {'Buy Date':<10} {'Buy Price':>10} {'Sell Date':<10} {'Sell Price':>10} {'Amount':>8} {'P/L ($)':>12}"
    print(header)
    print("-" * len(header))

    total_pl = 0.0
    for r in records:
        rec_id = str(r.get("id", "N/A"))[:30]
        acc_num = r.get("accountNumber", "N/A")
        trade_type = str(r.get("trade_type") or firestore_db._categorize_realized_trade(r))[:12]
        sym = r.get("symbol", "N/A")[:24]
        buy_date = str(r.get("buy_date", ""))[:10]
        buy_price = float(r.get("buy_price") or 0.0)
        sell_date = str(r.get("sell_date", ""))[:10]
        sell_price = float(r.get("sell_price") or 0.0)
        amount = float(r.get("amount") or 0.0)
        pl = float(r.get("P/L") or 0.0)
        total_pl += pl

        print(
            f"{rec_id:<30} {acc_num:<8} {trade_type:<12} {sym:<24} {buy_date:<10} {buy_price:>10.2f} {sell_date:<10} {sell_price:>10.2f} {amount:>8.2f} {pl:>12.2f}"
        )

    print(f"\nTotal Realized P/L: ${total_pl:,.2f} across {len(records)} record(s).")
    return total_pl


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

    _print_realized_table(records)


def handle_calc_realized_command(
    uid: str,
    account_numbers: list[str],
    dry_run: bool = False,
    symbol_filter: str | None = None,
    output_json: bool = False,
) -> None:
    """Iterate over unprocessed transactions, calculate realized P/L, and optionally persist.

    Args:
        uid: Firebase User ID.
        account_numbers: List of account numbers to process.
        dry_run: If True, calculate and display without persisting to Firestore.
        symbol_filter: Optional ticker or OCC option symbol filter.
        output_json: If True, print raw JSON output.
    """
    all_realized: list[dict] = []
    total_processed_ids_count = 0

    for acc_num in account_numbers:
        records, processed_ids = realized.process_account_realized_pl(
            uid=uid, account_number=acc_num, dry_run=dry_run
        )
        all_realized.extend(records)
        total_processed_ids_count += len(processed_ids)

    if symbol_filter and symbol_filter.upper() != "ALL":
        all_realized = [
            r for r in all_realized if firestore_db._matches_realized_symbol(r, symbol_filter)
        ]

    for r in all_realized:
        if not r.get("trade_type"):
            r["trade_type"] = firestore_db._categorize_realized_trade(r)

    if output_json:
        print(json.dumps(all_realized, indent=2, default=str))
        return

    if not all_realized:
        print("No realized P/L transactions calculated from unprocessed transactions.")
        if dry_run:
            print("[DRY RUN] No database changes were made.")
        return

    if dry_run:
        print(f"[DRY RUN] Calculated realized P/L records for {len(account_numbers)} account(s) (NOT saved to Firestore):\n")
    else:
        print(f"Calculated and saved realized P/L records for {len(account_numbers)} account(s):\n")

    _print_realized_table(all_realized)

    if dry_run:
        print(
            f"\n[DRY RUN] {len(all_realized)} realized record(s) calculated, "
            f"{total_processed_ids_count} transaction(s) would be marked processed."
        )
        print("Run without --dry-run to save these records to Firestore.")
    else:
        print(
            f"\nSuccessfully saved {len(all_realized)} realized record(s) "
            f"and marked {total_processed_ids_count} transaction(s) as processed in Firestore."
        )


def handle_order_command(
    uid: str,
    acc_num: str,
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

    action_label = "Previewing" if preview else "Placing"
    print(f"\n{action_label} order for account {acc_num}:")
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
        help="Account name ('ind', 'ira', 'all').",
    )
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        help="Ticker or OCC option symbol (e.g. AAPL, NVDA, 'AAPL  260821C00205000').",
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
    txns_parser.add_argument(
        "--json", action="store_true", help="Output raw database documents in JSON format."
    )

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
        "--json", action="store_true", help="Output raw database documents in JSON format."
    )

    # calc-realized subcommand
    calc_parser = subparsers.add_parser(
        "calc-realized",
        aliases=["calculate-realized", "process-realized"],
        help="Calculate realized P/L from unprocessed transactions.",
    )
    calc_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only calculate and display realized P/L without saving to Firestore or marking transactions processed.",
    )
    calc_parser.add_argument(
        "--json", action="store_true", help="Output calculated realized records in JSON format."
    )

    # order subcommand
    order_parser = subparsers.add_parser(
        "order", aliases=["place-order"], help="Place or preview an order on Charles Schwab."
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
        if account_input in ("ind", "ira"):
            account_input = account_input + "_account"
        account_numbers = constants.resolve_account_numbers(account_input)
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
    elif args.command in ("calc-realized", "calculate-realized", "process-realized"):
        handle_calc_realized_command(
            uid=uid,
            account_numbers=account_numbers,
            dry_run=args.dry_run,
            symbol_filter=args.symbol,
            output_json=args.json,
        )
    elif args.command in ("order", "place-order"):
        if not args.symbol:
            parser.error("the following arguments are required: -s/--symbol")
        is_preview = args.preview
        assert len(account_numbers) == 1
        handle_order_command(
            uid=uid,
            acc_num=account_numbers[0],
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
