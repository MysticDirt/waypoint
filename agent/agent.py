import os
import json
import asyncio
import threading
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---- uAgents client that talks to your Hosted Agent (Agentverse) ----
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low  # ← keep funding helper
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from dotenv import load_dotenv
load_dotenv()

# ---------------- FastAPI app & CORS ----------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Pydantic models ----------------
class UserGoalRequest(BaseModel):
    prompt: str

class ItineraryItem(BaseModel):
    id: str
    title: str
    description: str
    startTime: str
    type: str

class Location(BaseModel):
    name: str
    latitude: float
    longitude: float
    linkedItineraryId: str

class AgentPlanResponse(BaseModel):
    status: str
    itinerary: List[ItineraryItem]
    logs: List[str]
    locations: List[Location]

# ---------------- Config ----------------
TARGET_AGENT_ADDRESS = os.getenv("TARGET_AGENT_ADDRESS", "").strip()  # Hosted Agent address (Agentverse)
MAILBOX_EMAIL = os.getenv("MAILBOX_EMAIL", "").strip()                # optional (no longer needed for API)
CLIENT_SEED = os.getenv("CLIENT_AGENT_SEED", "backend_client_seed_123")

if not TARGET_AGENT_ADDRESS:
    print("WARNING: TARGET_AGENT_ADDRESS is not set. Backend will use mock fallback.")

