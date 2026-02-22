# myWealthCom API 🚀

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.75.0-green)](https://fastapi.tiangolo.com/)

This is a **FastAPI-based** application designed to process **financial transaction data** and **extract relevant information** using AI models. It can handle both general transactions and stock data.

## Features 🌟

- **File Upload**: Upload XLSX files containing transaction data.
- **AI Data Extraction**: Use Gemini AI models to extract useful information from the transaction descriptions.
- **Flexible Output**: Returns processed data in JSON format for easy integration.

## Requirements 📋

- Python 3.8+
- FastAPI
- Pandas
- Gemini AI API
- Uvicorn (for running the server)

## Installation 🛠️

Clone the repository:

```bash
git clone https://github.com/your-username/myWealthCom.git
cd myWealthCom

python -m venv venv
source venv/bin/activate  # For Linux/macOS
venv\Scripts\activate  # For Windows

pip freeze | ForEach-Object { ($_ -split '==')[0] } > requirements.txt 
pip install -r requirements.txt


Running the Application 🏃‍♂️

To start the FastAPI application, run:

python Main.py

API Endpoints 📡
GET / 🌐

Check if the API is running.

Response:

{
  "message": "Hello, World!"
}

POST /transactions 💼

This endpoint processes transaction data by extracting relevant details from an uploaded CSV file.
Request

    Content-Type: multipart/form-data

    Body:

        file: The XLSX file containing transaction data.

        type: The type of data ("finance" or "stock").

Example cURL Request:

curl -X 'POST' \
  'http://127.0.0.1:8000/transactions' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@path_to_your_file.xlsx' \
  -F 'type=finance'

Response

{
  "status": "success",
  "data": [
    {
      "name": "GOOGLE PLAY APP",
      "credit": 50.00,
      "debit": 0.00
    },
    {
      "name": "Salary",
      "credit": 0.00,
      "debit": 1000.00
    }
  ]
}

docker build -t mywealthcom .
docker run -p 3000:3000 mywealthcom

Made with ❤️ Siyal Patil

