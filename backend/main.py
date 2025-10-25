from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import httpx
import json
from datetime import datetime, timedelta
import random

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class UserGoalRequest(BaseModel):
    prompt: str

class ItineraryItem(BaseModel):
    id: str
    title: str
    description: str
    startTime: str
    type: str  # 'travel', 'lodging', 'activity'

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

# Mock LLM function
def call_llm_api(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
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
        
        # Default refinement response
        return {
            "itinerary": [],
            "locations": []
        }
    
    return {}

# Mock external API functions
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

@app.post("/plan", response_model=AgentPlanResponse)
async def plan(request: UserGoalRequest):
    """Handle planning request by forwarding to uAgent"""
    try:
        # Forward request to uAgent
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:8001/plan",
                json={"prompt": request.prompt},
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return AgentPlanResponse(
                    status="success",
                    itinerary=data.get("itinerary", []),
                    logs=data.get("logs", ["Planning completed successfully"]),
                    locations=data.get("locations", [])
                )
            else:
                raise HTTPException(status_code=response.status_code, detail="Agent error")
                
    except httpx.ConnectError:
        # If agent is not running, return mock data directly
        print("Warning: Agent not running, using mock data")
        
        # Mock the agent's response
        plan_steps = call_llm_api(
            "You are an expert planner... Respond ONLY with a JSON list of steps.",
            f"Goal: {request.prompt}"
        )
        
        # Mock tool execution
        context = {
            "hotel_data": mock_search_hotels(),
            "event_data": mock_search_events(),
            "flight_data": mock_search_flights()
        }
        
        # Mock synthesis
        final_plan = call_llm_api(
            "You are a travel assistant. You have JSON data. Synthesize it into an itinerary. Respond with a single JSON object: { itinerary: ItineraryItem[], locations: Location[] }...",
            f"Original Goal: {request.prompt}\n\nCollected Data:\n{json.dumps(context)}"
        )
        
        return AgentPlanResponse(
            status="success",
            itinerary=final_plan.get("itinerary", []),
            logs=["Mock planning completed"],
            locations=final_plan.get("locations", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refine", response_model=AgentPlanResponse)
async def refine(request: Dict[str, Any]):
    """Handle refinement request by forwarding to uAgent"""
    try:
        # Forward request to uAgent
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:8001/refine",
                json=request,
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return AgentPlanResponse(
                    status="success",
                    itinerary=data.get("itinerary", []),
                    logs=data.get("logs", ["Refinement completed successfully"]),
                    locations=data.get("locations", [])
                )
            else:
                raise HTTPException(status_code=response.status_code, detail="Agent error")
                
    except httpx.ConnectError:
        # If agent is not running, return mock refined data
        print("Warning: Agent not running, using mock refinement")
        
        # Mock refinement
        refined_plan = call_llm_api(
            "You are an AI assistant. The user modified their plan. Accept the changes. If an item is deleted, remove its location. Respond with the new, updated JSON object.",
            f"Here is the user's modified plan:\n{json.dumps(request)}"
        )
        
        # Ensure we have valid data
        itinerary = request.get("itinerary", []) if refined_plan.get("itinerary") == [] else refined_plan.get("itinerary", request.get("itinerary", []))
        
        # Filter locations to match itinerary
        itinerary_ids = {item["id"] for item in itinerary}
        locations = [loc for loc in request.get("locations", []) 
                    if loc["linkedItineraryId"] in itinerary_ids]
        
        return AgentPlanResponse(
            status="success",
            itinerary=itinerary,
            logs=["Mock refinement completed"],
            locations=locations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
