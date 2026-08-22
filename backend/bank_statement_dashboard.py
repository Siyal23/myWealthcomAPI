"""
Bank Statement -> Cash Flow Dashboard

Run:
    python bank_statement_dashboard.py

Then open:
    http://127.0.0.1:8000/

The backend accepts a bank-statement PDF, sends it to Claude for:
1) raw transaction extraction
2) transaction classification

It then calculates the dashboard metrics and serves the dashboard page.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_HTML = BASE_DIR / "spend_dashboard_dynamic.html"
DATA_JSON = BASE_DIR / "dashboard_data.json"

load_dotenv()
EXTRACTION_MAX_TOKENS = 5000
CLASSIFICATION_MAX_TOKENS = 1500
EXTRACTION_CHUNK_PAGES = 2
CLASSIFICATION_CHUNK_SIZE = 30
MODEL_NAME = os.getenv("MODEL_NAME")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is not set in the environment.")

if not MODEL_NAME:
    raise RuntimeError("MODEL_NAME is not set in the environment.")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

TOTAL_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
}


app = FastAPI(title="Bank Statement Cash Flow Dashboard")


EXTRACTION_PROMPT = r"""
You are extracting transaction rows from a bank statement PDF.

Output ONLY valid JSON — an array of transaction objects. Do not output prose,
explanations, markdown fences, or any other text.

Each transaction object must contain exactly these fields:

{
  "date": "DD/MM/YYYY",
  "raw_description": "string",
  "ref_no": "string or null",
  "debit": "number or null",
  "credit": "number or null",
  "balance": "number",
  "ocr_uncertain": "boolean"
}

Rules:

1. Extract EVERY transaction row from EVERY page, in the exact order they appear.

2. Do not summarize, merge, combine, deduplicate, or skip transactions, even
   when multiple transactions have the same date, amount, counterparty, or
   description.

3. Use the transaction's Value Date for `date`, formatted DD/MM/YYYY.

4. `raw_description` must contain the complete transaction narration/details
   exactly as printed in the statement.
   - Preserve UPI/IMPS/NEFT/RTGS/cheque/reference information.
   - Do not shorten, clean, classify, or interpret it.
   - A narration that wraps over several PDF lines is still ONE description.

5. `ref_no` must come ONLY from the statement's dedicated Ref No./Cheque No.
   column.
   - If that column contains "-" or is blank, return null.
   - Do not copy the UPI transaction ID into ref_no.

6. `debit` comes ONLY from the Debit column.
   - Blank or "-" means null.

7. `credit` comes ONLY from the Credit column.
   - Blank or "-" means null.

8. `balance` comes ONLY from the Balance column.
   - Remove currency symbols and thousands separators when converting to a number.

9. Do not classify or interpret transactions. Do not create category,
   counterparty, bucket, direction, investment, expense, or transfer fields.

10. Skip all non-transaction rows:
    statement headers, column headers, account information, page numbers,
    page totals, statement summaries, brought-forward rows, closing summaries,
    bank notices, and footers.

11. If a transaction continues across a page boundary, keep it as one transaction.

12. Never infer a missing amount from the balance or from another transaction.

13. If OCR or PDF rendering makes any transaction value/text uncertain, use the
    best reading and set ocr_uncertain=true. Otherwise set false.

14. Before returning the result, verify that the output is valid JSON and that
    every transaction row is represented exactly once and in statement order.
"""


CLASSIFICATION_PROMPT = r"""
Classify each supplied bank transaction.

Return ONLY valid JSON, no prose or markdown.
Return one compact object per input:
{"index": integer, "counterparty": "short name", "bucket": "CODE"}

Allowed bucket codes:
HDFC = own HDFC transfer
INV = investment/broker/mutual fund/clearing
RUTU = Rutugandha
RENT = clearly identified rent
BILL = utility/telecom/insurance/household bill
FOOD = food/grocery/delivery/restaurant
SUB = subscription/membership
PERSON = person-to-person UPI
BANK = bank-generated credit/refund/interest/NACH
OTHER = other clear spend