# ---------------- Agentverse Bridge (client agent) ----------------
class AgentverseBridge:
    """
    Minimal client uAgent that sends Chat messages to your Hosted Agent (Agentverse)
    and awaits a single reply. We serialize requests with a lock to keep it simple.
    """
    def __init__(self, target_address: str):
        self.target_address = target_address

        # ✅ mailbox=True is all you need with current uAgents
        self._agent = Agent(name="BackendClient", seed=CLIENT_SEED, mailbox=True)

        self._protocol = Protocol(spec=chat_protocol_spec)
        self._lock = asyncio.Lock()
        self._loop = asyncio.new_event_loop()
        self._thread: Optional[threading.Thread] = None
        self._pending_future: Optional[asyncio.Future] = None

        @self._protocol.on_message(ChatMessage)
        async def on_msg(ctx: Context, sender: str, msg: ChatMessage):
            if sender != self.target_address:
                return
            text = msg.text() or ""
            fut = self._pending_future
            if fut and not fut.done():
                fut.set_result(text)

        @self._protocol.on_message(ChatAcknowledgement)
        async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
            pass

        self._agent.include(self._protocol, publish_manifest=False)

        # Optional faucet; safe to keep
        try:
            fund_agent_if_low(self._agent.wallet.address())
        except Exception:
            pass

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._agent.run()
        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

    async def send_and_wait(self, message_text: str, timeout: float = 25.0) -> str:
        if not self.target_address:
            raise RuntimeError("TARGET_AGENT_ADDRESS not configured.")
        async with self._lock:
            self.start()

            def _mk_future():
                return asyncio.run_coroutine_threadsafe(self._make_future(), self._loop).result()
            self._pending_future = _mk_future()

            start_session = ChatMessage(
                timestamp=datetime.utcnow(),
                msg_id=os.urandom(8).hex(),
                content=[StartSessionContent(type="start-session")]
            )
            user_msg = ChatMessage(
                timestamp=datetime.utcnow(),
                msg_id=os.urandom(8).hex(),
                content=[TextContent(type="text", text=message_text),
                         EndSessionContent(type="end-session")]
            )

            def _send():
                async def _do_send():
                    await self._agent._context.send(self.target_address, start_session)
                    await self._agent._context.send(self.target_address, user_msg)
                return asyncio.run_coroutine_threadsafe(_do_send(), self._loop).result()
            _send()

            try:
                result = await asyncio.wait_for(self._pending_future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                raise TimeoutError("Timed out waiting for hosted agent response.")
            finally:
                self._pending_future = None

    async def _make_future(self):
        return asyncio.get_running_loop().create_future()

# Create a global bridge
bridge = AgentverseBridge(TARGET_AGENT_ADDRESS)

# ---------------- Mock fallback (unchanged) ----------------
def call_llm_api(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    if "Respond ONLY with a JSON list of steps" in system_prompt:
        return [
            {"tool_name": "search_hotels", "parameters": {"location": "Chicago", "checkin": "2025-11-01", "checkout": "2025-11-03"}},
            {"tool_name": "search_events", "parameters": {"location": "Chicago", "date": "2025-11-01"}},
            {"tool_name": "search_flights", "parameters": {"from": "SFO", "to": "ORD", "date": "2025-11-01"}}
        ]
    elif "Synthesize it into an itinerary" in system_prompt:
        base_time = datetime.now() + timedelta(days=7)
        return {
            "itinerary": [
                {"id": "item_1", "title": "Flight to Chicago", "description": "Depart SFO→ORD", "startTime": (base_time+timedelta(hours=8)).isoformat(), "type": "travel"},
                {"id": "item_2", "title": "Check-in at Budget Inn Chicago", "description": "Affordable downtown", "startTime": (base_time+timedelta(hours=14)).isoformat(), "type": "lodging"},
                {"id": "item_3", "title": "Art Institute of Chicago", "description": "Free weekend admission", "startTime": (base_time+timedelta(days=1, hours=10)).isoformat(), "type": "activity"},
                {"id": "item_4", "title": "Chicago Cultural Center", "description": "Free exhibitions", "startTime": (base_time+timedelta(days=1, hours=14)).isoformat(), "type": "activity"},
                {"id": "item_5", "title": "Millennium Park Concert", "description": "Free outdoor concert", "startTime": (base_time+timedelta(days=1, hours=18)).isoformat(), "type": "activity"},
            ],
            "locations": [
                {"name": "O'Hare International Airport", "latitude": 41.9742, "longitude": -87.9073, "linkedItineraryId": "item_1"},
                {"name": "Budget Inn Chicago", "latitude": 41.8781, "longitude": -87.6298, "linkedItineraryId": "item_2"},
                {"name": "Art Institute of Chicago", "latitude": 41.8796, "longitude": -87.6237, "linkedItineraryId": "item_3"},
                {"name": "Chicago Cultural Center", "latitude": 41.8837, "longitude": -87.6249, "linkedItineraryId": "item_4"},
                {"name": "Millennium Park", "latitude": 41.8826, "longitude": -87.6234, "linkedItineraryId": "item_5"},
            ]
        }
    elif "Accept the changes" in system_prompt:
        m = re.search(r'\{.*\}', user_prompt, re.DOTALL)
        if m:
            data = json.loads(m.group())
            ids = {i["id"] for i in data.get("itinerary", [])}
            locs = [l for l in data.get("locations", []) if l.get("linkedItineraryId") in ids]
            return {"itinerary": data.get("itinerary", []), "locations": locs}
        return {"itinerary": [], "locations": []}
    return {}

def mock_search_flights(from_city: str = "SFO", to_city: str = "ORD", date: str = "") -> Dict[str, Any]:
    return {"flights":[
        {"airline":"United","flight_number":"UA123","departure":from_city,"arrival":to_city,"price":250,"departure_time":"08:00","arrival_time":"14:00"},
        {"airline":"Southwest","flight_number":"SW456","departure":from_city,"arrival":to_city,"price":180,"departure_time":"10:30","arrival_time":"16:30"},
    ]}

def mock_search_hotels(location: str = "Chicago", checkin: str = "", checkout: str = "") -> Dict[str, Any]:
    return {"hotels":[
        {"name":"Budget Inn Chicago","address":"123 Downtown St","price_per_night":75,"rating":4.2,"latitude":41.8781,"longitude":-87.6298},
        {"name":"Chicago Hostel","address":"456 Loop Ave","price_per_night":35,"rating":4.5,"latitude":41.8850,"longitude":-87.6300},
    ]}

def mock_search_events(location: str = "Chicago", date: str = "") -> Dict[str, Any]:
    return {"events":[
        {"name":"Art Institute of Chicago","type":"museum","price":0,"description":"Free weekends","latitude":41.8796,"longitude":-87.6237},
        {"name":"Chicago Cultural Center","type":"cultural","price":0,"description":"Free exhibitions","latitude":41.8837,"longitude":-87.6249},
        {"name":"Millennium Park Concert","type":"concert","price":0,"description":"Free outdoor concert","latitude":41.8826,"longitude":-87.6234},
    ]}

# ---------------- Utils ----------------
def _parse_agent_json(text: str) -> Dict[str, Any]:
    m = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}

# ---------------- FastAPI lifecycle ----------------
@app.on_event("startup")
async def _startup():
    bridge.start()

# ---------------- HTTP Endpoints ----------------
@app.post("/plan", response_model=AgentPlanResponse)
async def plan(request: UserGoalRequest):
    logs: List[str] = []
    goal = request.prompt.strip()

    if TARGET_AGENT_ADDRESS:
        try:
            reply_text = await bridge.send_and_wait(f"PLAN: {goal}", timeout=25.0)
            data = _parse_agent_json(reply_text)
            if isinstance(data, dict) and "itinerary" in data and "locations" in data:
                logs.append("Hosted agent planning completed")
                return AgentPlanResponse(
                    status="success",
                    itinerary=data.get("itinerary", []),
                    logs=logs,
                    locations=data.get("locations", [])
                )
            logs.append("Hosted agent returned unexpected structure; using mock fallback")
        except Exception as e:
            logs.append(f"Hosted agent error: {e}; using mock fallback")

    # mock fallback
    context = {
        "hotel_data": mock_search_hotels(),
        "event_data": mock_search_events(),
        "flight_data": mock_search_flights(),
    }
    final_plan = call_llm_api(
        "Synthesize it into an itinerary.",
        f"Original Goal: {goal}\n\nCollected Data:\n{json.dumps(context)}"
    )
    logs.append("Mock planning completed")
    return AgentPlanResponse(
        status="success",
        itinerary=final_plan.get("itinerary", []),
        logs=logs,
        locations=final_plan.get("locations", [])
    )

@app.post("/refine", response_model=AgentPlanResponse)
async def refine(request: Dict[str, Any]):
    logs: List[str] = []
    payload = json.dumps(request)

    if TARGET_AGENT_ADDRESS:
        try:
            reply_text = await bridge.send_and_wait(f"REFINE: {payload}", timeout=25.0)
            data = _parse_agent_json(reply_text)
            if isinstance(data, dict) and "itinerary" in data and "locations" in data:
                logs.append("Hosted agent refinement completed")
                return AgentPlanResponse(
                    status="success",
                    itinerary=data.get("itinerary", []),
                    logs=logs,
                    locations=data.get("locations", [])
                )
            logs.append("Hosted agent returned unexpected structure; using mock fallback")
        except Exception as e:
            logs.append(f"Hosted agent error: {e}; using mock fallback")

    # mock fallback
    refined = call_llm_api(
        "Accept the changes and ensure consistency.",
        f"Here is the user's modified plan:\n{payload}"
    )
    itinerary = request.get("itinerary", []) if refined.get("itinerary") == [] else refined.get("itinerary", request.get("itinerary", []))
    ids = {i["id"] for i in itinerary}
    locations = [l for l in request.get("locations", []) if l.get("linkedItineraryId") in ids]
    logs.append("Mock refinement completed")
    return AgentPlanResponse(status="success", itinerary=itinerary, logs=logs, locations=locations)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "agent", "target_agent": bool(TARGET_AGENT_ADDRESS)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
