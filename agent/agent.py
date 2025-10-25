from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low, register_agent_with_mailbox
from typing import List, Dict, Any
import json
from datetime import datetime, timedelta
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

# new imports
import os
from anthropic import Anthropic, APIStatusError
from dotenv import load_dotenv

load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

def _ask_claude_for_json(system_prompt: str, user_prompt: str) -> dict | list:
    """
    Calls Claude and tries to parse a single JSON object or array from the response.
    Falls back to {} on failure (your code already guards).
    """
    try:
        msg = anthropic_client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.1
        )
        # Claude returns a list of content blocks; we expect text in the first
        text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        # robust JSON extraction (handles code fences / extra prose)
        import re, json
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
    except APIStatusError as e:
        # log or print(e) if you want visibility
        pass
    except Exception:
        pass
    return {}

# swap this into your code: replace the whole mock call_llm_api with:
def call_llm_api(system_prompt: str, user_prompt: str) -> Any:
    return _ask_claude_for_json(system_prompt, user_prompt)


# FastAPI app for HTTP endpoints
app = FastAPI()

# Pydantic Models (matching backend)
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

# Initialize the agent
agent = Agent(
    name="PlannerAgent",
    seed="planner_agent_seed_12345",
    port=8001,
    endpoint=["http://127.0.0.1:8001/submit"],
    mailbox=True
)

# Fund the agent if needed
fund_agent_if_low(agent.wallet.address())

# Mock LLM function (same as backend)
def mock_call_llm_api(system_prompt: str, user_prompt: str) -> Any:
    """Mock LLM API call that returns structured responses based on the prompt"""
    
    # Check if this is a decomposition prompt
    if "Respond ONLY with a JSON list of steps" in system_prompt:
        # Return mock decomposition steps
        return [
            {"tool_name": "search_hotels", "parameters": {"location": "Chicago", "checkin": "2025-11-01", "checkout": "2025-11-03"}},
            {"tool_name": "search_events", "parameters": {"location": "Chicago", "date": "2025-11-01"}},
            {"tool_name": "search_flights", "parameters": {"from": "SFO", "to": "ORD", "date": "2025-11-01"}}
        ]
    
    # Check if this is a synthesis prompt
    elif "Synthesize it into an itinerary" in system_prompt:
        # Return mock synthesized itinerary
        base_time = datetime.now() + timedelta(days=7)
        return {
            "itinerary": [
                {
                    "id": "item_1",
                    "title": "Flight to Chicago",
                    "description": "Depart from SFO to ORD on United Airlines",
                    "startTime": (base_time + timedelta(hours=8)).isoformat(),
                    "type": "travel"
                },
                {
                    "id": "item_2",
                    "title": "Check-in at Budget Inn Chicago",
                    "description": "Affordable downtown accommodation with great reviews",
                    "startTime": (base_time + timedelta(hours=14)).isoformat(),
                    "type": "lodging"
                },
                {
                    "id": "item_3",
                    "title": "Art Institute of Chicago",
                    "description": "World-renowned art museum with free admission on weekends",
                    "startTime": (base_time + timedelta(days=1, hours=10)).isoformat(),
                    "type": "activity"
                },
                {
                    "id": "item_4",
                    "title": "Chicago Cultural Center",
                    "description": "Free exhibitions and performances",
                    "startTime": (base_time + timedelta(days=1, hours=14)).isoformat(),
                    "type": "activity"
                },
                {
                    "id": "item_5",
                    "title": "Millennium Park Concert",
                    "description": "Free outdoor concert at Jay Pritzker Pavilion",
                    "startTime": (base_time + timedelta(days=1, hours=18)).isoformat(),
                    "type": "activity"
                }
            ],
            "locations": [
                {
                    "name": "O'Hare International Airport",
                    "latitude": 41.9742,
                    "longitude": -87.9073,
                    "linkedItineraryId": "item_1"
                },
                {
                    "name": "Budget Inn Chicago",
                    "latitude": 41.8781,
                    "longitude": -87.6298,
                    "linkedItineraryId": "item_2"
                },
                {
                    "name": "Art Institute of Chicago",
                    "latitude": 41.8796,
                    "longitude": -87.6237,
                    "linkedItineraryId": "item_3"
                },
                {
                    "name": "Chicago Cultural Center",
                    "latitude": 41.8837,
                    "longitude": -87.6249,
                    "linkedItineraryId": "item_4"
                },
                {
                    "name": "Millennium Park",
                    "latitude": 41.8826,
                    "longitude": -87.6234,
                    "linkedItineraryId": "item_5"
                }
            ]
        }
    
    # Check if this is a refinement prompt
    elif "Accept the changes" in system_prompt:
        # Parse the modified plan from user_prompt and return it
        try:
            # Extract the itinerary from the user prompt
            import re
            match = re.search(r'\{.*\}', user_prompt, re.DOTALL)
            if match:
                data = json.loads(match.group())
                # Filter locations to match remaining itinerary items
                itinerary_ids = {item["id"] for item in data.get("itinerary", [])}
                filtered_locations = [loc for loc in data.get("locations", []) 
                                    if loc["linkedItineraryId"] in itinerary_ids]
                return {
                    "itinerary": data.get("itinerary", []),
                    "locations": filtered_locations
                }
        except:
            pass
        
        # Default refinement response - return what was sent
        return json.loads(user_prompt) if "{" in user_prompt else {"itinerary": [], "locations": []}
    
    return {}