Use only evidence in the narration and debit/credit direction.
Do not invent identities. Counterparty should be 1-4 words, or "Unknown".
"""



def parse_json_response(text: str) -> Any:
    cleaned = (text or "").strip()

    # Remove markdown fences if Claude added them.
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Find the first complete JSON value and ignore accidental text
        # after it.
        decoder = json.JSONDecoder()

        start_positions = [
            cleaned.find("["),
            cleaned.find("{"),
        ]
        start_positions = [p for p in start_positions if p >= 0]

        if not start_positions:
            raise

        start = min(start_positions)

        value, _ = decoder.raw_decode(cleaned[start:])
        return value

def call_claude(
    content: list[dict[str, Any]],
    max_tokens: int,
    operation: str = "",
) -> str:
    parts = []

    with client.messages.stream(
        model=MODEL_NAME,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    ) as stream:

        for text in stream.text_stream:
            parts.append(text)

        final_message = stream.get_final_message()

    usage = final_message.usage

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_creation = getattr(
        usage, "cache_creation_input_tokens", 0
    ) or 0
    cache_read = getattr(
        usage, "cache_read_input_tokens", 0
    ) or 0

    print("\n" + "=" * 60)
    print(f"Claude operation : {operation}")
    print(f"Model            : {MODEL_NAME}")
    print(f"Input tokens     : {input_tokens:,}")
    print(f"Output tokens    : {output_tokens:,}")
    print(f"Cache write      : {cache_creation:,}")
    print(f"Cache read       : {cache_read:,}")
    print(f"Total tokens     : {input_tokens + output_tokens:,}")
    TOTAL_USAGE["input_tokens"] += input_tokens
    TOTAL_USAGE["output_tokens"] += output_tokens
    TOTAL_USAGE["cache_creation_input_tokens"] += cache_creation
    TOTAL_USAGE["cache_read_input_tokens"] += cache_read

    print("=" * 60)

    if not parts:
        raise ValueError("Claude returned no text content.")

    return "".join(parts).strip()


def extract_transactions_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Extract PDF text locally and send small page chunks to Claude.
    This prevents a large statement from requiring a huge single response.
    """
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages.append(f"--- PAGE {page_number} ---\n{text}")

    if not any(p.strip() for p in pages):
        raise ValueError("No readable text was extracted from the PDF.")

    all_transactions: list[dict[str, Any]] = []

    for start in range(0, len(pages), EXTRACTION_CHUNK_PAGES):
        end = min(start + EXTRACTION_CHUNK_PAGES, len(pages))
        chunk = "\n\n".join(pages[start:end])

        chunk_prompt = (
            EXTRACTION_PROMPT
            + "\n\nThis request contains only pages "
            + f"{start + 1}-{end}. Extract transactions from these pages only."
            + "\nDo not include transactions from other pages."
            + "\n\nPDF TEXT:\n"
            + chunk
        )

        text = call_claude(
            [{"type": "text", "text": chunk_prompt}],
            max_tokens=EXTRACTION_MAX_TOKENS,
            operation=f"PDF extraction pages {start + 1}-{end}",
        )
        transactions = parse_json_response(text)

        if not isinstance(transactions, list):
            raise ValueError(
                f"Extraction for pages {start + 1}-{end} was not a JSON array."
            )

        validate_raw_transactions(transactions)
        all_transactions.extend(transactions)

    if not all_transactions:
        raise ValueError("No transactions were extracted from the statement.")

    return all_transactions


def validate_raw_transactions(transactions: list[dict[str, Any]]) -> None:
    required = {
        "date",
        "raw_description",
        "ref_no",
        "debit",
        "credit",
        "balance",
        "ocr_uncertain",
    }

    for index, tx in enumerate(transactions):
        if set(tx.keys()) != required:
            raise ValueError(
                f"Raw transaction {index + 1} has incorrect fields: {set(tx.keys())}"
            )

        if not isinstance(tx["date"], str):
            raise ValueError(f"Transaction {index + 1}: date is not a string.")

        if tx["debit"] is not None and not isinstance(tx["debit"], (int, float)):
            raise ValueError(f"Transaction {index + 1}: debit is not numeric/null.")

        if tx["credit"] is not None and not isinstance(tx["credit"], (int, float)):
            raise ValueError(f"Transaction {index + 1}: credit is not numeric/null.")

        if not isinstance(tx["balance"], (int, float)):
            raise ValueError(f"Transaction {index + 1}: balance is not numeric.")

        if not isinstance(tx["ocr_uncertain"], bool):
            raise ValueError(f"Transaction {index + 1}: ocr_uncertain is not boolean.")


