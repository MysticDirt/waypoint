import uvicorn
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict

# --- 1. AGENT CONFIGURATION ---

# The agent runs on port 8001 and exposes a REST API
AGENT_URL = "http://127.0.0.1:8001"


# --- 2. FASTAPI APP INITIALIZATION ---

app = FastAPI()

# --- 3. CORS MIDDLEWARE ---
# This is crucial to allow your React frontend (on localhost:5173)
# to talk to this backend (on localhost:8000).

origins = [
    "http://localhost:5173",  # Your frontend's address
    "http://127.0.0.1:5173",
    "http://localhost:5174",  # Alternative frontend port
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],
)


# --- 4. DATA MODELS ---
# These models match the Fetch.ai agent models

class UserGoalRequest(BaseModel):
    prompt: str

class AgentPlanResponse(BaseModel):
    status: str
    itinerary: List[Dict]
    flights: List[Dict]  # New: flight data
    events: List[Dict]   # New: event data
    logs: List[str]
    locations: List[Dict]
    
class PlanRequest(BaseModel):
    prompt: str

class RefineRequest(BaseModel):
    itinerary: List[Dict]
    locations: List[Dict]


# --- 5. API ENDPOINTS ---

@app.get("/health")
async def health_check():
    """A simple health check endpoint."""
    return {"status": "ok", "agent_url": AGENT_URL}

@app.post("/plan", response_model=AgentPlanResponse)
async def create_plan(request: UserGoalRequest):
    """
    Receives the goal from the frontend and forwards it to the Fetch.ai orchestrator agent.
    The orchestrator coordinates with flight_agent and event_agent using Fetch.ai's multi-agent system.
    """
    try:
        print(f"Forwarding request to orchestrator agent: {request.prompt}")
        
        # Send HTTP POST request to the orchestrator agent's REST endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_URL}/plan",
                json={"prompt": request.prompt},
                timeout=180.0  # Give agents time to coordinate (Groq + Claude + data fetching)
            )
            
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                print("Received successful plan from orchestrator.")
                print(f"Flights found: {len(response_data.get('flights', []))}")
                print(f"Events found: {len(response_data.get('events', []))}")
                return AgentPlanResponse(**response_data)
            else:
                error_msg = f"Agent returned status {response.status_code}: {response.text}"
                print(error_msg)
                return AgentPlanResponse(
                    status="error",
                    logs=[error_msg],
                    itinerary=[],
                    flights=[],
                    events=[],
                    locations=[]
                )

    except Exception as e:
        print(f"Error querying orchestrator agent: {e}")
        return AgentPlanResponse(
            status="error",
            logs=[f"Failed to reach agent or agent timed out: {e}"],
            itinerary=[],
            flights=[],
            events=[],
            locations=[]
        )

@app.post("/refine", response_model=AgentPlanResponse)
async def refine_plan(request: RefineRequest):
    """
    Receives an edited itinerary from the frontend and forwards it to the orchestrator for refinement.
    """
    try:
        print(f"Forwarding refinement request to orchestrator with {len(request.itinerary)} items")
        
        # Send HTTP POST request to the orchestrator agent's REST endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_URL}/refine",
                json={"itinerary": request.itinerary, "locations": request.locations},
                timeout=180.0  # Give agents time to refine
            )
            
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                print("Received successful refinement from orchestrator.")
                return AgentPlanResponse(**response_data)
            else:
                error_msg = f"Agent returned status {response.status_code}: {response.text}"
                print(error_msg)
                return AgentPlanResponse(
                    status="error",
                    logs=[error_msg],
                    itinerary=request.itinerary,
                    flights=[],
                    events=[],
                    locations=request.locations
                )

    except Exception as e:
        print(f"Error querying orchestrator for refinement: {e}")
        return AgentPlanResponse(
            status="error",
            logs=[f"Failed to reach agent or agent timed out: {e}"],
            itinerary=request.itinerary,
            flights=[],
            events=[],
            locations=request.locations
        )


# --- 6. RUN THE SERVER ---

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)