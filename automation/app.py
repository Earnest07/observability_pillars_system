# from fastapi import FastAPI, Request, Response
# from twilio.rest import Client
# from twilio.twiml.voice_response import VoiceResponse, Gather
# import os
# import json
# import datetime

# app = FastAPI(title="Infrastructure Automation Controller")


# # ---------------------------------------------------------
# # Twilio client
# # ---------------------------------------------------------

# twilio_client = Client(
#     os.getenv("TWILIO_API_KEY_SID"),
#     os.getenv("TWILIO_API_KEY_SECRET"),
#     os.getenv("TWILIO_ACCOUNT_SID")
# )


# # ---------------------------------------------------------
# # Health check
# # ---------------------------------------------------------

# @app.get("/")
# def health():
#     return {
#         "status": "automation controller running"
#     }


# # ---------------------------------------------------------
# # Alertmanager webhook
# # ---------------------------------------------------------

# @app.post("/alert")
# async def receive_alert(request: Request):

#     payload = await request.json()

#     timestamp = datetime.datetime.utcnow()

#     print("=" * 60)
#     print("ALERT RECEIVED FROM ALERTMANAGER")
#     print("Time:", timestamp)
#     print(json.dumps(payload, indent=4))
#     print("=" * 60)

#     # Process only firing alerts.
#     firing_alerts = [
#         alert
#         for alert in payload.get("alerts", [])
#         if alert.get("status") == "firing"
#     ]

#     if not firing_alerts:
#         print("No firing alerts found.")
#         return {
#             "status": "received",
#             "action": "none"
#         }

#     # For this stage, initiate one call for the first firing alert.
#     alert = firing_alerts[0]

#     labels = alert.get("labels", {})

#     alert_name = labels.get(
#         "alertname",
#         "Infrastructure Alert"
#     )

#     service = labels.get(
#         "service",
#         "unknown service"
#     )

#     instance = labels.get(
#         "instance",
#         "unknown instance"
#     )

#     print("=" * 60)
#     print("STARTING INCIDENT CALL")
#     print("Alert:", alert_name)
#     print("Service:", service)
#     print("Instance:", instance)
#     print("=" * 60)

#     call = twilio_client.calls.create(
#         to=os.environ["ALERT_PHONE_NUMBER"],
#         from_=os.environ["TWILIO_PHONE_NUMBER"],
#         url="https://showy-placate-stardom.ngrok-free.dev/voice"
#     )

#     print("=" * 60)
#     print("TWILIO CALL INITIATED")
#     print("Call SID:", call.sid)
#     print("Status:", call.status)
#     print("=" * 60)

#     return {
#         "status": "received",
#         "action": "call initiated",
#         "alert": alert_name,
#         "service": service,
#         "instance": instance,
#         "call_sid": call.sid
#     }


# # ---------------------------------------------------------
# # Manual test call
# # ---------------------------------------------------------

# @app.post("/test-call")
# def test_call():

#     call = twilio_client.calls.create(
#         to=os.environ["ALERT_PHONE_NUMBER"],
#         from_=os.environ["TWILIO_PHONE_NUMBER"],
#         url="https://showy-placate-stardom.ngrok-free.dev/voice"
#     )

#     print("=" * 60)
#     print("TWILIO TEST CALL INITIATED")
#     print("Call SID:", call.sid)
#     print("Status:", call.status)
#     print("=" * 60)

#     return {
#         "status": "call initiated",
#         "call_sid": call.sid,
#         "twilio_status": call.status
#     }


# # ---------------------------------------------------------
# # Twilio voice webhook
# # ---------------------------------------------------------

# @app.post("/voice")
# async def voice():

#     response = VoiceResponse()

#     gather = Gather(
#         num_digits=1,
#         action="https://showy-placate-stardom.ngrok-free.dev/voice/ack",
#         method="POST",
#         timeout=10
#     )

#     gather.say(
#         "Critical infrastructure alert. "
#         "The application is currently down. "
#         "Press 1 to acknowledge this alert."
#     )

#     response.append(gather)

#     response.say(
#         "No acknowledgement received. Goodbye."
#     )

#     return Response(
#         content=str(response),
#         media_type="application/xml"
#     )


