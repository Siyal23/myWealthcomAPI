import pdfplumber
from google import generativeai as genai
import pandas as pd
import json
import uuid
import os


# Set up Gemini
genai.configure(api_key="AIzaSyCs35IuDNP6xMBx1y5iJJxGEfBHq0V_wBk")
model = genai.GenerativeModel("gemini-1.5-flash")

def getFinanceData(csv_text):
        finRes = model.generate_content(
        f"""
        Extract finance transaction details and provide column details in json format 
        :\n\n{csv_text}
    
        """
    )
        return finRes
     
def getStockData(csv_text):
        stockResponse = model.generate_content(
        f"""
        Extract stocks transaction details from the following CSV data only without any extra text or information
        just provide data in JSON format also 
        keep the schema as below
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
        
def convertXlsToCsv(id,req,app):
    file = req.files['file']
    UPLOAD_FOLDER="uploads"
    app.config['UPLOAD_FOLDER']=UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH']=16 * 1024 * 1024
    
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    csvfilename=str(id)+".csv"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'],csvfilename)
    file.save(filepath)
    df=pd.read_csv(filepath,skiprows=20,engine="python",sep=None)
    df.to_csv("uploads\\"+csvfilename,index=False)
def getTransactionDetails(req,app):
    type = req.form['type']
    uid=uuid.uuid4()
    if req.files:
        convertXlsToCsv(uid,req,app)
    if type=="stock":
         df = pd.read_csv(f"uploads\\{str(uid)}.csv")
         # Convert the DataFrame to a string (so Gemini can read it)
         csv_text = df.to_string(index=False)
         clean=getStockData(csv_text).text.strip().removeprefix("```json").removesuffix("```").strip()
         jsonres=json.loads(clean)
         return jsonres
        #  prettyPrint=json.dumps(jsonres,indent=2)
        #  return prettyPrint
    else:
         df = pd.read_csv(f"uploads\\{str(uid)}.csv")
         # Convert the DataFrame to a string (so Gemini can read it)
         csv_text = df.to_string(index=False)
         clean=getFinanceData(csv_text).text.strip().removeprefix("```json").removesuffix("```").strip()
         print(clean)
         jsonres=json.loads(clean)
         prettyPrint=json.dumps(getFinanceData(csv_text).text,indent=2)
         return prettyPrint