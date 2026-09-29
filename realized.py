"""
realized.py
~~~~~~~~~~~
Service module for normalizing raw transactions and calculating realized
profit/loss using FIFO (First-In, First-Out) matching.
"""

import csv
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

ROTH_REALIZED_CSV_PATH = os.environ.get("ROTH_REALIZED_CSV_PATH", "")


def _join_aids(aids) -> str:
    """Return a '_'-joined sorted string of activity IDs."""
    return "_".join(sorted(str(aid) for aid in aids))


def _collect_aids(processed_set: set, record: dict) -> None:
    """Add all activity_ids from *record* into *processed_set*."""
    for aid in record.get("activity_ids", []):
        processed_set.add(str(aid))


def normalize_transactions(txns: list[dict]) -> list[dict]:
    """Normalize Firestore raw transactions into a flat representation for calculations.

    Args:
        txns: List of raw transaction dictionaries from Firestore.

    Returns:
        List of normalized transaction dictionaries.
    """
    rows = []
    for txn in txns:
        txn_type = txn.get("type")
        net_amount = txn.get("netAmount", 0.0)
        time_str = txn.get("time")
        if time_str:
            time_str = time_str[:10]
        account_num = txn.get("accountNumber")

        transfer_items = txn.get("transferItems", [])
        for item in transfer_items:
            if not item:
                continue
            instrument = item.get("instrument", {}) or {}
            pos_effect = item.get("positionEffect")

            is_valid = False
            if pos_effect is not None:
                is_valid = True
            elif txn_type == "DIVIDEND_OR_INTEREST" and net_amount < 0:
                is_valid = True
                pos_effect = "INTEREST"

            if not is_valid:
                continue

            symbol = instrument.get("symbol", "")
            if symbol.startswith("SPX"):
                continue
            instrument_id = instrument.get("instrumentId", "")
            amount = item.get("amount", 0.0)
            cost = item.get("cost", 0.0)
            price = item.get("price", 0.0)

            if (amount < 0 and pos_effect == "OPENING") or (amount > 0 and pos_effect == "CLOSING"):
                sl = "short"
            else:
                sl = "long"

            rows.append(
                {
                    "activityId": (
                        str(txn["activityId"]) if txn.get("activityId") is not None else None
                    ),
                    "accountNumber": account_num,
                    "time": time_str,
                    "symbol": symbol,
                    "instrumentId": instrument_id,
                    "amount": amount,
                    "cost": cost,
                    "price": price,
                    "netAmount": net_amount,
                    "positionEffect": pos_effect,
                    "sl": sl,
                }
            )
    return rows