# # ---------------------------------------------------------
# # Twilio acknowledgement webhook
# # ---------------------------------------------------------

# @app.post("/voice/ack")
# async def voice_ack(request: Request):

#     form = await request.form()

#     digits = form.get("Digits")
#     call_sid = form.get("CallSid")

#     print("=" * 60)
#     print("VOICE ACKNOWLEDGEMENT RECEIVED")
#     print("Call SID:", call_sid)
#     print("Digits:", digits)
#     print("=" * 60)

#     response = VoiceResponse()

#     if digits == "1":

#         response.say(
#             "Acknowledgement received. "
#             "The incident has been acknowledged. Goodbye."
#         )

#         print("INCIDENT ACKNOWLEDGED")

#     else:

#         response.say(
#             "Invalid response. Goodbye."
#         )

#         print("INVALID ACKNOWLEDGEMENT")

#     return Response(
#         content=str(response),
#         media_type="application/xml"
#     )


from fastapi import FastAPI, Request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

import asyncio
import datetime
import json
import os

from aws_scaler import scale_out, scale_in


app = FastAPI(title="Infrastructure Automation Controller")


# =========================================================
# Twilio client
# =========================================================

twilio_client = Client(
    os.getenv("TWILIO_API_KEY_SID"),
    os.getenv("TWILIO_API_KEY_SECRET"),
    os.getenv("TWILIO_ACCOUNT_SID")
)


# =========================================================
# Incident configuration
# =========================================================

MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 30


# =========================================================
# In-memory incident state
#
# Key:
#     Alertmanager fingerprint
#
# Value:
#     Incident information
# =========================================================

incidents = {}


# =========================================================
# Helper: current UTC timestamp
# =========================================================

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# =========================================================
# Helper: initiate Twilio call
# =========================================================

def initiate_call(incident):

    call = twilio_client.calls.create(
        to=os.environ["ALERT_PHONE_NUMBER"],
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url="https://showy-placate-stardom.ngrok-free.dev/voice"
    )

    incident["attempt"] += 1
    incident["call_sid"] = call.sid
    incident["last_call_status"] = call.status
    incident["last_call_time"] = utc_now()

    print("=" * 60)
    print("TWILIO INCIDENT CALL INITIATED")
    print("Fingerprint:", incident["fingerprint"])
    print("Attempt:", f'{incident["attempt"]}/{MAX_ATTEMPTS}')
    print("Call SID:", call.sid)
    print("Status:", call.status)
    print("=" * 60)

    return call


# =========================================================
# Retry worker
# =========================================================

async def retry_incident(fingerprint):

    incident = incidents.get(fingerprint)

    if not incident:
        print("Incident no longer exists:", fingerprint)
        return

    while True:

        # -------------------------------------------------
        # Stop if incident was acknowledged
        # -------------------------------------------------

        if incident["status"] == "acknowledged":
            print(
                "Retry worker stopped - incident acknowledged:",
                fingerprint
            )
            return

        # -------------------------------------------------
        # Stop if incident was resolved
        # -------------------------------------------------

        if incident["status"] == "resolved":
            print(
                "Retry worker stopped - incident resolved:",
                fingerprint
            )
            return

        # -------------------------------------------------
        # Stop after maximum attempts
        # -------------------------------------------------

        if incident["attempt"] >= MAX_ATTEMPTS:

            incident["status"] = "scale_out_required"

            print("=" * 60)
            print("MAXIMUM CALL ATTEMPTS REACHED")
            print("Fingerprint:", fingerprint)
            print("Attempts:", incident["attempt"])
            print("STATUS: SCALE OUT REQUIRED")
            print("=" * 60)

            # -------------------------------------------------
            # Terraform integration will be added here.
            # -------------------------------------------------

            scale_out()

            return

        # -------------------------------------------------
        # Wait before the next call
        # -------------------------------------------------

        print("=" * 60)
        print("WAITING BEFORE NEXT CALL")
        print("Fingerprint:", fingerprint)
        print(
            "Next attempt:",
            f'{incident["attempt"] + 1}/{MAX_ATTEMPTS}'
        )
        print(
            "Delay:",
            f"{RETRY_DELAY_SECONDS} seconds"
        )
        print("=" * 60)

        await asyncio.sleep(RETRY_DELAY_SECONDS)

        # -------------------------------------------------
        # Check again after waiting
        # -------------------------------------------------

        if incident["status"] in (
            "acknowledged",
            "resolved"
        ):
            return

        # -------------------------------------------------
        # Start next call
        # -------------------------------------------------

        initiate_call(incident)


