# Proactive Life Manager Agent

A full-stack web application that uses AI to autonomously plan and manage life activities. Users provide high-level goals (e.g., "Plan a cheap cultural weekend in Chicago"), and the system breaks down the goal, calls external services, and presents an interactive itinerary with a map.

## 🚀 Features

- **AI-Powered Planning**: Autonomous goal decomposition and itinerary creation
- **Interactive Map**: Visual representation of planned locations using Leaflet
- **Editable Itinerary**: Delete, reorder, and refine your plans
- **Real-time Updates**: Instant synchronization between itinerary and map
- **Beautiful UI**: Modern, responsive design with Tailwind CSS

## 🛠️ Technology Stack

- **Frontend**: React 18 with Vite, Tailwind CSS, Leaflet maps
- **Backend**: FastAPI (Python)
- **Agent**: Fetch.ai uAgent framework
- **AI**: Mock LLM functions (ready for real LLM integration)

## 📋 Prerequisites

- Node.js 18+ and npm
- Python 3.8+
- Git

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd calhacks12
```

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
```

### 3. Agent Setup
```bash
cd ../agent
pip install -r requirements.txt
```

### 4. Frontend Setup
```bash
cd ../frontend
npm install
```

## 🏃‍♂️ Running the Application

You'll need three terminal windows to run all components:

### Terminal 1: Start the Agent (Port 8001)
```bash
cd agent
python agent.py
```
The agent will start on `http://127.0.0.1:8001`

### Terminal 2: Start the Backend (Port 8000)
```bash
cd backend
python main.py
```
The backend API will be available at `http://127.0.0.1:8000`

### Terminal 3: Start the Frontend (Port 5173)
```bash
cd frontend
npm run dev
```
The application will open at `http://localhost:5173`

## 📖 Usage

1. **Open the Application**: Navigate to `http://localhost:5173` in your browser

2. **Enter a Goal**: Type your goal in the input field (e.g., "Plan a cheap cultural weekend in Chicago")

3. **Generate Plan**: Click the "Plan" button to generate an itinerary

4. **View Itinerary**: Your planned activities will appear in the left column with:
   - Title and description
   - Start time
   - Activity type (travel, lodging, activity)

5. **Interact with the Map**: The right column shows a map with markers for each location

6. **Edit Your Plan**:
   - **Delete**: Click the ✕ button to remove an item
   - **Reorder**: Use ↑ and ↓ buttons to move items up or down
   - **Update**: Click "Yes, update plan" to confirm changes

## 🏗️ Project Structure

```
calhacks12/
├── backend/
│   ├── main.py           # FastAPI server with endpoints
│   └── requirements.txt   # Python dependencies
├── agent/
│   ├── agent.py          # Fetch.ai uAgent implementation
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Main React component
│   │   ├── main.jsx      # React entry point
│   │   └── index.css     # Tailwind CSS styles
│   ├── index.html        # HTML template
│   ├── package.json      # Node dependencies
│   ├── vite.config.js    # Vite configuration
│   ├── tailwind.config.js # Tailwind configuration
│   └── postcss.config.js # PostCSS configuration
└── README.md            # This file
```

## 🔌 API Endpoints

### Backend (FastAPI)

- `POST /plan` - Create a new itinerary from a user goal
  - Request: `{ "prompt": "string" }`
  - Response: `AgentPlanResponse`

- `POST /refine` - Update an existing itinerary
  - Request: `{ "itinerary": [...], "locations": [...] }`
  - Response: `AgentPlanResponse`

- `GET /health` - Health check endpoint

### Agent (uAgent)

- `POST /plan` - Process planning request
- `POST /refine` - Process refinement request
- `GET /health` - Agent health check

## 📊 Data Models

### UserGoalRequest
```typescript
{
  prompt: string
}
```

### ItineraryItem
```typescript
{
  id: string,
  title: string,
  description: string,
  startTime: string,
  type: 'travel' | 'lodging' | 'activity'
}
```

### Location
```typescript
{
  name: string,
  latitude: number,
  longitude: number,
  linkedItineraryId: string
}
```

### AgentPlanResponse
```typescript
{
  status: string,
  itinerary: ItineraryItem[],
  logs: string[],
  locations: Location[]
}
```

## 🔄 Data Flow

1. **Planning Flow**:
   - User enters goal → React → FastAPI `/plan` → uAgent `/plan`
   - uAgent decomposes goal → Executes mock tools → Synthesizes plan
   - Returns itinerary → FastAPI → React displays results

2. **Refinement Flow**:
   - User edits itinerary → React → FastAPI `/refine` → uAgent `/refine`
   - uAgent processes changes → Updates locations
   - Returns refined plan → FastAPI → React updates display

## 🧪 Mock Functions

The application includes mock functions for:
- `call_llm_api()` - Simulates LLM responses
- `mock_search_flights()` - Returns sample flight data
- `mock_search_hotels()` - Returns sample hotel data
- `mock_search_events()` - Returns sample event data

These can be replaced with real API calls for production use.

## 🎨 Customization

### Integrating Real LLM
Replace the `call_llm_api()` function in both `backend/main.py` and `agent/agent.py` with actual LLM API calls (e.g., OpenAI, Gemini, etc.).

### Adding New Tools
1. Create new mock functions in the backend
2. Add tool execution logic in the agent
3. Update the decomposition prompt to use new tools

### Styling
Modify `frontend/src/index.css` and Tailwind classes in `App.jsx` to customize the appearance.

## 🐛 Troubleshooting

### Port Already in Use
If any port is already in use, you can change it in:
- Backend: `backend/main.py` (line with `uvicorn.run`)
- Agent: `agent/agent.py` (port parameter in Agent initialization)
- Frontend: `frontend/vite.config.js` (server.port)

### CORS Issues
Ensure the backend CORS middleware includes your frontend URL in `allow_origins`.

### Agent Not Running
The backend includes fallback mock data if the agent is not running, allowing testing without the full stack.

## 📝 Notes

- The `@tailwind` warnings in the CSS file are normal and will be processed during build
- The application works with mock data by default - no external APIs required
- All three components (frontend, backend, agent) must be running for full functionality

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📄 License

This project was created for CalHacks 12.0 hackathon.