# Mock tool functions
def mock_search_flights(from_city: str = "SFO", to_city: str = "ORD", date: str = "") -> Dict[str, Any]:
    """Mock flight search API"""
    return {
        "flights": [
            {
                "airline": "United Airlines",
                "flight_number": "UA123",
                "departure": from_city,
                "arrival": to_city,
                "price": 250,
                "departure_time": "08:00",
                "arrival_time": "14:00"
            },
            {
                "airline": "Southwest",
                "flight_number": "SW456",
                "departure": from_city,
                "arrival": to_city,
                "price": 180,
                "departure_time": "10:30",
                "arrival_time": "16:30"
            }
        ]
    }

def mock_search_hotels(location: str = "Chicago", checkin: str = "", checkout: str = "") -> Dict[str, Any]:
    """Mock hotel search API"""
    return {
        "hotels": [
            {
                "name": "Budget Inn Chicago",
                "address": "123 Downtown St, Chicago, IL",
                "price_per_night": 75,
                "rating": 4.2,
                "latitude": 41.8781,
                "longitude": -87.6298
            },
            {
                "name": "Chicago Hostel",
                "address": "456 Loop Ave, Chicago, IL",
                "price_per_night": 35,
                "rating": 4.5,
                "latitude": 41.8850,
                "longitude": -87.6300
            }
        ]
    }

def mock_search_events(location: str = "Chicago", date: str = "") -> Dict[str, Any]:
    """Mock events search API"""
    return {
        "events": [
            {
                "name": "Art Institute of Chicago",
                "type": "museum",
                "price": 0,
                "description": "Free admission on weekends",
                "latitude": 41.8796,
                "longitude": -87.6237
            },
            {
                "name": "Chicago Cultural Center",
                "type": "cultural",
                "price": 0,
                "description": "Free exhibitions and performances",
                "latitude": 41.8837,
                "longitude": -87.6249
            },
            {
                "name": "Millennium Park Concert",
                "type": "concert",
                "price": 0,
                "description": "Free outdoor concert",
                "latitude": 41.8826,
                "longitude": -87.6234
            }
        ]
    }