# =========================================================
# Health check
# =========================================================

@app.get("/")
def health():

    return {
        "status": "automation controller running"
    }


# =========================================================
# Alertmanager webhook
# =========================================================

@app.post("/alert")
async def receive_alert(request: Request):

    payload = await request.json()

    print("=" * 60)
    print("ALERT RECEIVED FROM ALERTMANAGER")
    print("Time:", utc_now())
    print(json.dumps(payload, indent=4))
    print("=" * 60)

    # -----------------------------------------------------
    # Process firing alerts
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Process each firing alert
    # -----------------------------------------------------

    for alert in firing_alerts:

        fingerprint = alert.get("fingerprint")

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

        # -------------------------------------------------
        # Fingerprint is required
        # -------------------------------------------------

        if not fingerprint:

            print(
                "WARNING: Alert has no fingerprint."
            )

            continue

        # -------------------------------------------------
        # Existing incident
        # -------------------------------------------------

        if fingerprint in incidents:

            incident = incidents[fingerprint]

            print("=" * 60)
            print("EXISTING INCIDENT RECEIVED")
            print("Fingerprint:", fingerprint)
            print("Status:", incident["status"])
            print(
                "Attempt:",
                f'{incident["attempt"]}/{MAX_ATTEMPTS}'
            )
            print(
                "Ignoring duplicate Alertmanager notification."
            )
            print("=" * 60)

            continue

        # -------------------------------------------------
        # Create new incident
        # -------------------------------------------------

        incident = {
            "fingerprint": fingerprint,
            "alertname": alert_name,
            "service": service,
            "instance": instance,
            "status": "calling",
            "attempt": 0,
            "call_sid": None,
            "last_call_status": None,
            "last_call_time": None,
            "created_at": utc_now()
        }

        incidents[fingerprint] = incident

        print("=" * 60)
        print("NEW INCIDENT CREATED")
        print("Fingerprint:", fingerprint)
        print("Alert:", alert_name)
        print("Service:", service)
        print("Instance:", instance)
        print("=" * 60)

        # -------------------------------------------------
        # Initial call
        # -------------------------------------------------

        initiate_call(incident)

        # -------------------------------------------------
        # Start asynchronous retry worker
        # -------------------------------------------------

        asyncio.create_task(
            retry_incident(fingerprint)
        )

    return {
        "status": "received",
        "action": "incident processed"
    }


# =========================================================
# Manual test call
# =========================================================

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


# =========================================================
# Twilio voice webhook
# =========================================================

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


# =========================================================
# Twilio acknowledgement webhook
# =========================================================

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

    # -----------------------------------------------------
    # Find incident associated with this call
    # -----------------------------------------------------

    incident = None

    for current_incident in incidents.values():

        if current_incident["call_sid"] == call_sid:

            incident = current_incident
            break

    # -----------------------------------------------------
    # Acknowledgement
    # -----------------------------------------------------

    if digits == "1":

        response.say(
            "Acknowledgement received. "
            "The incident has been acknowledged. Goodbye."
        )

        if incident:

            incident["status"] = "acknowledged"
            incident["acknowledged_at"] = utc_now()

            print("=" * 60)
            print("INCIDENT ACKNOWLEDGED")
            print(
                "Fingerprint:",
                incident["fingerprint"]
            )
            print(
                "Attempt:",
                f'{incident["attempt"]}/{MAX_ATTEMPTS}'
            )
            print("=" * 60)

        else:

            print(
                "WARNING: Could not match Call SID "
                "to an active incident."
            )

    # -----------------------------------------------------
    # Invalid response
    # -----------------------------------------------------

    else:

        response.say(
            "Invalid response. Goodbye."
        )

        print("INVALID ACKNOWLEDGEMENT")

    return Response(
        content=str(response),
        media_type="application/xml"
    )

