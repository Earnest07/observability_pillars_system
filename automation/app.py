from fastapi import FastAPI, Request
import datetime
import json


app = FastAPI(
    title="Infrastructure Automation Controller"
)


@app.get("/")
def health():
    return {
        "status": "automation controller running"
    }


@app.post("/alert")
async def receive_alert(request: Request):

    payload = await request.json()

    timestamp = datetime.datetime.utcnow()

    print("=" * 60)
    print("ALERT RECEIVED")
    print("Time:", timestamp)
    print(json.dumps(payload, indent=4))
    print("=" * 60)

    return {
        "status": "received"
    }