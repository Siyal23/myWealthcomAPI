from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from myWealthCom import getTransactionDetails
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # frontend origin
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def hello_world():
    return "Hello, World!"

@app.post("/transactions")
async def transactions(request: Request):
    return await getTransactionDetails(request) 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
