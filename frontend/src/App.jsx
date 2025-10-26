import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'

// Fix for default markers in react-leaflet
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

// Component to handle map bounds
function MapBounds({ locations }) {
  const map = useMap()
  
  useEffect(() => {
    if (locations && locations.length > 0) {
      const bounds = L.latLngBounds(locations.map(loc => [loc.latitude, loc.longitude]))
      map.fitBounds(bounds, { padding: [50, 50] })
    }
  }, [locations, map])
  
  return null
}

// Component to render map markers
function MapMarkers({ locations }) {
  return (
    <>
      {locations.map((location, index) => (
        <Marker key={index} position={[location.latitude, location.longitude]}>
          <Popup>
            <div className="font-semibold">{location.name}</div>
            <div className="text-sm text-gray-600">ID: {location.linkedItineraryId}</div>
          </Popup>
        </Marker>
      ))}
    </>
  )
}

function App() {
  const [itinerary, setItinerary] = useState([])
  const [locations, setLocations] = useState([])
  const [prompt, setPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [error, setError] = useState(null)
  const [conversation, setConversation] = useState([]) // Array of {role: 'user'|'assistant', content: string, timestamp: Date}
  const [chatInput, setChatInput] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const chatEndRef = useRef(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    
    setIsLoading(true)
    setError(null)
    
    // Add user message to conversation
    const userMessage = { role: 'user', content: prompt, timestamp: new Date() }
    setConversation(prev => [...prev, userMessage])
    
    try {
      const response = await axios.post('http://127.0.0.1:8000/plan', { 
        prompt,
        conversation_history: conversation 
      })
      
      // Add assistant response to conversation
      const assistantMessage = {
        role: 'assistant',
        content: response.data.logs?.join('\n') || 'Plan generated successfully',
        timestamp: new Date(),
        status: response.data.status
      }
      setConversation(prev => [...prev, assistantMessage])
      
      setItinerary(response.data.itinerary || [])
      setLocations(response.data.locations || [])
      setHasChanges(false)
      setPrompt('') // Clear the main input after submission
      
      // Generate conversation ID if this is a new conversation
      if (!conversationId) {
        setConversationId(Date.now().toString())
      }
    } catch (err) {
      console.error('Error planning:', err)
      setError('Failed to create plan. Please try again.')
      const errorMessage = {
        role: 'assistant',
        content: 'Error: Failed to create plan. Please try again.',
        timestamp: new Date(),
        status: 'error'
      }
      setConversation(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = (id) => {
    setItinerary(prevItinerary => prevItinerary.filter(item => item.id !== id))
    setHasChanges(true)
  }

  const handleSwap = (index1, index2) => {
    if (index2 < 0 || index2 >= itinerary.length) return
    
    const newItinerary = [...itinerary]
    const temp = newItinerary[index1]
    newItinerary[index1] = newItinerary[index2]
    newItinerary[index2] = temp
    
    setItinerary(newItinerary)
    setHasChanges(true)
  }

  const handleRefine = async () => {
    setIsLoading(true)
    setError(null)
    
    const refineMessage = { role: 'user', content: 'Updating plan based on my changes...', timestamp: new Date() }
    setConversation(prev => [...prev, refineMessage])
    
    try {
      const response = await axios.post('http://127.0.0.1:8000/refine', {
        itinerary,
        locations
      })
      
      const assistantMessage = {
        role: 'assistant',
        content: response.data.logs?.join('\n') || 'Plan updated successfully',
        timestamp: new Date(),
        status: response.data.status
      }
      setConversation(prev => [...prev, assistantMessage])
      
      setItinerary(response.data.itinerary || [])
      setLocations(response.data.locations || [])
      setHasChanges(false)
    } catch (err) {
      console.error('Error refining:', err)
      setError('Failed to refine plan. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleChatSubmit = async (e) => {
    e.preventDefault()
    if (!chatInput.trim() || isLoading) return
    
    setIsLoading(true)
    setError(null)
    
    // Add user message to conversation
    const userMessage = { role: 'user', content: chatInput, timestamp: new Date() }
    setConversation(prev => [...prev, userMessage])
    setChatInput('')
    
    try {
      // Send follow-up message with full conversation context
      const response = await axios.post('http://127.0.0.1:8000/plan', { 
        prompt: chatInput,
        conversation_history: [...conversation, userMessage],
        itinerary: itinerary,
        locations: locations
      })
      
      // Add assistant response
      const assistantMessage = {
        role: 'assistant',
        content: response.data.logs?.join('\n') || 'Updated based on your input',
        timestamp: new Date(),
        status: response.data.status
      }
      setConversation(prev => [...prev, assistantMessage])
      
      // Update itinerary if provided
      if (response.data.itinerary) {
        setItinerary(response.data.itinerary)
      }
      if (response.data.locations) {
        setLocations(response.data.locations)
      }
      setHasChanges(false)
    } catch (err) {
      console.error('Error in chat:', err)
      const errorMessage = {
        role: 'assistant',
        content: 'Error: Failed to process your message. Please try again.',
        timestamp: new Date(),
        status: 'error'
      }
      setConversation(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }
  
  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation])
  
  // Check if last message needs clarification
  const needsClarification = conversation.length > 0 && 
    conversation[conversation.length - 1].status === 'needs_clarification'

  const getTypeColor = (type) => {
    switch(type) {
      case 'travel': return 'bg-blue-100 text-blue-800 border-blue-200'
      case 'lodging': return 'bg-green-100 text-green-800 border-green-200'
      case 'activity': return 'bg-purple-100 text-purple-800 border-purple-200'
      default: return 'bg-gray-100 text-gray-800 border-gray-200'
    }
  }

  const formatTime = (timeString) => {
    try {
      const date = new Date(timeString)
      return date.toLocaleString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return timeString
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="grid grid-cols-1 md:grid-cols-2 h-screen">
        {/* Left Column - Itinerary */}
        <div className="flex flex-col h-full overflow-hidden">
          <div className="bg-white shadow-sm border-b">
            <div className="p-6">
              <h1 className="text-3xl font-bold text-gray-900 mb-6">
                Proactive Life Manager
              </h1>
              
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Enter your goal (e.g., 'Plan a cheap cultural weekend in Chicago')"
                    className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={isLoading}
                  />
                  <button
                    type="submit"
                    disabled={isLoading || !prompt.trim()}
                    className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                  >
                    Plan
                  </button>
                </div>
              </form>

              {error && (
                <div className="mt-4 p-3 bg-red-100 border border-red-300 text-red-700 rounded-lg">
                  {error}
                </div>
              )}
              
              {/* Chat/Conversation Panel */}
              {conversation.length > 0 && (
                <div className="mt-4 border border-gray-300 rounded-lg bg-white">
                  <div className="bg-gray-100 px-4 py-2 border-b border-gray-300 rounded-t-lg">
                    <h3 className="font-semibold text-sm text-gray-700">💬 Conversation with AI</h3>
                  </div>
                  <div className="max-h-64 overflow-y-auto p-4 space-y-3">
                    {conversation.map((message, index) => (
                      <div
                        key={index}
                        className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[80%] rounded-lg px-4 py-3 ${
                            message.role === 'user'
                              ? 'bg-blue-600 text-white'
                              : message.status === 'error'
                              ? 'bg-red-100 text-red-800 border border-red-300'
                              : message.status === 'needs_clarification'
                              ? 'bg-yellow-50 text-yellow-900 border-2 border-yellow-400 shadow-md'
                              : 'bg-gray-100 text-gray-800 border border-gray-300'
                          }`}
                        >
                          {message.status === 'needs_clarification' && (
                            <div className="flex items-center gap-2 mb-2 pb-2 border-b border-yellow-300">
                              <span className="text-xl">❓</span>
                              <span className="font-semibold text-sm">I need your help!</span>
                            </div>
                          )}
                          <div className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</div>
                          <div className={`text-xs mt-2 ${
                            message.role === 'user' ? 'text-blue-100' : 'text-gray-500'
                          }`}>
                            {new Date(message.timestamp).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                    ))}
                    <div ref={chatEndRef} />
                  </div>
                  
                  {/* Chat Input */}
                  <form onSubmit={handleChatSubmit} className={`border-t p-3 ${
                    needsClarification ? 'bg-yellow-50 border-yellow-300' : 'border-gray-300'
                  }`}>
                    {needsClarification && (
                      <div className="mb-2 text-xs text-yellow-800 font-medium">
                        👆 Please answer the questions above
                      </div>
                    )}
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        placeholder={needsClarification ? "Type your answer here..." : "Reply to the AI or ask follow-up questions..."}
                        className={`flex-1 px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 ${
                          needsClarification 
                            ? 'border-yellow-400 focus:ring-yellow-500 bg-white' 
                            : 'border-gray-300 focus:ring-blue-500'
                        }`}
                        disabled={isLoading}
                      />
                      <button
                        type="submit"
                        disabled={isLoading || !chatInput.trim()}
                        className={`px-4 py-2 text-sm rounded-lg transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed ${
                          needsClarification
                            ? 'bg-yellow-500 text-white hover:bg-yellow-600'
                            : 'bg-blue-600 text-white hover:bg-blue-700'
                        }`}
                      >
                        {needsClarification ? 'Answer' : 'Send'}
                      </button>
                    </div>
                  </form>
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <div className="text-center">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <p className="mt-2 text-gray-600">Loading...</p>
                </div>
              </div>
            )}

            {!isLoading && itinerary.length > 0 && (
              <div className="space-y-4">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-xl font-semibold text-gray-800">Your Itinerary</h2>
                  {hasChanges && (
                    <button
                      onClick={handleRefine}
                      className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                    >
                      Yes, update plan
                    </button>
                  )}
                </div>

                {itinerary.map((item, index) => (
                  <div
                    key={item.id}
                    className={`p-4 rounded-lg border-2 ${getTypeColor(item.type)} transition-all hover:shadow-md`}
                  >
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="font-semibold text-lg">{item.title}</h3>
                          <span className={`px-2 py-1 text-xs rounded-full font-medium ${getTypeColor(item.type)}`}>
                            {item.type}
                          </span>
                        </div>
                        <p className="text-gray-700 mb-2">{item.description}</p>
                        <p className="text-sm text-gray-600">
                          {formatTime(item.startTime)}
                        </p>
                      </div>
                      
                      <div className="flex flex-col gap-1 ml-4">
                        <button
                          onClick={() => handleSwap(index, index - 1)}
                          disabled={index === 0}
                          className="p-1 text-gray-600 hover:text-gray-900 disabled:text-gray-300 disabled:cursor-not-allowed"
                          title="Move up"
                        >
                          ↑
                        </button>
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="p-1 text-red-600 hover:text-red-800"
                          title="Delete"
                        >
                          ✕
                        </button>
                        <button
                          onClick={() => handleSwap(index, index + 1)}
                          disabled={index === itinerary.length - 1}
                          className="p-1 text-gray-600 hover:text-gray-900 disabled:text-gray-300 disabled:cursor-not-allowed"
                          title="Move down"
                        >
                          ↓
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!isLoading && itinerary.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                <p className="text-lg">No itinerary yet.</p>
                <p className="mt-2">Enter a goal above to get started!</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column - Map */}
        <div className="h-full bg-gray-200 relative">
          <MapContainer
            center={[41.8781, -87.6298]}
            zoom={12}
            className="h-full w-full"
          >
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            />
            <MapMarkers locations={locations} />
            <MapBounds locations={locations} />
          </MapContainer>
        </div>
      </div>
    </div>
  )
}

export default App