# HTTP endpoint for planning
@app.post("/plan")
async def handle_plan(request: UserGoalRequest):
    """Handle planning request"""
    prompt = request.prompt
    logs = []
    
    # Step 1: Decompose the goal
    logs.append(f"Decomposing goal: {prompt}")
    system_prompt = "You are an expert planner. Break down the user's goal into actionable steps. Respond ONLY with a JSON list of steps."
    user_prompt = f"Goal: {prompt}"
    
    plan_steps_json = call_llm_api(system_prompt, user_prompt)
    logs.append(f"Generated {len(plan_steps_json)} planning steps")
    
    # Step 2: Execute tools
    context = {}
    for step in plan_steps_json:
        tool_name = step.get("tool_name")
        params = step.get("parameters", {})
        logs.append(f"Executing tool: {tool_name}")
        
        if tool_name == "search_hotels":
            context["hotel_data"] = mock_search_hotels(**params)
        elif tool_name == "search_events":
            context["event_data"] = mock_search_events(**params)
        elif tool_name == "search_flights":
            context["flight_data"] = mock_search_flights(**params)
    
    logs.append("All tools executed successfully")
    
    # Step 3: Synthesize the plan
    logs.append("Synthesizing final itinerary")
    system_prompt = """You are a travel assistant. You have JSON data from various sources. 
    Synthesize it into a comprehensive itinerary. 
    Respond with a single JSON object: { "itinerary": ItineraryItem[], "locations": Location[] }
    Each ItineraryItem must have: id, title, description, startTime, type
    Each Location must have: name, latitude, longitude, linkedItineraryId"""
    
    user_prompt = f"Original Goal: {prompt}\n\nCollected Data:\n{json.dumps(context, indent=2)}"
    
    final_plan_json = call_llm_api(system_prompt, user_prompt)
    logs.append("Itinerary synthesis complete")
    
    # Step 4: Return the response
    return {
        "status": "success",
        "itinerary": final_plan_json.get("itinerary", []),
        "logs": logs,
        "locations": final_plan_json.get("locations", [])
    }

# HTTP endpoint for refinement
@app.post("/refine")
async def handle_refine(request: Dict[str, Any]):
    """Handle refinement request"""
    logs = []
    
    # Extract the modified itinerary and locations
    modified_itinerary = request.get("itinerary", [])
    modified_locations = request.get("locations", [])
    
    logs.append(f"Received modified plan with {len(modified_itinerary)} items")
    
    # Step 1: Refine the plan
    system_prompt = """You are an AI assistant. The user has modified their travel plan. 
    Accept the changes and ensure consistency. 
    If an item is deleted, remove its corresponding location. 
    Respond with the new, updated JSON object containing itinerary and locations arrays."""
    
    user_prompt = f"Here is the user's modified plan:\n{json.dumps({'itinerary': modified_itinerary, 'locations': modified_locations}, indent=2)}"
    
    new_plan_json = call_llm_api(system_prompt, user_prompt)
    
    # Ensure locations match itinerary items
    itinerary_ids = {item["id"] for item in modified_itinerary}
    filtered_locations = [loc for loc in modified_locations 
                         if loc["linkedItineraryId"] in itinerary_ids]
    
    logs.append(f"Refined plan with {len(modified_itinerary)} items and {len(filtered_locations)} locations")
    logs.append("Refinement complete")
    
    # Step 2: Return the refined response
    return {
        "status": "success",
        "itinerary": modified_itinerary,
        "logs": logs,
        "locations": filtered_locations
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agent", "address": agent.address}

# Agent startup and shutdown
@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"PlannerAgent started with address: {agent.address}")

@agent.on_event("shutdown")
async def shutdown(ctx: Context):
    ctx.logger.info("PlannerAgent shutting down")

if __name__ == "__main__":
    # Run both the agent and FastAPI server
    import threading
    import time
    
    # Start the agent in a separate thread
    def run_agent():
        agent.run()
    
    agent_thread = threading.Thread(target=run_agent)
    agent_thread.daemon = True
    agent_thread.start()
    
    # Give the agent time to start
    time.sleep(2)
    
    # Run the FastAPI server
    uvicorn.run(app, host="127.0.0.1", port=8001)