def calculate_realized_pl_with_status(txns: list[dict]) -> tuple[list[dict], set[str]]:
    """Calculate realized gain and losses using FIFO matching, returning
    realized records and activity IDs of fully matched raw transactions.

    Args:
        txns: List of raw transaction dictionaries from Firestore.

    Returns:
        Tuple of (list of realized P/L records, set of processed activity IDs).
    """
    rows = normalize_transactions(txns)

    # Group transactions by key fields to consolidate partial fills
    aggregated: dict = {}
    for r in rows:
        key = (
            r["accountNumber"],
            r["time"],
            r["symbol"],
            r["instrumentId"],
            r["positionEffect"],
            r["sl"],
        )
        if key not in aggregated:
            aggregated[key] = {
                "amount_sum": r["amount"],
                "cost_sum": r["cost"],
                "price_list": [r["price"]],
                "netAmount_sum": r["netAmount"],
                "activity_ids": [str(r["activityId"])] if r.get("activityId") is not None else [],
            }
        else:
            aggregated[key]["amount_sum"] += r["amount"]
            aggregated[key]["cost_sum"] += r["cost"]
            aggregated[key]["price_list"].append(r["price"])
            aggregated[key]["netAmount_sum"] += r["netAmount"]
            if r.get("activityId") is not None:
                aggregated[key]["activity_ids"].append(str(r["activityId"]))

    grouped_rows = []
    for key, val in aggregated.items():
        avg_price = sum(val["price_list"]) / len(val["price_list"]) if val["price_list"] else 0.0
        grouped_rows.append(
            {
                "accountNumber": key[0],
                "time": key[1],
                "symbol": key[2],
                "positionEffect": key[4],
                "sl": key[5],
                "amount": abs(val["amount_sum"]),
                "cost": val["cost_sum"],
                "price": avg_price,
                "netAmount": val["netAmount_sum"],
                "activity_ids": val["activity_ids"],
            }
        )

    # Two-pass stable sort:
    # 1. Sort by positionEffect descending so OPENING processed before CLOSING.
    # 2. Sort by (accountNumber, time) ascending.
    grouped_rows.sort(key=lambda x: x["positionEffect"] or "", reverse=True)
    grouped_rows.sort(key=lambda x: (x["accountNumber"] or "", x["time"] or ""))

    opened: dict[str, list] = {}
    result = []
    processed_activity_ids = set()

    for idx, row in enumerate(grouped_rows):
        key = f"{row['accountNumber']}_{row['symbol']}_{row['sl']}"

        if row["positionEffect"] == "INTEREST":
            interest_aids = _join_aids(row.get("activity_ids", []))
            rec_id = (
                f"realized_interest_{row['accountNumber']}_{interest_aids}"
                if interest_aids
                else f"realized_{row['accountNumber']}_interest_{row['time']}_{idx}"
            )
            result.append(
                {
                    "accountNumber": row["accountNumber"],
                    "amount": 1.0,
                    "symbol": "MARGIN INTEREST",
                    "buy_date": row["time"],
                    "buy_price": row["netAmount"],
                    "sell_date": row["time"],
                    "sell_price": 0.0,
                    "P/L": row["netAmount"],
                    "id": rec_id,
                }
            )
            _collect_aids(processed_activity_ids, row)
        elif row["positionEffect"] == "OPENING":
            if key in opened:
                opened[key].append(row)
            else:
                opened[key] = [row]
        elif row["positionEffect"] == "CLOSING":
            closing_matched = False
            while key in opened and len(opened[key]) > 0:
                o = opened[key].pop(0)
                matched_quantity = min(o["amount"], row["amount"])

                unit_net_o = o["netAmount"] / o["amount"] if o["amount"] else 0.0
                unit_net_row = row["netAmount"] / row["amount"] if row["amount"] else 0.0
                realized_pl = (unit_net_o + unit_net_row) * matched_quantity

                open_aids = _join_aids(o.get("activity_ids", []))
                close_aids = _join_aids(row.get("activity_ids", []))
                if open_aids and close_aids:
                    rec_id = f"realized_{open_aids}_{close_aids}"
                else:
                    rec_id = f"realized_{row['accountNumber']}_{row['symbol']}_{o['time']}_{row['time']}_{idx}"

                result.append(
                    {
                        "accountNumber": o["accountNumber"],
                        "amount": matched_quantity,
                        "symbol": o["symbol"],
                        "buy_date": o["time"],
                        "buy_price": o["price"],
                        "sell_date": row["time"],
                        "sell_price": row["price"],
                        "P/L": realized_pl,
                        "id": rec_id,
                    }
                )
                closing_matched = True

                if o["amount"] > row["amount"]:
                    o["amount"] -= row["amount"]
                    o["netAmount"] = unit_net_o * o["amount"]
                    opened[key].insert(0, o)
                    _collect_aids(processed_activity_ids, row)
                    break
                elif o["amount"] < row["amount"]:
                    _collect_aids(processed_activity_ids, o)
                    row["amount"] -= o["amount"]
                    row["netAmount"] = unit_net_row * row["amount"]
                else:
                    _collect_aids(processed_activity_ids, o)
                    _collect_aids(processed_activity_ids, row)

                if len(opened[key]) == 0:
                    opened.pop(key)

            if closing_matched and row["amount"] == 0:
                _collect_aids(processed_activity_ids, row)

    result.sort(key=lambda x: x["sell_date"] or "", reverse=True)
    return result, processed_activity_ids