def _local_classification(index: int, tx: dict[str, Any]) -> dict[str, Any] | None:
    d = str(tx["raw_description"]).upper()
    incoming = money(tx["credit"]) > 0

    def r(cp: str, bucket: str):
        return {"index": index, "counterparty": cp, "bucket_code": bucket}

    if ("HDFC" in d and "SIYAL" in d) or "7020646117" in d:
        return r("SIYAL DE", "HDFC")
    if "ZERODHA" in d:
        return r("Zerodha", "INV")
    if "INDIAN CLEARING" in d or "ICCL" in d:
        return r("Indian Clearing Corp", "INV")
    if "RUTUGAND" in d:
        return r("Rutugandha", "RUTU")

    merchants = {
        "ZOMATO": "Zomato",
        "ZEPTO": "Zepto",
        "BLINKIT": "Blinkit",
        "EATCLUB": "EatClub",
        "LICIOUS": "Licious",
        "APPLE": "Apple",
        "UBER": "Uber",
    }
    for key, cp in merchants.items():
        if key in d:
            return r(cp, "FOOD" if key not in {"APPLE", "UBER"} else
                     ("SUB" if key == "APPLE" else "OTHER"))

    if incoming and any(
        x in d for x in ("INTEREST", "INT.PD", "NACH", "REFUND", "REVERSAL")
    ):
        return r("Bank", "BANK")
    return None


_BUCKETS = {
    "HDFC": "Self Transfer (HDFC)",
    "INV": "Investment",
    "RUTU": "Rutugandha (Person)",
    "RENT": "Rent",
    "BILL": "Bills",
    "FOOD": "Food & Delivery",
    "SUB": "Subscription",
    "PERSON": "Person UPI",
    "BANK": "Bank Credit",
    "OTHER": "Other Spend",
}


def build_final_category(counterparty: str, bucket_code: str) -> str:
    category_map = {
        "HDFC": "Own HDFC Account Transfer (Self)",
        "INV": f"{counterparty} (Investment)",
        "RUTU": "Rutugandha (Person)",
        "RENT": "Rent",
        "BILL": f"{counterparty} (Bill)",
        "FOOD": f"{counterparty} (Food/Delivery)",
        "SUB": f"{counterparty} (Subscription)",
        "PERSON": "Person-to-Person UPI",
        "BANK": "Bank Credit",
        "OTHER": f"{counterparty} (Other Spend)",
    }
    return category_map.get(bucket_code, f"{counterparty} (Other Spend)")


def build_direction_category(
    tx: dict[str, Any],
    counterparty: str,
    bucket_code: str,
) -> str:
    debit = money(tx["debit"])
    credit = money(tx["credit"])

    if bucket_code == "HDFC":
        return (
            "SBI -> HDFC (transferred to own HDFC a/c)"
            if debit > 0
            else "HDFC -> SBI (received from own HDFC a/c)"
        )

    if bucket_code == "INV":
        return (
            f"SBI -> {counterparty} (investment)"
            if debit > 0
            else f"{counterparty} -> SBI (received)"
        )

    if bucket_code == "BANK":
        return "Bank Credit received"

    if debit > 0:
        return f"SBI -> {counterparty} (sent)"
    if credit > 0:
        return f"{counterparty} -> SBI (received)"
    return counterparty


def _apply_classification(
    tx: dict[str, Any],
    classification: dict[str, Any],
) -> None:
    bucket_code = (
        classification.get("bucket")
        or classification.get("bucket_code")
    )
    counterparty = classification.get("counterparty") or "Unknown"

    if not bucket_code:
        raise ValueError(
            f"Classification is missing bucket/bucket_code: {classification}"
        )

    if bucket_code not in _BUCKETS:
        raise ValueError(
            f"Unknown bucket code '{bucket_code}' "
            f"for classification: {classification}"
        )

    tx["counterparty"] = counterparty
    tx["bucket"] = _BUCKETS[bucket_code]
    tx["final_category"] = build_final_category(
        counterparty, bucket_code
    )
    tx["direction_category"] = build_direction_category(
        tx, counterparty, bucket_code
    )


