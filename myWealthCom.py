import pdfplumber
from google import generativeai as genai
import pandas as pd
import json

# Set up Gemini
genai.configure(api_key="AIzaSyCs35IuDNP6xMBx1y5iJJxGEfBHq0V_wBk")
model = genai.GenerativeModel("gemini-1.5-flash")

# Load and extract text from your PDF
df = pd.read_csv("C:/Users/siyal/OneDrive/Desktop/holdings.csv")
# Convert the DataFrame to a string (so Gemini can read it)
csv_text = df.to_string(index=False)

response = model.generate_content(
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
clean=response.text.strip().removeprefix("```json").removesuffix("```").strip()
jsonres=json.loads(clean)
prettyPrint=json.dumps(jsonres,indent=2)
print(prettyPrint)