# myWealthCom 💰

A **personal finance dashboard application** that processes **bank statement PDFs**, extracts transaction data with AI, classifies transactions, and turns the results into a dynamic cash-flow dashboard. A Python/FastAPI backend powers the processing and serves the dashboard.

The goal is to answer not only **"what category did I spend on?"**, but also **"where did my money actually go?"** — including people, merchants, investments, transfers, and recurring destinations.

## Features 🌟

- **Bank Statement PDF Upload**: Upload a bank statement PDF for processing.
- **AI Transaction Extraction**: Uses Claude to extract transaction rows from bank statement pages.
- **Page-Based Processing**: Large statements are processed in page chunks rather than sending the entire PDF in one large request.
- **Standard Transaction Schema**: Extracts:
  - Date
  - Raw description / narration
  - Reference number
  - Debit
  - Credit
  - Balance
  - OCR uncertainty when applicable
- **Transaction Classification**:
  - Python handles obvious/known transaction patterns locally.
  - Claude classifies transactions that require additional interpretation.
- **Counterparty Tracking**: Keeps track of who or what received/sent money, rather than relying only on broad categories such as Food or Investment.
- **Dynamic Categories**: Transactions are normalized into categories such as spending, investment, self-transfer, bills, food, subscriptions, and person-to-person transfers.
- **Dynamic Cash-Flow Dashboard**: Dashboard insights are generated from the actual statement data rather than hard-coded names such as a specific person or bank account.
- **Top Destinations**: Shows the largest outgoing destinations based on the transactions in the uploaded statement.
- **Token Usage Logging**: Prints Claude input/output/cache usage for each extraction/classification operation and the total usage for the request.
- **Streaming Claude Requests**: Uses streaming for longer Claude operations.
- **JSON Dashboard Data**: Produces transaction/dashboard data consumed by the HTML dashboard.

## Architecture

```text
Bank Statement PDF
        |
        v
   FastAPI Upload
        |
        v
 Extract PDF Pages
        |
        v
 Split into Page Chunks
        |
        v
 Claude - Transaction Extraction
        |
        v
 Raw Transaction JSON
        |
        v
 Python Validation / Normalization
        |
        +----------------------+
        |                      |
        v                      v
 Obvious Transactions     Ambiguous Transactions
 Python Rules             Claude Classification
        |                      |
        +----------+-----------+
                   |
                   v
        Final Transaction Data
                   |
                   v
        Dashboard JSON Data
                   |
                   v
        Dynamic HTML Dashboard
```

## Transaction Extraction

Each extracted transaction is normalized to a common structure:

```json
{
  "date": "DD/MM/YYYY",
  "raw_description": "string",
  "ref_no": "string or null",
  "debit": 1000.00,
  "credit": null,
  "balance": 25000.00
}
```

If OCR makes a row uncertain, the transaction can also contain:

```json
{
  "ocr_uncertain": true
}
```

The extraction process is designed to preserve the original narration instead of cleaning or shortening it, because the narration is later useful for identifying counterparties and classifying transactions.

## Classification

Classification has two stages.

### 1. Local Python classification

Transactions that can be identified reliably from existing rules are classified without another Claude request.

This reduces API usage and keeps obvious classifications deterministic.

### 2. Claude classification

Transactions that cannot be confidently classified locally are sent to Claude.

Claude returns a compact classification containing information such as:

```json
{
  "index": 12,
  "counterparty": "Example Person",
  "bucket": "PERSON"
}
```

Python then normalizes the result into the final dashboard fields.

This separation keeps the expensive AI step focused on transactions that actually need interpretation.

## Dashboard

The dashboard is intentionally **data-driven** rather than being built around one person's statement.

For example, the dashboard does not permanently assume that a user has:

- Rutugandha
- HDFC transfers
- Zerodha
- Any particular merchant

Instead, the UI calculates insights from the uploaded statement.

Examples of dynamic insights include:

