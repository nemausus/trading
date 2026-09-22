#!/usr/bin/env python3
"""
script.py
~~~~~~~~~
Standalone administrative and debugging CLI script to inspect raw transactions
and realized P/L records stored in Firestore outside of the web application.

Reuses firestore_db.py, constants.py, and realized.py services directly.

Usage examples:
    python script.py --account acc2 txns --limit 100
    python script.py --account primary realized --limit 50
    python script.py --account all txns --unprocessed
    python script.py --account acc1 realized --json
"""

import argparse
import json
import os
import sys
from dotenv import load_dotenv

# Ensure environment variables from .env are loaded at startup
load_dotenv()

from roll_chain import extract_underlying_symbol
import constants
import firestore_db


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

    env_uid = os.environ.get('DEFAULT_UID')
    if env_uid:
        return env_uid

    try:
        db = firestore_db.get_db()
        users = list(db.collection('users').limit(1).stream())
        if users:
            return users[0].id
    except Exception as err:
        raise RuntimeError(f"Failed to auto-discover user UID from Firestore: {err}") from err

    raise RuntimeError("No user UID specified and no users found in Firestore.")


def resolve_account_hashes(account_input: str | None) -> list[str]:
    """Resolve account argument into a list of encrypted account hashes.

    Args:
        account_input: Account suffix ('acc2', 'acc1'), alias ('primary', 'secondary',
            'ira', 'ind', 'all'), or full account hash string.

    Returns:
        List of matching account hash strings.
    """
    if not account_input or account_input.lower() == 'all':
        return constants.get_all_account_hashes()

    acc_lower = account_input.lower().strip()
    if acc_lower in ('primary', 'ind'):
        return [constants.get_primary_account_hash()]
    if acc_lower in ('secondary', 'ira', 'roth'):
        return [constants.get_secondary_account_hash()]

    try:
        return [constants.get_account_hash(account_input)]
    except ValueError:
        return [account_input]


def handle_txns_command(
    uid: str,
    account_hashes: list[str],
    limit: int,
    unprocessed_only: bool,
    symbol_filter: str | None,
    output_json: bool
) -> None:
    """Fetch and display raw transactions for specified account(s)."""
    txns = []
    # If filtering by symbol, fetch a larger candidate pool to ensure we return up to `limit` matches
    fetch_limit = limit * 10 if symbol_filter else limit

    for acc_hash in account_hashes:
        if unprocessed_only:
            t_list = firestore_db.get_unprocessed_transactions(uid, acc_hash, limit=fetch_limit)
        else:
            t_list = firestore_db.get_transactions(uid, acc_hash, limit=fetch_limit)
        txns.extend(t_list)

    # Sort combined results by transaction time descending
    txns.sort(key=lambda x: x.get('time', ''), reverse=True)

    if symbol_filter:
        target_sym = extract_underlying_symbol(symbol_filter).upper()
        raw_target = symbol_filter.strip().upper()
        filtered = []
        for t in txns:
            transfer_items = t.get('transferItems', [])
            match = False
            for item in transfer_items:
                inst = item.get('instrument', {}) or {}
                sym = inst.get('symbol', '')
                und = inst.get('underlyingSymbol') or extract_underlying_symbol(sym)
                if und and und.strip().upper() == target_sym:
                    match = True
                    break
                if sym and sym.strip().upper() == raw_target:
                    match = True
                    break
            if match:
                filtered.append(t)
        txns = filtered

    txns = txns[:limit]

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
        act_id = str(t.get('activityId', 'N/A'))[:15]
        time_str = str(t.get('time', ''))[:10]
        acc_num = t.get('accountNumber') or constants.get_account_number_for_hash(t.get('accountHash', ''))
        processed = str(t.get('processed', False))

        transfer_items = t.get('transferItems', [])
        if transfer_items:
            for item in transfer_items:
                inst = item.get('instrument', {}) or {}
                sym = inst.get('symbol', 'N/A')[:24]
                pos_eff = item.get('positionEffect') or 'N/A'
                amount = item.get('amount', 0.0)
                price = item.get('price', 0.0)
                net_amt = t.get('netAmount', 0.0)
                print(f"{act_id:<15} {time_str:<12} {acc_num:<8} {sym:<24} {pos_eff:<10} {amount:>8.2f} {price:>10.2f} {net_amt:>12.2f} {processed:<10}")
        else:
            net_amt = t.get('netAmount', 0.0)
            txn_type = t.get('type', 'N/A')[:24]
            print(f"{act_id:<15} {time_str:<12} {acc_num:<8} {txn_type:<24} {'N/A':<10} {'0.00':>8} {'0.00':>10} {net_amt:>12.2f} {processed:<10}")

    print(f"\nTotal: {len(txns)} transaction(s) listed.")