def validate_classification_schema(
    classification: dict[str, Any],
    source: str = "unknown",
) -> None:
    if not isinstance(classification, dict):
        raise ValueError(
            f"{source}: classification is not an object: {classification!r}"
        )

    if "index" not in classification:
        raise ValueError(
            f"{source}: missing 'index': {classification}"
        )

    if "counterparty" not in classification:
        raise ValueError(
            f"{source}: missing 'counterparty': {classification}"
        )

    bucket = (
        classification.get("bucket")
        or classification.get("bucket_code")
    )
    if not bucket:
        raise ValueError(
            f"{source}: missing 'bucket' or 'bucket_code': {classification}"
        )

    if bucket not in _BUCKETS:
        raise ValueError(
            f"{source}: invalid bucket '{bucket}'. "
            f"Allowed values: {sorted(_BUCKETS)}"
        )


def classify_transactions(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    final = [dict(tx) for tx in transactions]
    unresolved: list[int] = []

    # First classify obvious transactions locally.
    for i, tx in enumerate(final):
        local = _local_classification(i, tx)

        if local is None:
            unresolved.append(i)
            continue

        validate_classification_schema(
            local,
            source=f"local classification transaction {i}",
        )
        _apply_classification(tx, local)

    # Send only ambiguous transactions to Claude.
    for start in range(0, len(unresolved), CLASSIFICATION_CHUNK_SIZE):
        batch = unresolved[start:start + CLASSIFICATION_CHUNK_SIZE]

        compact = [
            {
                "index": i,
                "description": final[i]["raw_description"],
                "debit": final[i]["debit"],
                "credit": final[i]["credit"],
            }
            for i in batch
        ]

        prompt = (
            CLASSIFICATION_PROMPT
            + "\n\nINPUT:\n"
            + json.dumps(
                compact,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

        text = call_claude(
            [{"type": "text", "text": prompt}],
            max_tokens=CLASSIFICATION_MAX_TOKENS,
            operation=(
                f"Transaction classification "
                f"{start + 1}-{start + len(batch)}"
            ),
        )

        classified = parse_json_response(text)

        if not isinstance(classified, list):
            raise ValueError(
                "Classification result is not a JSON array."
            )

        if len(classified) != len(batch):
            raise ValueError(
                f"Classification count mismatch: expected {len(batch)}, "
                f"got {len(classified)}."
            )

        seen: set[int] = set()

        for item in classified:
            validate_classification_schema(
                item,
                source="Claude classification",
            )

            if set(item.keys()) != {
                "index",
                "counterparty",
                "bucket",
            }:
                raise ValueError(
                    "Compact classification returned unexpected fields: "
                    f"{set(item.keys())}"
                )

            i = int(item["index"])

            if i not in batch or i in seen:
                raise ValueError(
                    f"Invalid/duplicate classification index: {i}"
                )

            seen.add(i)
            _apply_classification(final[i], item)

        missing = set(batch) - seen
        if missing:
            raise ValueError(
                f"Claude did not classify transaction indexes: "
                f"{sorted(missing)}"
            )

    validate_classified_transactions(final)
    return final


def validate_classified_transactions(
    transactions: list[dict[str, Any]],
) -> None:
    expected = {
        "date",
        "raw_description",
        "ref_no",
        "debit",
        "credit",
        "balance",
        "ocr_uncertain",
        "counterparty",
        "final_category",
        "bucket",
        "direction_category",
    }

    for index, tx in enumerate(transactions):
        if set(tx.keys()) != expected:
            missing = expected - set(tx.keys())
            extra = set(tx.keys()) - expected
            raise ValueError(
                f"Classified transaction {index + 1} has incorrect fields. "
                f"Missing={sorted(missing)}, Extra={sorted(extra)}"
            )

        if tx["bucket"] not in set(_BUCKETS.values()):
            raise ValueError(
                f"Classified transaction {index + 1} has unsupported bucket: "
                f"{tx['bucket']}"
            )

        if not isinstance(tx["counterparty"], str):
            raise ValueError(
                f"Classified transaction {index + 1}: "
                "counterparty must be a string."
            )

        if not isinstance(tx["final_category"], str):
            raise ValueError(
                f"Classified transaction {index + 1}: "
                "final_category must be a string."
            )

        if not isinstance(tx["direction_category"], str):
            raise ValueError(
                f"Classified transaction {index + 1}: "
                "direction_category must be a string."
            )


def money(value: Any) -> float:
    return round(float(value or 0), 2)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%d/%m/%Y")


def format_period(dates: list[str]) -> str:
    parsed = [parse_date(d) for d in dates]
    first = min(parsed)
    last = max(parsed)

    if first.year == last.year and first.month == last.month:
        return f"{first.strftime('%b')} {first.day}–{last.day} {first.year}"

    if first.year == last.year:
        return f"{first.strftime('%b')} {first.day}–{last.strftime('%b')} {last.day} {first.year}"

    return f"{first.strftime('%d %b %Y')}–{last.strftime('%d %b %Y')}"


def mask_account_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 4:
        return "····" + digits
    return "····" + digits[-4:]


def extract_account_metadata(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Best-effort metadata extraction. This is deliberately not used to
    construct transactions, so a failure here cannot alter transaction data.
    """
    text = ""
    try:
        import io

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages[:2])
    except Exception:
        pass

    bank = "Bank"
    if re.search(r"\bState Bank of India\b|\bSBI\b", text, re.I):
        bank = "SBI"

    account_match = re.search(r"Account Number\s*:?\s*(\d{6,})", text, re.I)
    account_masked = mask_account_number(account_match.group(1)) if account_match else None

    return {
        "bank": bank,
        "account_masked": account_masked,
    }


def build_dashboard_data(
    transactions: list[dict[str, Any]],
    pdf_bytes: bytes,
) -> dict[str, Any]:
    if not transactions:
        raise ValueError("No transactions were extracted from the statement.")

    dates = [tx["date"] for tx in transactions]
    ordered = sorted(
        transactions,
        key=lambda tx: (
            parse_date(tx["date"]),
            transactions.index(tx),
        ),
    )

    total_debits = round(sum(money(tx["debit"]) for tx in transactions), 2)
    total_credits = round(sum(money(tx["credit"]) for tx in transactions), 2)

    first = transactions[0]
    opening_balance = round(
        money(first["balance"])
        - money(first["credit"])
        + money(first["debit"]),
        2,
    )
    closing_balance = money(transactions[-1]["balance"])

    hdfc_out = hdfc_in = 0.0
    investment_out = investment_in = 0.0
    rutu_out = rutu_in = 0.0

    spend_by_bucket: dict[str, float] = defaultdict(float)

    for tx in transactions:
        debit = money(tx["debit"])
        credit = money(tx["credit"])
        bucket = tx.get("bucket") or "Other Spend"

        if bucket == "Self Transfer (HDFC)":
            hdfc_out += debit
            hdfc_in += credit
        elif bucket == "Investment":
            investment_out += debit
            investment_in += credit
        elif bucket == "Rutugandha (Person)":
            rutu_out += debit
            rutu_in += credit

        spend_by_bucket[bucket] += debit - credit

    true_spend_buckets = [
        "Rent",
        "Bills",
        "Food & Delivery",
        "Subscription",
        "Person UPI",
        "Other Spend",
    ]

    true_spend = round(
        sum(spend_by_bucket[b] for b in true_spend_buckets),
        2,
    )

    # Last transaction of each day = daily closing balance.
    daily_closing: dict[str, dict[str, Any]] = {}
    for tx in transactions:
        daily_closing[tx["date"]] = tx

    balance_over_time = [
        {
            "date": date,
            "balance": money(daily_closing[date]["balance"]),
        }
        for date in sorted(daily_closing, key=parse_date)
    ]

    spend_categories = []
    for bucket in true_spend_buckets:
        value = round(spend_by_bucket[bucket], 2)
        if value > 0:
            spend_categories.append({"label": bucket, "value": value})

    metadata = extract_account_metadata(pdf_bytes)
    metadata.update(
        {
            "period_label": format_period(dates),
            "transaction_count": len(transactions),
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "total_debits": total_debits,
            "total_credits": total_credits,
            "true_spend": true_spend,
            "hdfc_net": round(hdfc_out - hdfc_in, 2),
            "investment_net": round(investment_out - investment_in, 2),
            "rutugandha_net": round(rutu_in - rutu_out, 2),
            "true_spend_buckets": true_spend_buckets,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    # Keep the field names expected by the existing dashboard.
    dashboard_transactions = []
    for tx in transactions:
        dashboard_transactions.append(
            {
                "Date": tx["date"],
                "Details": tx["raw_description"],
                "RefNo": tx["ref_no"],
                "Counterparty": tx["counterparty"],
                "Final_Category": tx["final_category"],
                "Debit": money(tx["debit"]),
                "Credit": money(tx["credit"]),
                "Balance": money(tx["balance"]),
                "Direction_Category": tx["direction_category"],
                "Bucket": tx["bucket"],
                "DateSort": parse_date(tx["date"]).strftime("%Y-%m-%d"),
                "OCR_Uncertain": tx["ocr_uncertain"],
            }
        )

    return {
        "meta": metadata,
        "flow": {
            "true_spend": round(
                sum(
                    money(tx["debit"])
                    for tx in transactions
                    if tx["bucket"] in true_spend_buckets
                ),
                2,
            ),
            "to_hdfc": round(hdfc_out, 2),
            "invested": round(investment_out, 2),
            "to_rutugandha": round(rutu_out, 2),
        },
        "spend_by_category": spend_categories,
        "balance_over_time": balance_over_time,
        "transactions": dashboard_transactions,
    }


async def process_statement(pdf_bytes: bytes) -> dict[str, Any]:
    raw_transactions = extract_transactions_from_pdf(pdf_bytes)
    classified_transactions = classify_transactions(raw_transactions)

    dashboard = build_dashboard_data(classified_transactions, pdf_bytes)

    total_tokens = (
        TOTAL_USAGE["input_tokens"]
        + TOTAL_USAGE["output_tokens"]
    )
    print("\n" + "=" * 60)
    print("TOTAL CLAUDE USAGE")
    print(f"Input tokens     : {TOTAL_USAGE['input_tokens']:,}")
    print(f"Output tokens    : {TOTAL_USAGE['output_tokens']:,}")
    print(f"Cache write      : {TOTAL_USAGE['cache_creation_input_tokens']:,}")
    print(f"Cache read       : {TOTAL_USAGE['cache_read_input_tokens']:,}")
    print(f"Total tokens     : {total_tokens:,}")
    print("=" * 60)

    DATA_JSON.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return dashboard


@app.get("/")
async def dashboard_page():
    if not DASHBOARD_HTML.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Dashboard HTML not found: {DASHBOARD_HTML}",
        )
    return FileResponse(DASHBOARD_HTML)


@app.get("/api/dashboard-data")
async def dashboard_data():
    if not DATA_JSON.exists():
        return JSONResponse(
            {
                "meta": {},
                "transactions": [],
                "error": "No processed statement yet. Upload a PDF first.",
            }
        )

    return JSONResponse(json.loads(DATA_JSON.read_text(encoding="utf-8")))


@app.post("/api/process-statement")
async def process_statement_endpoint(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF bank statement.")

    pdf_bytes = await file.read()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

    try:
        dashboard = await process_statement(pdf_bytes)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "message": "Statement processed successfully.",
        "filename": file.filename,
        "transaction_count": dashboard["meta"]["transaction_count"],
        "period": dashboard["meta"]["period_label"],
        "true_spend": dashboard["meta"]["true_spend"],
        "opening_balance": dashboard["meta"]["opening_balance"],
        "closing_balance": dashboard["meta"]["closing_balance"],
    }


if __name__ == "__main__":
    uvicorn.run(
        "bank_statement_dashboard:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
