import uvicorn
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # Import CORS
from pydantic import BaseModel

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
    itinerary: list
    logs: list
    locations: list
    
# This is the model *we send* to the agent
class PlanRequest(BaseModel):
    prompt: str


# --- 5. API ENDPOINTS ---

@app.get("/health")
async def health_check():
    """A simple health check endpoint."""
    return {"status": "ok", "agent_url": AGENT_URL}

@app.post("/plan", response_model=AgentPlanResponse)
async def create_plan(request: UserGoalRequest):
    """
    Receives the goal from the frontend and forwards it to the uAgent.
    """
    try:
        print(f"Forwarding request to agent: {request.prompt}")
        
        # Send HTTP POST request to the agent's REST endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_URL}/plan",
                json={"prompt": request.prompt},
                timeout=180.0  # Give the agent 3 minutes to run (Claude + SerpApi can be slow)
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

# You can add your /refine endpoint here later,
# following the same pattern as /plan


# --- 6. RUN THE SERVER ---

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)