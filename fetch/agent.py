# hosted_planner_agent.py
# Hosted on Agentverse: a uAgents agent that handles planning and refinement
# via the standard Chat protocol. It calls Claude (Anthropic) when the API key
# is present, otherwise falls back to mock behavior.

from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any, Dict, List
import os, json, re

# NEW: async helpers for non-blocking Anthropic calls
import asyncio
from functools import partial

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from openai import OpenAI


##
### Example Expert Assistant
##
## This chat example is a barebones example of how you can create a simple chat agent
## and connect to agentverse. In this example we will be prompting the ASI-1 model to
## answer questions on a specific subject only.
##

def create_text_chat(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.utcnow(), msg_id=uuid4(), content=content)

# the subject that this assistant is an expert in
subject_matter = "travel"

AS1_KEY = os.getenv("AS1_KEY", "").strip()
# print(AS1_KEY)
client = OpenAI(
    # By default, we are using the ASI-1 LLM endpoint and model
    base_url='https://api.asi1.ai/v1',

    # You can get an ASI-1 api key by creating an account at https://asi1.ai/dashboard/api-keys
    api_key=AS1_KEY,
)

import asyncio, json
from functools import partial
from typing import Any, Dict, List

def _safe_extract_json(text: str) -> Dict[str, Any]:
    """
    Try to parse a JSON object from the model's response.
    If it isn't valid JSON, return an empty dict so caller can fallback.
    """
    if not isinstance(text, str):
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # Very defensive: try to find a top-level {...} or [...]
        import re
        m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}