- True spend
- Money received
- Investments
- Top outgoing destination
- Where your money went
- Spending by category
- Transaction history
- Balance over time

If one user's largest destination is a friend, that person can appear. If another user's largest destination is Amazon, a credit-card account, a landlord, or an investment account, the dashboard can show that instead.

## Requirements 📋

- Python 3.8+
- FastAPI
- Uvicorn
- Pandas
- pdfplumber
- Anthropic Python SDK
- python-dotenv

The exact installed package versions should be maintained in `requirements.txt`.

## Installation 🛠️

Clone the repository:

```bash
git clone https://github.com/your-username/myWealthCom.git
cd myWealthCom
```

Create and activate a virtual environment:

```bash
python -m venv venv
```

Windows:

```powershell
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

If `requirements.txt` needs to be regenerated from the current virtual environment:

```powershell
pip freeze | ForEach-Object { ($_ -split '==')[0] } > requirements.txt
```

## Environment Variables 🔐

Create a `.env` file in the backend/project directory.

For example:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Do **not** commit `.env` or API keys to GitHub.

The application loads environment variables using `python-dotenv`.

## Running the Application 🏃‍♂️

From the backend directory:

```powershell
python bank_statement_dashboard.py
```

The FastAPI server runs at:

```text
http://127.0.0.1:8000
```

Open the dashboard in your browser.

## API Endpoints 📡

### `GET /`

Serves the dashboard HTML page.

### `GET /api/dashboard-data`

Returns the currently generated dashboard data used by the frontend.

### `POST /api/process-statement`

Processes an uploaded bank statement PDF.

The endpoint:

1. Receives the PDF.
2. Extracts its pages.
3. Sends page chunks to Claude for transaction extraction.
4. Combines and validates the extracted transactions.
5. Applies local classification rules.
6. Sends unresolved transactions to Claude for classification.
7. Normalizes the classification results.
8. Generates the dashboard data.
9. Returns the processed dashboard.

## Token Usage

The application prints usage for every Claude operation.

Example:

```text
============================================================
Claude operation : PDF extraction pages 1-2
Model            : claude-haiku-4-5-20251001
Input tokens     : 2,391
Output tokens    : 1,906
Cache write      : 0
Cache read       : 0
Total tokens     : 4,297
============================================================
```

At the end of processing, total usage is printed:

```text
============================================================
TOTAL CLAUDE USAGE
Input tokens     : ...
Output tokens    : ...
Cache write      : ...
Cache read       : ...
Total tokens     : ...
============================================================
```

Page chunking and local classification are used to avoid unnecessarily large Claude requests and reduce token consumption.

## Generated Files

`dashboard_data.json` is generated application data used by the dashboard.

It should normally **not be committed to Git** if it contains personal bank transaction information. Add it to `.gitignore`:

```gitignore
dashboard_data.json
```

Similarly, keep secrets and local environments out of Git:

```gitignore
.env
venv/
__pycache__/
*.pyc
```

## Important Security Note 🔒

Bank statements contain sensitive financial information.

Do not commit:

- Bank statement PDFs
- `.env`
- API keys
- Personal transaction data
- Generated `dashboard_data.json`

Use `.gitignore` to prevent accidental commits.

## Docker

If Docker configuration is present in the project, the application can be built and run with:

```bash
docker build -t wealthcomapi .
docker run -p 5000:5000 --env-file .env wealthcomapi
```

Make sure the container configuration and exposed port match the current FastAPI application configuration.

## Project Goal 💰

This project is intended to provide a more useful view of personal finances than a basic category-based spending report.

Instead of only showing:

```text
Food       ₹5,000
Investment ₹10,000
```

the dashboard aims to show:

```text
Where did the money go?

Friend       ₹7,000
Zerodha     ₹10,000
Amazon       ₹4,000
Rent        ₹25,000
```

while still retaining category-level information.

The goal is to make recurring relationships, destinations, transfers, investments, and actual spending easier to understand from a bank statement.

---

Made with ❤️ Siyal Patil
