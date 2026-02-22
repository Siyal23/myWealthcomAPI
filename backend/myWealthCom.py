import pdfplumber
import pandas as pd
import json
import uuid
import os
from fastapi.responses import FileResponse
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
claude_api_key = os.getenv("ANTHROPIC_API_KEY")
client = Anthropic (
    api_key=claude_api_key
)
model_name = os.getenv("MODEL_NAME")

# Configuration variables
UPLOAD_FOLDER = "uploads"
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

async def getFinanceData(csv_text,model_name):
    prompt = f"""          
        You are a financial data parser.

        Below is a CSV with multiple transaction rows. Each row contains a 'Description' field.

        Your task:
        - Extract **only one name per row** from the 'Description'.
        - Return one name per row, in the same order.
        - If no obvious name, return the most likely business/person involved.
        - Do NOT add headers, explanations, or extra text.
        - The number of lines in your output MUST equal the number of rows in the CSV.

        csv text:
        {csv_text}"""
    
    finRes = client.messages.create(
        model=f"{model_name}",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            }
        ],
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

async def getListOfNames(response)->list:
    final_names_list=[]
    lines = response.split("\n")
    for line in lines:
        name_part=line.split(",")
        final_names_list.append(name_part[0].strip())
    return final_names_list

async def getTransactionDetails(req):
    form_data = await req.form()
    type = form_data.get('type')
    uid = uuid.uuid4()

    # Handle file and conversion
    if form_data.get('file'):
        await convertXlsToCsv(uid, req)

    # Process data based on type
    if type == "stock":
        df = pd.read_csv(os.path.join(UPLOAD_FOLDER,f"{str(uid)}.csv"))
        csv_text = df.to_string(index=False)
        stock_response = await getStockData(csv_text)
        clean = stock_response.text.strip().removeprefix("```json").removesuffix("```").strip()
        jsonres = json.loads(clean)
        return jsonres

    else:
        df = pd.read_csv(os.path.join(UPLOAD_FOLDER,f"{str(uid)}.csv"))
        df = df[df['Description'].notna()]
        df = df[~df['Description'].astype(str).str.startswith('**')]
        df = df.reset_index(drop=True)
        df1 = df.drop(columns=['Txn Date', 'Value Date', 'Ref No./Cheque No.','        Debit','Credit', 'Balance'])
        names=[]
        csvtext=df1.to_csv(index=False)
        response = await getFinanceData(csvtext,model_name)
        response_text = response.content[0].text.strip().removeprefix("```json").removesuffix("```").strip()
        names.extend(await getListOfNames(response_text))
        df['names']=names
        output_path = os.path.join(UPLOAD_FOLDER, "output.csv")
        df.to_csv(output_path, index=False)
        return FileResponse(
            output_path,
            media_type="text/csv",
            filename="output.csv"
        )
