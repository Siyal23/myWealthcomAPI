import pdfplumber
from google import generativeai as genai
import pandas as pd
import json
import uuid
import os

# Set up Gemini
genai.configure(api_key="AIzaSyCs35IuDNP6xMBx1y5iJJxGEfBHq0V_wBk")
model = genai.GenerativeModel("gemini-1.5-flash")

# Configuration variables
UPLOAD_FOLDER = "uploads"
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

async def getFinanceData(csv_text):
    finRes = model.generate_content(
         f"""
        Your are financial advisor.I have a CSV file with transaction data, and I need to extract 
        specific names from the "Description". Please output each name found in the "Description" 
        as a separate with the tabular format providing name,credit,debit.
        Where name is the extracted name from the "Description" field.In case you cannot find what name
        should be extracted.give most possible name that can be found.
        Some example names to consider:
        1)by debit card-OTHPOS509413474245GOOGLE PLAY APP CYBS S2240920005-- = GOOGLE PLAY APP
        2)BY TRANSFER-NEFT*ICIC0000009*ICIN212026633934*Salary 2025APR M-- = Salary
        Important points:
        1)Do not omit any entry, even if the same name appears multiple times or with the same debit/credit values.
        2)Ensure each transaction is processed separately, even if the name appears in different rows.
        3)Treat each name, debit, and credit value as unique for each transaction and ensure that every occurrence of a name is processed as a distinct entry.
        4)If the name appears more than once in the same transaction, output that entry separately, with each entry considered unique based on its combination of name, debit, and credit.
        5)Make sure the correct name is extracted from each transaction. For example, "RAMNAYAN" should not be confused with "RUTUGAND" or any other name in the list.
        7)Do not provide any extra text only provide data not extra code.
        9)Do not provide column headers in response.
        {csv_text}
        """
    )
    return finRes

async def getStockData(csv_text):
    stockResponse = model.generate_content(
        f"""
        Extract stocks transaction details from the following CSV data only without any extra text or information.
        Provide data in JSON format also. 
        Keep the schema as below:
        "securityName": "string",
        "quantity": "float",
        "averageCostPrice": "float",       
        "lastTradedPrice": "float",
        "investedAmount": "float",      
        "currentStockPrice": "float",
        "PnL": "float",
        "net_change": "float",     
        "day_change": "float"       
        :\n\n{csv_text}
        """
    )
    return stockResponse

# Function to save uploaded file
async def save_file(file, file_path):
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

async def convertXlsToCsv(id, req):
    form_data = await req.form()
    file = form_data.get('file')

    # Ensure upload folder exists
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    # Save file to disk
    csvfilename = f"{str(id)}.csv"
    filepath = os.path.join(UPLOAD_FOLDER, csvfilename)
    await save_file(file, filepath)

    # Read and process CSV
    df = pd.read_csv(filepath, skiprows=20, engine="python", sep=None)
    df.to_csv(filepath, index=False)

async def getTransactionDetails(req):
    form_data = await req.form()
    type = form_data.get('type')
    uid = uuid.uuid4()

    # Handle file and conversion
    if form_data.get('file'):
        await convertXlsToCsv(uid, req)

    # Process data based on type
    if type == "stock":
        df = pd.read_csv(f"{UPLOAD_FOLDER}\\{str(uid)}.csv")
        csv_text = df.to_string(index=False)
        stock_response = await getStockData(csv_text)
        clean = stock_response.text.strip().removeprefix("```json").removesuffix("```").strip()
        jsonres = json.loads(clean)
        return jsonres

    else:
        df = pd.read_csv(f"{UPLOAD_FOLDER}\\{str(uid)}.csv")
        df1 = df.drop(columns=['Txn Date', 'Value Date', 'Ref No./Cheque No.', 'Balance'])
        chunk_size = 15
        chunks = [df1[i:i+chunk_size] for i in range(0, len(df1), chunk_size)]
        chunk_texts = [chunk.to_csv(index=False) for chunk in chunks]

        all_responses = []
        for chunk_text in chunk_texts:
            response = await getFinanceData(chunk_text)
            response_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
            print(response_text)
            all_responses.append(response_text)
        return all_responses
