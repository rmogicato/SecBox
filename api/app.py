from flask import Flask
from flask_cors import CORS
from dataManager import handler
app = Flask(__name__)
CORS(app)


@app.route("/greeting")
def greeting():
    return {"greeting": "Backend is running"}


@app.route("/start")
def create():

    return {"processId": handler.start_process()}


@app.route("/getReports")
def get_reports():
    reports = handler.get_reports()
    return {"reports": reports}


if __name__ == '__main__':
    app.run()