async def asi_execute_steps(goal: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Uses ASI-1 to perform the 'execution' phase of your trip planner:
      - search_hotels(location, checkin, checkout)
      - search_events(location, date)
      - search_flights(from, to, date)

    Returns STRICT structured JSON:
      {
        "hotel_data":  { "hotels":  [ { name, address, price_per_night, rating, latitude, longitude } ... ] },
        "event_data":  { "events":  [ { name, type, price, description, latitude, longitude } ... ] },
        "flight_data": { "flights": [ { airline, flight_number, departure, arrival, price, departure_time, arrival_time } ... ] }
      }

    On error or non-JSON responses, returns {} so the caller can fallback to mocks.
    """
    # System prompt: force schema + JSON-only output
    system_prompt = (
        "You are a data-gathering travel agent that can use web search and agent tools.\n"
        "Execute the given steps (search_hotels, search_events, search_flights) and return ONLY JSON with keys:\n"
        "  hotel_data, event_data, flight_data.\n"
        "SCHEMAS (arrays may be empty, but keys must exist):\n"
        "- hotel_data.hotels[]: { name, address, price_per_night, rating, latitude, longitude }\n"
        "- event_data.events[]: { name, type, price, description, latitude, longitude }\n"
        "- flight_data.flights[]: { airline, flight_number, departure, arrival, price, departure_time, arrival_time }\n"
        "No prose, no markdown, no explanations—return only a single JSON object."
    )

    user_payload = {
        "goal": goal,
        "steps": steps,
    }

    # Prepare a sync call to run off the event loop.
    def _call():
        return client.chat.completions.create(
            model="asi1-mini",  # or "asi1" if you have access and want the larger model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            max_tokens=2500,
            temperature=0.1,
        )

    try:
        # Run the blocking HTTP in a worker thread; add a hard timeout
        resp = await asyncio.wait_for(asyncio.to_thread(_call), timeout=25.0)
        raw = resp.choices[0].message.content if resp and resp.choices else ""
        data = _safe_extract_json(raw)

        # Normalize shape (guarantee top-level keys and arrays exist)
        if isinstance(data, dict):
            hotel_data  = data.get("hotel_data")  or {}
            event_data  = data.get("event_data")  or {}
            flight_data = data.get("flight_data") or {}
            hotel_data.setdefault("hotels", [])
            event_data.setdefault("events", [])
            flight_data.setdefault("flights", [])

            return {
                "hotel_data": hotel_data,
                "event_data": event_data,
                "flight_data": flight_data,
            }
        return {}
    except Exception:
        return {}

agent = Agent()

# We create a new protocol which is compatible with the chat protocol spec. This ensures
# compatibility between agents
protocol = Protocol(spec=chat_protocol_spec)

# --- Config flags (mock override) ---
FORCE_MOCK = os.getenv("FORCE_MOCK", "").strip().lower() in {"1", "true", "yes"}
print(FORCE_MOCK)
# --- Claude client (optional if key present) ---
USE_MOCK = FORCE_MOCK
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

anthropic_client = None
APIStatusError = Exception  # placeholder to avoid NameError in except paths

if not USE_MOCK:
    print("something")
    try:
        from anthropic import Anthropic, APIStatusError as _AnthropicAPIStatusError  # type: ignore
        APIStatusError = _AnthropicAPIStatusError
        if ANTHROPIC_API_KEY:
            anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
        else:
            USE_MOCK = True
    except Exception:
        print(Exception)
        anthropic_client = None
        USE_MOCK = True
print(USE_MOCK)
# ---------- Helpers ----------
def _create_text_msg(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.utcnow(), msg_id=uuid4(), content=content)

def _extract_json(text: str) -> Any:
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}

# NEW: Non-blocking Anthropic call with timeout
async def _ask_claude_for_json_async(system_prompt: str, user_prompt: str) -> Any:
    """
    Non-blocking wrapper around Anthropic's sync client.
    Runs the network call in a worker thread with a hard timeout.
    Returns {} on any failure so the pipeline can fall back to mock.
    """
    # print("FINAL MOCK", USE_MOCK)
    if USE_MOCK or anthropic_client is None:
        return {}
    # print("another thing")
    call = partial(
        anthropic_client.messages.create,
        model="claude-3-5-sonnet-latest",
        max_tokens=2000,
        temperature=0.1,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    try:
        # Adjust timeout to your UX/SLA needs
        msg = await asyncio.wait_for(asyncio.to_thread(call), timeout=12.0)
        text = "".join(getattr(b, "text", "") for b in msg.content)
        return _extract_json(text) or {}
    except (APIStatusError, asyncio.TimeoutError):
        return {}
    except Exception:
        return {}

# ---------- Mock tool functions (kept for demo + no-key mode) ----------
def mock_search_flights(from_city: str = "SFO", to_city: str = "ORD", date: str = "") -> Dict[str, Any]:
    return {
        "flights": [
            {"airline": "United", "flight_number": "UA123", "departure": from_city, "arrival": to_city,
             "price": 250, "departure_time": "08:00", "arrival_time": "14:00"},
            {"airline": "Southwest", "flight_number": "SW456", "departure": from_city, "arrival": to_city,
             "price": 180, "departure_time": "10:30", "arrival_time": "16:30"},
        ]
    }

def mock_search_hotels(location: str = "Chicago", checkin: str = "", checkout: str = "") -> Dict[str, Any]:
    return {
        "hotels": [
            {"name": "Budget Inn Chicago", "address": "123 Downtown St", "price_per_night": 75, "rating": 4.2,
             "latitude": 41.8781, "longitude": -87.6298},
            {"name": "Chicago Hostel", "address": "456 Loop Ave", "price_per_night": 35, "rating": 4.5,
             "latitude": 41.8850, "longitude": -87.6300},
        ]
    }

def mock_search_events(location: str = "Chicago", date: str = "") -> Dict[str, Any]:
    return {
        "events": [
            {"name": "Art Institute of Chicago", "type": "museum", "price": 0, "description": "Free admission on weekends",
             "latitude": 41.8796, "longitude": -87.6237},
            {"name": "Chicago Cultural Center", "type": "cultural", "price": 0, "description": "Free exhibitions and performances",
             "latitude": 41.8837, "longitude": -87.6249},
            {"name": "Millennium Park Concert", "type": "concert", "price": 0, "description": "Free outdoor concert",
             "latitude": 41.8826, "longitude": -87.6234},
        ]
    }

# ---------- Planning pipeline (works with Claude or mock) ----------
DECOMPOSE_SYS = (
    "You are an expert planner. Break down the user's goal into actionable steps. "
    "Respond ONLY with a JSON list named steps, where each item has keys: tool_name, parameters."
)
SYNTH_SYS = (
    "You are a travel assistant. You have JSON data from various sources.\n"
    "Synthesize it into a comprehensive itinerary.\n"
    'Respond with a single JSON object: { "itinerary": ItineraryItem[], "locations": Location[] }\n'
    "Each ItineraryItem must have: id, title, description, startTime, type\n"
    "Each Location must have: name, latitude, longitude, linkedItineraryId"
)
REFINE_SYS = (
    "You are an AI assistant. The user has modified their travel plan. "
    "Accept the changes and ensure consistency. If an item is deleted, remove its corresponding location. "
    'Respond with the new JSON object: { "itinerary": [...], "locations": [...] }'
)

def _mock_decompose(_: str) -> List[Dict[str, Any]]:
    return [
        {"tool_name": "search_hotels", "parameters": {"location": "Chicago", "checkin": "2025-11-01", "checkout": "2025-11-03"}},
        {"tool_name": "search_events", "parameters": {"location": "Chicago", "date": "2025-11-01"}},
        {"tool_name": "search_flights", "parameters": {"from": "SFO", "to": "ORD", "date": "2025-11-01"}},
    ]

def _mock_synthesize(_: Dict[str, Any]) -> Dict[str, Any]:
    base_time = datetime.utcnow() + timedelta(days=7)
    return {
        "itinerary": [
            {"id": "item_1", "title": "Flight to Chicago", "description": "SFO → ORD on United",
             "startTime": (base_time + timedelta(hours=8)).isoformat(), "type": "travel"},
            {"id": "item_2", "title": "Check-in at Budget Inn Chicago", "description": "Affordable downtown accommodation",
             "startTime": (base_time + timedelta(hours=14)).isoformat(), "type": "lodging"},
            {"id": "item_3", "title": "Art Institute of Chicago", "description": "Free admission on weekends",
             "startTime": (base_time + timedelta(days=1, hours=10)).isoformat(), "type": "activity"},
        ],
        "locations": [
            {"name": "O'Hare International Airport", "latitude": 41.9742, "longitude": -87.9073, "linkedItineraryId": "item_1"},
            {"name": "Budget Inn Chicago", "latitude": 41.8781, "longitude": -87.6298, "linkedItineraryId": "item_2"},
            {"name": "Art Institute of Chicago", "latitude": 41.8796, "longitude": -87.6237, "linkedItineraryId": "item_3"},
        ],
    }

# NEW: async versions of the pipelines
async def run_plan_pipeline_async(goal: str) -> Dict[str, Any]:
    # 1) decompose
    print(USE_MOCK)
    if USE_MOCK:
        steps = _mock_decompose(goal)
    else:
        decomp = await _ask_claude_for_json_async(DECOMPOSE_SYS, f"Goal: {goal}\nReturn: {{\"steps\":[...]}}")
        steps = decomp.get("steps") if isinstance(decomp, dict) else decomp
        if not isinstance(steps, list):
            steps = _mock_decompose(goal)

    # 2) execute mock tools (replace with real ones if you have them)
    # Step 2: execute via ASI-1 (fallback to your mocks if empty)
    ctx_data: Dict[str, Any] = await asi_execute_steps(goal, steps)

    if not ctx_data or not any(ctx_data.get(k, {}).get(v, []) for k, v in [
        ("hotel_data", "hotels"), ("event_data", "events"), ("flight_data", "flights")
    ]):
        # Fallback to existing mocks so you always synthesize something
        ctx_data = {}
        for step in steps:
            tool = step.get("tool_name")
            raw_params = step.get("parameters", {}) or {}
            param_map = {"from": "from_city", "to": "to_city"}
            params = {param_map.get(k, k): v for k, v in raw_params.items()}

            if tool == "search_hotels":
                ctx_data["hotel_data"] = mock_search_hotels(**params)
            elif tool == "search_events":
                ctx_data["event_data"] = mock_search_events(**params)
            elif tool == "search_flights":
                ctx_data["flight_data"] = mock_search_flights(**params)


    # 3) synthesize
    if USE_MOCK:
        return _mock_synthesize(ctx_data)
    synth = await _ask_claude_for_json_async(
        SYNTH_SYS,
        f"Original Goal: {goal}\n\nCollected Data:\n{json.dumps(ctx_data)}"
    )
    if isinstance(synth, dict) and "itinerary" in synth and "locations" in synth:
        return synth
    return _mock_synthesize(ctx_data)

async def run_refine_pipeline_async(itinerary: List[Dict[str, Any]], locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    if USE_MOCK:
        ids = {i["id"] for i in itinerary}
        locs = [l for l in locations if l.get("linkedItineraryId") in ids]
        return {"itinerary": itinerary, "locations": locs}

    refined = await _ask_claude_for_json_async(
        REFINE_SYS,
        f"Here is the user's modified plan:\n{json.dumps({'itinerary': itinerary, 'locations': locations})}"
    )
    if isinstance(refined, dict) and "itinerary" in refined and "locations" in refined:
        return refined

    # safe fallback: filter locations to existing items
    ids = {i["id"] for i in itinerary}
    locs = [l for l in locations if l.get("linkedItineraryId") in ids]
    return {"itinerary": itinerary, "locations": locs}

# ---------- Agent + Chat protocol ----------
agent = Agent()  # Hosted agent on Agentverse; mailbox is implicit in hosted runtime
protocol = Protocol(spec=chat_protocol_spec)

@protocol.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    # ack
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    # greet on session start
    if any(isinstance(item, StartSessionContent) for item in msg.content):
        await ctx.send(sender, _create_text_msg("Hi! I can PLAN trips and REFINE plans. Send:\n- PLAN: <your goal>\n- REFINE: {\"itinerary\":[],\"locations\":[]}"))
        return

    text = msg.text() or ""
    text_stripped = text.strip()

    # ROUTING:
    #  - PLAN: <goal text>
    #  - REFINE: {json}
    if text_stripped.upper().startswith("PLAN:"):
        goal = text_stripped.split(":", 1)[1].strip()
        result = await run_plan_pipeline_async(goal)
        await ctx.send(sender, _create_text_msg(json.dumps(result, indent=2)))
        return

    if text_stripped.upper().startswith("REFINE:"):
        payload = _extract_json(text_stripped)
        itinerary = payload.get("itinerary", []) if isinstance(payload, dict) else []
        locations = payload.get("locations", []) if isinstance(payload, dict) else []
        result = await run_refine_pipeline_async(itinerary, locations)
        await ctx.send(sender, _create_text_msg(json.dumps(result, indent=2)))
        return

    # default: treat input as a planning goal
    result = await run_plan_pipeline_async(text_stripped or "Weekend on a budget in Chicago")
    await ctx.send(sender, _create_text_msg(json.dumps(result, indent=2), end_session=True))

@protocol.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    # could be used for receipts/telemetry
    pass

agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    # Local runner for testing without Agentverse
    import os
    from uagents import Bureau

    print("[Boot] FORCE_MOCK:", FORCE_MOCK,
          "| USE_MOCK (Claude):", USE_MOCK,
          "| ASI key present:", bool(AS1_KEY))

    # Optional: quick smoke test for ASI key
    try:
        ping = client.chat.completions.create(
            model="asi1-mini",
            messages=[{"role": "user", "content": "Return JSON: {\"ok\": true}"}],
            max_tokens=16,
            temperature=0.0,
        )
        print("[ASI] Smoke test:", ping.choices[0].message.content)
    except Exception as e:
        print("[ASI] Smoke test failed:", e)

    # Run a full uAgents loop locally
    bureau = Bureau()         # simple local runtime
    bureau.add(agent)
    bureau.run()
