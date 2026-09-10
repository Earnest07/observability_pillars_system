from fastapi import FastAPI, Request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
import json
import datetime

app = FastAPI(title="Infrastructure Automation Controller")


# ---------------------------------------------------------
# Twilio client
# ---------------------------------------------------------

twilio_client = Client(
    os.getenv("TWILIO_API_KEY_SID"),
    os.getenv("TWILIO_API_KEY_SECRET"),
    os.getenv("TWILIO_ACCOUNT_SID")
)


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@app.get("/")
def health():
    return {
        "status": "automation controller running"
    }


# ---------------------------------------------------------
# Alertmanager webhook
# ---------------------------------------------------------

@app.post("/alert")
async def receive_alert(request: Request):

    payload = await request.json()

    timestamp = datetime.datetime.utcnow()

    print("=" * 60)
    print("ALERT RECEIVED FROM ALERTMANAGER")
    print("Time:", timestamp)
    print(json.dumps(payload, indent=4))
    print("=" * 60)

    # Process only firing alerts.
    firing_alerts = [
        alert
        for alert in payload.get("alerts", [])
        if alert.get("status") == "firing"
    ]

    if not firing_alerts:
        print("No firing alerts found.")
        return {
            "status": "received",
            "action": "none"
        }

    # For this stage, initiate one call for the first firing alert.
    alert = firing_alerts[0]

    labels = alert.get("labels", {})

    alert_name = labels.get(
        "alertname",
        "Infrastructure Alert"
    )

    service = labels.get(
        "service",
        "unknown service"
    )

    instance = labels.get(
        "instance",
        "unknown instance"
    )

    print("=" * 60)
    print("STARTING INCIDENT CALL")
    print("Alert:", alert_name)
    print("Service:", service)
    print("Instance:", instance)
    print("=" * 60)

    call = twilio_client.calls.create(
        to=os.environ["ALERT_PHONE_NUMBER"],
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url="https://showy-placate-stardom.ngrok-free.dev/voice"
    )

    print("=" * 60)
    print("TWILIO CALL INITIATED")
    print("Call SID:", call.sid)
    print("Status:", call.status)
    print("=" * 60)

    return {
        "status": "received",
        "action": "call initiated",
        "alert": alert_name,
        "service": service,
        "instance": instance,
        "call_sid": call.sid
    }


# ---------------------------------------------------------
# Manual test call
# ---------------------------------------------------------

@app.post("/test-call")
def test_call():

    call = twilio_client.calls.create(
        to=os.environ["ALERT_PHONE_NUMBER"],
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url="https://showy-placate-stardom.ngrok-free.dev/voice"
    )

    print("=" * 60)
    print("TWILIO TEST CALL INITIATED")
    print("Call SID:", call.sid)
    print("Status:", call.status)
    print("=" * 60)

    return {
        "status": "call initiated",
        "call_sid": call.sid,
        "twilio_status": call.status
    }


# ---------------------------------------------------------
# Twilio voice webhook
# ---------------------------------------------------------

@app.post("/voice")
async def voice():

    response = VoiceResponse()

    gather = Gather(
        num_digits=1,
        action="https://showy-placate-stardom.ngrok-free.dev/voice/ack",
        method="POST",
        timeout=10
    )

    gather.say(
        "Critical infrastructure alert. "
        "The application is currently down. "
        "Press 1 to acknowledge this alert."
    )

    response.append(gather)

    response.say(
        "No acknowledgement received. Goodbye."
    )

    return Response(
        content=str(response),
        media_type="application/xml"
    )


# ---------------------------------------------------------
# Twilio acknowledgement webhook
# ---------------------------------------------------------

@app.post("/voice/ack")
async def voice_ack(request: Request):

    form = await request.form()

    digits = form.get("Digits")
    call_sid = form.get("CallSid")

    print("=" * 60)
    print("VOICE ACKNOWLEDGEMENT RECEIVED")
    print("Call SID:", call_sid)
    print("Digits:", digits)
    print("=" * 60)

    response = VoiceResponse()

    if digits == "1":

        response.say(
            "Acknowledgement received. "
            "The incident has been acknowledged. Goodbye."
        )

        print("INCIDENT ACKNOWLEDGED")

    else:

        response.say(
            "Invalid response. Goodbye."
        )

        print("INVALID ACKNOWLEDGEMENT")

    return Response(
        content=str(response),
        media_type="application/xml"
    )
