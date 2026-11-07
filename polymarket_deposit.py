"""Filtered gross USDC inflows. Uses rujin.py's sender exclusions; no trading."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from http.client import IncompleteRead, RemoteDisconnected
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TOKENS = {
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC.e",
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": "USDC",
}
# Exact address list from Desktop/polymarket/����Ǯ/rujin.py.
# Labels are local rules, not verified official classifications.
EXCLUDED = dict(zip([
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",
    "0xc5d563a36ae78145c45a50134d48a1215220f80a",
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045",
    "0x3a3bd7bb9528e159577f7c2e685cc81a765002e2",
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296",
    "0x9d84ce0306f8551e02efef1680475fc0f1dc1344",
    "0xe3f18acc55091e2c48d883fc8c8413319d4ab7b0",
    "0x3a9418b2651c8164db5ebc56f12008137865e0f7",
    "0xd36ec33c8bed5a9f7b6630855f1533455b98a418",
    "0xf7cd89be08af4d4d6b1522852ced49fc10169f64",
    "0xc288480574783bd7615170660d71753378159c47",
    "0xc536633ff12ee52e280b2af2594031060c5aaf41",
    "0x535ec2dccf77489cc0d1453f088344a2995fccd9",
], ["CTF Exchange", "Neg Risk Exchange", "Conditional Tokens", "Wrapped Collateral",
    "Neg Risk Adapter", "Maker refund", "Relayer", "Internal contract", "USDC swap pool",
    "Rewards", "User exclusion 1", "User exclusion 2", "User exclusion 3"]))


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("Invalid wallet/address")
    return value.lower()


def rpc(url, method, params):
    payload = json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params)).encode()
    for attempt in range(6):
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=60) as response:
                result = json.loads(response.read(), parse_float=Decimal)
            if not isinstance(result, dict) or "error" in result or "result" not in result:
                raise ValueError("RPC error or missing result; no complete total")
            return result["result"]
        except HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 5:
                raise ValueError(f"RPC HTTP {exc.code}") from None
        except (URLError, TimeoutError, IncompleteRead, RemoteDisconnected):
            if attempt == 5:
                raise ValueError("RPC network failure or timeout") from None
        time.sleep(2 ** attempt)


def classify(tx, wallet):
    if address(tx.get("to")) != wallet:
        raise ValueError("Response contains another recipient")
    sender = address(tx.get("from"))
    raw = tx.get("rawContract") or {}
    token = str(raw.get("address", "")).lower()
    if token not in TOKENS:
        raise ValueError("Unexpected token")
    try:
        if raw.get("value") is not None:
            amount = Decimal(int(raw["value"], 16)) / Decimal(1000000)
        else:
            amount = Decimal(str(tx["value"]))
        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid amount")
    except (KeyError, TypeError, InvalidOperation):
        raise ValueError("Missing or invalid transfer amount") from None
    return dict(sender=sender, token=TOKENS[token], amount=str(amount),
                included=sender not in EXCLUDED, reason=EXCLUDED.get(sender, "Sender not excluded"),
                transaction_hash=tx.get("hash"), unique_id=tx.get("uniqueId"),
                timestamp=(tx.get("metadata") or {}).get("blockTimestamp"))


def collect(wallet, call, output):
    wallet = address(wallet)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, rule="rujin_sender_exclusions_v1", wallet=wallet,
                  observed_at=datetime.now(timezone.utc).isoformat(), status="incomplete",
                  gross_deposit=None, excluded_total=None, pages=0, duplicates=0,
                  exclusions=EXCLUDED, tokens=TOKENS)
    included, excluded = Decimal(0), Decimal(0)
    seen, cursors = {}, set()
    try:
        end_block = call("eth_blockNumber", [])
        if not isinstance(end_block, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", end_block):
            raise ValueError("Invalid snapshot block")
        report["to_block"] = end_block
        cursor = None
        with (output / "pages.jsonl").open("w", encoding="utf-8") as pages, \
             (output / "transfers.jsonl").open("w", encoding="utf-8") as details:
            while True:
                params = dict(toAddress=wallet, contractAddresses=list(TOKENS), category=["erc20"],
                              withMetadata=True, excludeZeroValue=True, maxCount="0x64",
                              fromBlock="0x0", toBlock=end_block)
                if cursor:
                    params["pageKey"] = cursor
                result = call("alchemy_getAssetTransfers", [params])
                if not isinstance(result, dict) or not isinstance(result.get("transfers"), list):
                    raise ValueError("Missing transfers list")
                pages.write(json.dumps(dict(params=params, result=result), default=str) + "\n")
                pages.flush()
                report["pages"] += 1
                for tx in result["transfers"]:
                    row = classify(tx, wallet)
                    uid = tx.get("uniqueId")
                    if uid:
                        if uid in seen:
                            if seen[uid] != row:
                                raise ValueError("Conflicting duplicate transfer")
                            report["duplicates"] += 1
                            continue
                        seen[uid] = row
                    # Do not deduplicate by transaction hash: one transaction can have many logs.
                    details.write(json.dumps(row) + "\n")
                    if row["included"]:
                        included += Decimal(row["amount"])
                    else:
                        excluded += Decimal(row["amount"])
                cursor = result.get("pageKey")
                if not cursor:
                    break
                if not isinstance(cursor, str) or cursor in cursors:
                    raise ValueError("Invalid or repeated pagination cursor")
                cursors.add(cursor)
        report.update(status="complete", gross_deposit=str(included), excluded_total=str(excluded))
    except Exception:
        report["error"] = "Query or validation failed; inspect captured pages. Total is unavailable."
        raise
    finally:
        report["sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in output.glob("*.jsonl")}
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Calculate filtered gross deposits using rujin.py rules")
    parser.add_argument("wallet")
    parser.add_argument("--output", type=Path, help="New output directory (must not exist)")
    args = parser.parse_args()
    try:
        wallet = address(args.wallet)
        url = os.environ.get("POLYGON_RPC_URL", "")
        if not url.startswith("https://"):
            raise ValueError("Set POLYGON_RPC_URL to an HTTPS Alchemy Polygon endpoint")
        output = args.output or Path(__file__).parent / "results" / (wallet + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        result = collect(wallet, lambda method, params: rpc(url, method, params), output)
        print("Filtered gross deposit (USDC + USDC.e):", result["gross_deposit"])
        print("Excluded:", result["excluded_total"])
        print("Evidence:", output.resolve())
        return 0
    except Exception as exc:
        # Never print network exception text: it can contain an API key URL.
        print("FAILED:", type(exc).__name__, "No complete deposit total. Check RPC setup and evidence.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

