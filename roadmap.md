Hackathon Roadmap: The Proactive Life Manager Agent

Project Goal: A single, intelligent agent that takes a vague, high-level user goal (e.g., "Plan a cultural weekend trip under $500"), autonomously breaks it down, queries multiple services, and presents a final, interactive and modifiable itinerary with map integration.

Tech Stack:

Frontend: React.js (with React Leaflet for maps and a library like react-beautiful-dnd for drag-and-drop)

Backend: FastAPI

Agent Framework: Fetch.ai uAgents & Agentverse

Reasoning Engine: LLM (Gemini, Claude, or other)

Tool/Service Integration: MCP (Model Context Protocol) or direct API calls

Phase 0: Pre-Hackathon (Preparation)

The goal here is to not waste precious hackathon time on boilerplate and setup.

Team & Roles:

Frontend (React): 1-2 members.

Backend (FastAPI): 1 member.

Agent/LLM (Fetch.ai, LLM): 1 member (can overlap with Backend).

Environment Setup:

Frontend: Create a new React app (Vite). Include axios. Install react-leaflet, leaflet. Optional but recommended: Install react-beautiful-dnd or similar for easy list swapping.

Backend: Create a FastAPI project (main.py, requirements.txt).

Agent: Install uagent and run the "hello world" example. Register on Agentverse.

API Keys & Access:

Secure LLM API key (e.g., Google AI Studio for Gemini).

Get Agentverse credentials.

Find 2-3 free external APIs for tools (weather, mock flights, city events).

Get map tile access (e.g., OpenStreetMap).

Architecture & Data Modeling:

Flow: React -> FastAPI -> uAgent -> LLM (Plan) -> uAgent (Tools) -> LLM (Synthesize) -> FastAPI -> React.

NEW: Add a feedback loop: React (modified list) -> FastAPI -> uAgent -> LLM (Refine) -> FastAPI -> React.

UserGoalRequest: { "prompt": "string" }

AgentPlanResponse: { "status": "string", "itinerary": "ItineraryItem[]", "logs": "string[]", "locations": "Location[]" }

ItineraryItem: { "id": "string", "title": "string", "description": "string", "startTime": "string", "type": "string" }

Location: { "name": "string", "latitude": "number", "longitude": "number", "linkedItineraryId": "string" }

Phase 1: The "Plumbing" (MVP Backend & Frontend)

Goal: Get React to talk to FastAPI. No agent, no LLM yet.

Backend (FastAPI):

Create GET / and POST /plan endpoints.

The /plan endpoint takes UserGoalRequest and returns a mock, hard-coded JSON response:

{
  "status": "success",
  "itinerary": [
    { "id": "item-1", "title": "Flight to Chicago", "description": "Arrive at ORD", "startTime": "10:00 AM", "type": "travel" },
    { "id": "item-2", "title": "Check into Mock Hotel", "description": "Downtown", "startTime": "12:00 PM", "type": "lodging" },
    { "id": "item-3", "title": "Visit Mock Museum", "description": "Art exhibit", "startTime": "2:00 PM", "type": "activity" }
  ],
  "logs": ["Request received", "Mock plan generated"],
  "locations": [
    { "name": "Mock Hotel", "latitude": 41.8781, "longitude": -87.6298, "linkedItineraryId": "item-2" },
    { "name": "Mock Museum", "latitude": 41.8795, "longitude": -87.6242, "linkedItineraryId": "item-3" }
  ]
}


Frontend (React):

Build the main UI component (two-column layout).

Left Side (Itinerary):

Input field and "Submit" button.

Loading state.

Itinerary List:

Use useState to store the itinerary array from the API.

.map() over the array to render each item as a list element.

Each item MUST have an "X" (delete) button. (Implement handleDelete(id) which filters the state array).

Each item MUST have "Swap" buttons (up/down arrows). (Implement handleSwap(index1, index2) which reorders the state array).

(Drag-and-drop is a better "Swap" - implement if time allows).

Add a "Yes, update plan" button (disabled by default). Enable it after the user makes a change (delete/swap).

Right Side (Map):

<MapContainer> component.

Render locations array as <Marker> components.

Milestone 1: You see the mock itinerary as a list. You can click "X" to remove an item or "Swap" to reorder items. The map shows the mock pins. The "Yes, update plan" button becomes active when you make a change.

Phase 2: The "Brain" (LLM Planner Integration)

Goal: Replace the mock response with a real plan from the LLM. No tool use yet.

Backend (FastAPI):