def calculate_realized_pl(txns: list[dict]) -> list[dict]:
    """Calculate realized gain and losses using FIFO matching.

    Args:
        txns: List of raw transaction dictionaries from Firestore.

    Returns:
        List of realized gain/loss records sorted by sell_date descending.
    """
    result, _ = calculate_realized_pl_with_status(txns)
    return result


def process_account_realized_pl(uid: str, account_number: str) -> int:
    """Fetch unprocessed raw transactions for an account, calculate realized P/L,
    save realized records to Firestore, and mark matched transactions processed.

    Args:
        uid: User ID.
        account_number: Schwab account number.

    Returns:
        Number of realized P/L records saved.
    """
    import firestore_db

    txns = firestore_db.get_unprocessed_transactions(uid, account_number)
    if not txns:
        return 0
    realized_records, processed_ids = calculate_realized_pl_with_status(txns)
    if realized_records:
        firestore_db.save_realized_pl_transactions(uid, account_number, realized_records)
    if processed_ids:
        firestore_db.mark_transactions_processed(uid, account_number, processed_ids)
    return len(realized_records)


def _format_csv_symbol(symbol: str) -> str:
    """Format option symbol from CSV (e.g. 'META 09/11/2026 39.00 C') to OCC standard format ('META  260911C00039000')."""
    if not symbol:
        return ""
    parts = symbol.strip().split()
    if len(parts) != 4:
        return symbol.strip()
    ticker, date_str, strike_str, call_put = parts
    try:
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        yymmdd = dt.strftime("%y%m%d")
        strike_val = float(strike_str)
        strike_int = int(round(strike_val * 1000))
        cp = call_put.upper()
        if cp not in ("C", "P"):
            return symbol.strip()
        return f"{ticker:<6}{yymmdd}{cp}{strike_int:08d}"
    except Exception:
        return symbol.strip()


def load_csv_realized_pl(
    csv_path: str | None = None,
    account_number: str | None = None,
) -> list[dict]:
    """Read and parse realized P/L transactions from Schwab export CSV file.

    Args:
        csv_path: Path to the realized details CSV file (defaults to ROTH_REALIZED_CSV_PATH).
        account_number: Target account number/suffix (defaults to SECONDARY_ACCOUNT_SUFFIX).

    Returns:
        List of realized P/L transaction dictionaries.
    """
    path = csv_path if csv_path is not None else ROTH_REALIZED_CSV_PATH
    if not path or not os.path.exists(path):
        logger.warning("Realized P/L CSV file not found at %s", path)
        return []

    target_acc_num = account_number or os.environ.get("SECONDARY_ACCOUNT_SUFFIX", "")

    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        header_idx = None
        for i, row in enumerate(rows):
            if row and len(row) > 0 and row[0].strip() == "Symbol":
                header_idx = i
                break

        if header_idx is None:
            logger.warning("Header 'Symbol' not found in CSV file %s", path)
            return []

        def parse_num(val: str) -> float:
            if not val:
                return 0.0
            v = val.replace("$", "").replace(",", "").strip()
            return float(v)

        def parse_date(val: str) -> str:
            if not val:
                return ""
            try:
                return datetime.strptime(val.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                return val.strip()

        records = []
        for row in rows[header_idx + 1 :]:
            if not row or len(row) < 10 or not row[0].strip():
                continue
            symbol = _format_csv_symbol(row[0].strip())
            closed_date = parse_date(row[2])
            opened_date = parse_date(row[3])
            qty = parse_num(row[4])
            proceeds_per_share = parse_num(row[5])
            cost_per_share = parse_num(row[6])
            gain_loss = parse_num(row[9])

            records.append(
                {
                    "accountNumber": target_acc_num,
                    "amount": qty,
                    "symbol": symbol,
                    "buy_date": opened_date,
                    "buy_price": cost_per_share,
                    "sell_date": closed_date,
                    "sell_price": proceeds_per_share,
                    "P/L": gain_loss,
                    "id": f"csv_{target_acc_num}_{opened_date}_{closed_date}_{symbol}_{qty}",
                }
            )

        records.sort(key=lambda x: x.get("sell_date", ""), reverse=True)
        return records
    except Exception as e:
        logger.warning("Error loading realized P/L CSV from %s: %s", path, e)
        return []
