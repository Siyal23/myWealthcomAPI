from flask import Flask,request,Response
from myWealthCom import getTransactionDetails
import jsonify

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "Hello, World!"

@app.route("/transactions", methods=['POST'])
def transactions():
    # getTransactionDetails(request,app)

    res=getTransactionDetails(request,app)
    response = Response(
        response=res,
        status=200,
        mimetype='application/json'
    )
    return response
    

if __name__ == "__main__":
    app.run(port=3000)