def handle_realized_command(
    uid: str,
    account_hashes: list[str],
    limit: int,
    symbol_filter: str | None,
    output_json: bool
) -> None:
    """Fetch and display realized P/L records for specified account(s)."""
    fetch_limit = limit * 10 if symbol_filter else limit
    records = firestore_db.get_realized_pl_for_accounts(uid, account_hashes, limit=fetch_limit)

    if symbol_filter:
        target_sym = extract_underlying_symbol(symbol_filter).upper()
        raw_target = symbol_filter.strip().upper()
        filtered = []
        for r in records:
            sym = r.get('symbol', '')
            und = extract_underlying_symbol(sym)
            if und and und.strip().upper() == target_sym:
                filtered.append(r)
            elif sym and sym.strip().upper() == raw_target:
                filtered.append(r)
        records = filtered

    records = records[:limit]

    if output_json:
        print(json.dumps(records, indent=2, default=str))
        return

    if not records:
        print("No realized P/L records found.")
        return

    header = f"{'Record ID':<30} {'Account':<8} {'Symbol':<24} {'Buy Date':<10} {'Buy Price':>10} {'Sell Date':<10} {'Sell Price':>10} {'Amount':>8} {'P/L ($)':>12}"
    print(header)
    print("-" * len(header))

    total_pl = 0.0
    for r in records:
        rec_id = str(r.get('id', 'N/A'))[:30]
        acc_num = r.get('accountNumber', 'N/A')
        sym = r.get('symbol', 'N/A')[:24]
        buy_date = r.get('buy_date', '')[:10]
        buy_price = r.get('buy_price', 0.0)
        sell_date = r.get('sell_date', '')[:10]
        sell_price = r.get('sell_price', 0.0)
        amount = r.get('amount', 0.0)
        pl = r.get('P/L', 0.0)
        total_pl += pl

        print(f"{rec_id:<30} {acc_num:<8} {sym:<24} {buy_date:<10} {buy_price:>10.2f} {sell_date:<10} {sell_price:>10.2f} {amount:>8.2f} {pl:>12.2f}")

    print(f"\nTotal Realized P/L: ${total_pl:,.2f} across {len(records)} record(s).")


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for the CLI script."""
    parser = argparse.ArgumentParser(
        description="Administrative CLI tool for querying Firestore transactions and realized P/L data."
    )
    parser.add_argument(
        '--account',
        type=str,
        default='all',
        help="Account number suffix (e.g. 'acc2', 'acc1'), alias ('primary', 'secondary', 'all'), or full hash."
    )
    parser.add_argument(
        '--symbol',
        '-s',
        type=str,
        default=None,
        help="Filter by ticker or underlying symbol (e.g. NVDA, IBIT)."
    )
    parser.add_argument(
        '--uid',
        type=str,
        default=None,
        help="Firebase User ID (auto-discovered from Firestore if omitted)."
    )

    subparsers = parser.add_subparsers(dest='command', required=True, help="Subcommand to execute")

    # txns subcommand
    txns_parser = subparsers.add_parser('txns', aliases=['transactions'], help="List raw transactions from Firestore.")
    txns_parser.add_argument('--limit', type=int, default=100, help="Maximum number of transactions to return (default: 100).")
    txns_parser.add_argument('--unprocessed', action='store_true', help="Only return unprocessed raw transactions.")
    txns_parser.add_argument('--json', action='store_true', help="Output results in JSON format.")

    # realized subcommand
    realized_parser = subparsers.add_parser('realized', aliases=['realized-pl'], help="List realized P/L records from Firestore.")
    realized_parser.add_argument('--limit', type=int, default=100, help="Maximum number of realized records to return (default: 100).")
    realized_parser.add_argument('--json', action='store_true', help="Output results in JSON format.")

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        uid = resolve_uid(args.uid)
        account_hashes = resolve_account_hashes(args.account)
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.command in ('txns', 'transactions'):
        handle_txns_command(
            uid=uid,
            account_hashes=account_hashes,
            limit=args.limit,
            unprocessed_only=args.unprocessed,
            symbol_filter=args.symbol,
            output_json=args.json,
        )
    elif args.command in ('realized', 'realized-pl'):
        handle_realized_command(
            uid=uid,
            account_hashes=account_hashes,
            limit=args.limit,
            symbol_filter=args.symbol,
            output_json=args.json,
        )
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