Modify /plan to call your uAgent (e.g., via HTTP request to the agent's server).

Agent (uAgent & LLM):

Create PlannerAgent with a ReceiveGoal message handler.

On receive:

Construct "Prompt 1" (The Decomposer):

System Prompt: "You are an expert planner... [same as before] ... Respond ONLY with a JSON object."

User Prompt: f"Goal: {user_goal_prompt}"

Example LLM Output: (Same as before - a list of steps).

Call LLM API, parse the JSON response.

For now, just return this JSON plan (the steps) to the FastAPI endpoint.

Frontend (React):

Update the UI to just display the raw JSON steps list (for debugging). The interactive list and map won't work yet.

Milestone 2: You type in a goal, and the app displays the LLM's generated JSON step-by-step plan (not the final itinerary).

Phase 3: The "Hands" (Autonomous Tool Use)

Goal: Make the agent execute the plan from Phase 2.

Agent (uAgent Logic):

Modify the ReceiveGoal handler. After getting the steps from the LLM:

Do not return. Iterate through the steps.

Create a context = {}.

Create run_tool(tool_name, parameters) function.

Use if/else block to call real or mock APIs (flights, hotels, events), ensuring you get latitude and longitude for locations.

Store all results in the context object.

Frontend (React):

Implement a "live log" or status update (Simple: print() to agent console. Advanced: WebSockets).

Milestone 3: You submit a goal. The backend console logs show the agent executing each step and gathering data (e.g., "Hotel data received (with lat/lon).").

Phase 4: The "Synthesis" & Feedback Loop

Goal: Generate the final interactive plan and handle user changes.

Agent (uAgent Logic - Synthesis):

After the steps loop (Phase 3) is complete:

Construct "Prompt 2" (The Synthesizer):

System Prompt: "You are a helpful travel assistant. You have JSON data from APIs. Your job is to synthesize this into an itinerary. Respond with a single JSON object containing:

itinerary: An array of ItineraryItem objects ({ "id", "title", "description", "startTime", "type" }).

locations: An array of Location objects ({ "name", "latitude", "longitude", "linkedItineraryId" }).
Ensure the id and linkedItineraryId fields match."

User Prompt: f"Original Goal: ...\n\nCollected Data:\n{context_object_as_json_string}\n\nPlease generate the final JSON plan."

Call LLM, get the JSON, and send this final JSON object back to FastAPI.

Backend (FastAPI):

The /plan endpoint now returns this final JSON object (with itinerary and locations arrays).

Create a NEW endpoint: POST /refine. This endpoint will take a modified AgentPlanResponse object from the user.

Agent (uAgent Logic - Refinement):

Create a NEW message handler: ReceiveRefinement.

This handler receives the modified itinerary array (and old locations) from the user.

Construct "Prompt 3" (The Refiner):

System Prompt: "You are an AI assistant. The user has taken your original plan and modified it (deleted or reordered items). Your job is to accept these changes and update the plan. If they deleted a museum, remove its location from the map. If they swapped items, confirm the new order. Respond with the new, updated JSON object (itinerary and locations)."

User Prompt: f"Here is the user's modified plan:\n{modified_itinerary_array_as_json}\n\nPlease regenerate the final JSON plan and location list to match."

Call LLM, get the new JSON, and send it back via FastAPI.

Frontend (React):

The main handleSubmit function now populates the itinerary and locations state from the /plan response, rendering the list and map.

Wire up the "Yes, update plan" button.

onClick, it should POST the current, modified itinerary state (and locations state) to the new /refine endpoint.

It should show a loading spinner.

When the response comes back, it should update the itinerary and locations state again with the AI's confirmed changes.

Milestone 4 (The "Money Shot"):

You type in a goal. The app shows a spinner, then a full itinerary list and map pins appear.

You click "X" on "Visit Mock Museum". The item vanishes from the list.

You click "Yes, update plan".

The app shows a spinner, then re-renders. The museum is still gone, and (critically) the AI has now also removed the museum's pin from the map.

Phase 5: Polish & Presentation

Goal: Make it look impressive for the judges.

Frontend (React):

Spend 2 hours on pure CSS/UI library (Tailwind, etc.).

Make it clean, modern, and responsive.

Map Polish:

Style map markers. Add <Popup> to show names on click.

Bonus: Clicking an item in the list makes the map flyTo its corresponding pin.

Implement the WebSocket logger for a "live agent status" feed.

Backend (FastAPI/Agent):

Clean up logs. Add error handling (what if an API fails?).

Pitch:

Focus on the "autonomous feedback loop": "We give the agent a vague goal, it creates a plan. But we don't just stop there. The user can visually edit the plan—deleting or reordering items—and with one click, the agent understands and accepts those changes, regenerating the entire itinerary and map data to match."

Stretch Goals (If You Have Extra Time)

True MCP: Fully implement separate FlightAgent, HotelAgent on Agentverse.

Persistence: Save past plans to localStorage or a simple DB.

Drag-and-Drop: Implement react-beautiful-dnd to make swapping items intuitive.