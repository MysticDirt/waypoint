from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import httpx
import os

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

# Agent forwarding base URL (agent service)
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

@app.post("/plan", response_model=AgentPlanResponse)
async def plan(request: UserGoalRequest):
    """Handle planning request by forwarding to uAgent"""
    try:
        # Forward request to uAgent
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_BASE_URL}/plan",
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
        # Agent service unavailable
        raise HTTPException(status_code=502, detail="Agent service unavailable")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refine", response_model=AgentPlanResponse)
async def refine(request: Dict[str, Any]):
    """Handle refinement request by forwarding to uAgent"""
    try:
        # Forward request to uAgent
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_BASE_URL}/refine",
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
        # Agent service unavailable
        raise HTTPException(status_code=502, detail="Agent service unavailable")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
