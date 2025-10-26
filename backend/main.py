import uvicorn
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import os
from datetime import datetime, timezone

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

# --- 4. DATA MODELS (from your README) ---
# These models must match the models in your agent.py file

class UserGoalRequest(BaseModel):
    prompt: str

# This is the model *we expect back* from the agent
class AgentPlanResponse(BaseModel):
    status: str
    itinerary: List[Dict[str, Any]]
    logs: List[str]
    locations: List[Dict[str, Any]]

# This is the model *we send* to the agent
class PlanRequest(BaseModel):
    prompt: str

# This is the model for refining an existing itinerary
class RefineRequest(BaseModel):
    itinerary: List[Dict[str, Any]]
    locations: List[Dict[str, Any]]

# User profile config (used to inform the agent/LLM)
class UserProfile(BaseModel):
    city: str
    latitude: float
    longitude: float
    timezone: str

AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

USER_CITY = os.getenv("USER_CITY", "Berkeley, CA, USA")
USER_LAT = float(os.getenv("USER_LAT", "37.8715"))
USER_LON = float(os.getenv("USER_LON", "-122.2730"))
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "America/Los_Angeles")

current_profile = UserProfile(
    city=USER_CITY,
    latitude=USER_LAT,
    longitude=USER_LON,
    timezone=USER_TIMEZONE,
)

# --- 5. API ENDPOINTS ---

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "backend"}

@app.get("/profile", response_model=UserProfile)
async def get_profile():
    return current_profile

@app.post("/profile", response_model=UserProfile)
async def set_profile(profile: UserProfile):
    global current_profile
    current_profile = profile
    return current_profile

@app.post("/plan", response_model=AgentPlanResponse)
async def create_plan(request: UserGoalRequest):
    """
    Receives the goal from the frontend and forwards it to the uAgent.
    """
    try:
        # Inject context: user's location and current time, and enforce future planning
        now_iso = datetime.now(timezone.utc).isoformat()
        context_prefix = (
            f"CONTEXT: user_city={current_profile.city}; user_lat={current_profile.latitude}; user_lon={current_profile.longitude}; "
            f"user_timezone={current_profile.timezone}; now_utc={now_iso}. "
            f"Always plan into the future from now; avoid proposing past dates.\n"
        )
        prompt_with_context = f"{context_prefix}{request.prompt}"
        # Forward request to uAgent
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_BASE_URL}/plan",
                json={"prompt": prompt_with_context},
                timeout=30.0
            )
            print(f"Response status: {response.status_code}")
            if response.status_code == 200:
                response_data = response.json()
                print("Received successful plan from agent.")
                return AgentPlanResponse(**response_data)
            else:
                error_msg = f"Agent returned status {response.status_code}: {response.text}"
                print(error_msg)
                return AgentPlanResponse(
                    status="error",
                    logs=[error_msg],
                    itinerary=[],
                    locations=[]
                )

    except Exception as e:
        print(f"Error querying agent: {e}")
        return AgentPlanResponse(
            status="error",
            logs=[f"Failed to reach agent or agent timed out: {e}"],
            itinerary=[],
            locations=[]
        )

@app.post("/refine", response_model=AgentPlanResponse)
async def refine_plan(request: RefineRequest):
    """
    Receives an edited itinerary from the frontend and forwards it to the uAgent for refinement.
    """
    try:
        print(f"Forwarding refinement request to agent with {len(request.itinerary)} items")
        
        # Send HTTP POST request to the agent's REST endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_URL}/refine",
                json={"itinerary": request.itinerary, "locations": request.locations},
                timeout=180.0  # Give the agent 3 minutes to run
            )
            
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                print("Received successful refinement from agent.")
                return AgentPlanResponse(**response_data)
            else:
                error_msg = f"Agent returned status {response.status_code}: {response.text}"
                print(error_msg)
                return AgentPlanResponse(
                    status="error",
                    logs=[error_msg],
                    itinerary=request.itinerary,  # Return original itinerary on error
                    locations=request.locations
                )

    except Exception as e:
        print(f"Error querying agent for refinement: {e}")
        return AgentPlanResponse(
            status="error",
            logs=[f"Failed to reach agent or agent timed out: {e}"],
            itinerary=request.itinerary,  # Return original itinerary on error
            locations=request.locations
        )


# --- 6. RUN THE SERVER ---

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)