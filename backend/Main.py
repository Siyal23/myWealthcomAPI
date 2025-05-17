from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from myWealthCom import getTransactionDetails

app = FastAPI()

@app.get("/")
def hello_world():
    return "Hello, World!"

@app.post("/transactions")
async def transactions(request: Request):
    # Call your original function with the request object
    res = await getTransactionDetails(request)
    
    # If the result is a dictionary or list, return a JSON response
    if isinstance(res, (dict, list)):
        return JSONResponse(content=res,status_code=200)
    else:
        # Otherwise, return the result directly
        return JSONResponse(content=res, status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
