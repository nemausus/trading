"""
roll_chain.py
~~~~~~~~~~~~~
Service module for discovering and constructing full option rollover chains
from raw Schwab transaction records.
"""

import logging
from option_symbol import base_symbol

logger = logging.getLogger(__name__)


def extract_underlying_symbol(symbol: str) -> str:
    """Extract underlying ticker symbol from option or equity symbol string.

    Args:
        symbol: Option or equity symbol string.

    Returns:
        Cleaned underlying ticker symbol (e.g. 'IBIT', 'AAPL').
    """
    if not symbol:
        return ""
    return base_symbol(symbol).strip().upper()


def filter_transactions_by_underlying(txns: list[dict], underlying_symbol: str) -> list[dict]:
    """Filter raw transactions to those containing transfer items for the specified underlying symbol.

    Args:
        txns: List of raw transaction dicts.
        underlying_symbol: Target underlying ticker symbol (e.g. 'IBIT').

    Returns:
        Filtered list of matching transaction dicts.
    """
    target = underlying_symbol.strip().upper()
    if not target:
        return []

    matching = []
    for t in txns:
        items = t.get("transferItems", [])
        for item in items:
            inst = item.get("instrument", {}) or {}
            und = inst.get("underlyingSymbol")
            if not und:
                und = extract_underlying_symbol(inst.get("symbol", ""))
            if und and und.strip().upper() == target:
                matching.append(t)
                break
    return matching


def build_roll_chain(txns: list[dict], target_symbol: str) -> dict:
    """Reconstruct full rollover chain for a target option position from transactions.

    Args:
        txns: List of raw transaction dicts.
        target_symbol: Target option symbol (e.g. 'IBIT  261002C00040000').

    Returns:
        Dict containing target_symbol, underlying, chain sequence, and summary metrics.
    """
    if not target_symbol:
        return {
            "target_symbol": "",
            "underlying": "",
            "chain": [],
            "summary": {
                "total_legs": 0,
                "is_rolled": False,
                "total_net_amount": 0.0,
                "total_cost": 0.0,
            },
        }

    underlying = extract_underlying_symbol(target_symbol)
    filtered_txns = filter_transactions_by_underlying(txns, underlying)

    # Index option legs by orderId and by symbol
    orders: dict = {}
    symbol_open_map: dict = {}

    for t in filtered_txns:
        order_id = t.get("orderId")
        items = t.get("transferItems", [])
        for item in items:
            inst = item.get("instrument", {}) or {}
            if inst.get("assetType") == "OPTION":
                sym = inst.get("symbol", "").strip()
                if order_id is not None:
                    if order_id not in orders:
                        orders[order_id] = []
                    orders[order_id].append((t, item))

                if item.get("positionEffect") == "OPENING":
                    if sym not in symbol_open_map:
                        symbol_open_map[sym] = []
                    symbol_open_map[sym].append((t, item))

    # Sort symbol_open_map entries by transaction time descending
    for sym in symbol_open_map:
        symbol_open_map[sym].sort(key=lambda x: x[0].get("time", ""), reverse=True)

    chain_nodes = []
    visited_symbols = set()
    chain_txns_map: dict = {}
    current_sym = target_symbol.strip()

    while current_sym and current_sym not in visited_symbols:
        visited_symbols.add(current_sym)
        open_entries = symbol_open_map.get(current_sym, [])
        if not open_entries:
            # Fallback check for symbol string match ignoring whitespace differences
            matched_key = None
            for key in symbol_open_map:
                if key.replace(" ", "") == current_sym.replace(" ", ""):
                    matched_key = key
                    break
            if matched_key:
                open_entries = symbol_open_map[matched_key]
                current_sym = matched_key

        if not open_entries:
            chain_nodes.append(
                {
                    "symbol": current_sym,
                    "action": "UNKNOWN",
                    "time": None,
                    "orderId": None,
                    "amount": 0,
                    "price": 0.0,
                    "cost": 0.0,
                    "netAmount": 0.0,
                    "note": "Opening transaction not found in history",
                }
            )
            break

        open_txn, open_item = open_entries[0]
        order_id = open_txn.get("orderId")
        amount = open_item.get("amount", 0.0)
        price = open_item.get("price", 0.0)
        cost = open_item.get("cost", 0.0)
        time_str = open_txn.get("time", "")
        open_net = open_txn.get("netAmount", 0.0)

        if open_txn.get("activityId"):
            chain_txns_map[open_txn["activityId"]] = open_txn

        action = "STO" if amount < 0 else "BTO"

        node = {
            "symbol": current_sym,
            "action": action,
            "time": time_str,
            "orderId": order_id,
            "amount": abs(amount),
            "price": price,
            "cost": cost,
            "netAmount": open_net,
            "activityId": open_txn.get("activityId"),
        }

        prev_sym = None
        if order_id is not None and order_id in orders:
            order_legs = orders[order_id]
            for close_txn, close_item in order_legs:
                c_inst = close_item.get("instrument", {}) or {}
                c_sym = c_inst.get("symbol", "").strip()
                if close_item.get("positionEffect") == "CLOSING" and c_sym != current_sym:
                    prev_sym = c_sym
                    close_net = close_txn.get("netAmount", 0.0)
                    if close_txn.get("activityId"):
                        chain_txns_map[close_txn["activityId"]] = close_txn

                    node["rolled_from_symbol"] = prev_sym
                    node["close_leg"] = {
                        "symbol": prev_sym,
                        "amount": abs(close_item.get("amount", 0.0)),
                        "price": close_item.get("price", 0.0),
                        "cost": close_item.get("cost", 0.0),
                        "netAmount": close_net,
                        "activityId": close_txn.get("activityId"),
                    }
                    is_same_txn = open_txn.get("activityId") is not None and open_txn.get(
                        "activityId"
                    ) == close_txn.get("activityId")
                    node["roll_net_amount"] = open_net if is_same_txn else (close_net + open_net)
                    break

        chain_nodes.append(node)
        if prev_sym:
            current_sym = prev_sym
        else:
            break

    # Reverse chain so chronological order is [Original Opening] -> ... -> [Current Position]
    chain_nodes.reverse()

    total_net_amount = sum(t.get("netAmount", 0.0) for t in chain_txns_map.values())
    total_cost = sum(n.get("cost", 0.0) for n in chain_nodes)

    summary = {
        "total_legs": len(chain_nodes),
        "is_rolled": len(chain_nodes) > 1,
        "total_net_amount": total_net_amount,
        "total_cost": total_cost,
        "start_date": chain_nodes[0].get("time") if chain_nodes else None,
        "latest_date": chain_nodes[-1].get("time") if chain_nodes else None,
    }

    return {
        "target_symbol": target_symbol,
        "underlying": underlying,
        "chain": chain_nodes,
        "summary": summary,
    }
