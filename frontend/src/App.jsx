import React, { useState, useEffect, useRef, Component } from 'react'
import axios from 'axios'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'

// Error Boundary Component
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by boundary:', error, errorInfo)
    this.setState({ error, errorInfo })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-red-50 flex items-center justify-center p-4">
          <div className="bg-white p-8 rounded-lg shadow-lg max-w-2xl">
            <h1 className="text-2xl font-bold text-red-600 mb-4">Something went wrong</h1>
            <details className="text-sm">
              <summary className="cursor-pointer text-gray-700 font-medium mb-2">Error Details</summary>
              <pre className="bg-gray-100 p-4 rounded overflow-auto text-xs">
                {this.state.error && this.state.error.toString()}
                {this.state.errorInfo && this.state.errorInfo.componentStack}
              </pre>
            </details>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Reload Page
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

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
      // Filter out locations without valid coordinates
      const validLocations = locations.filter(loc => 
        loc && 
        typeof loc.latitude === 'number' && 
        typeof loc.longitude === 'number' &&
        !isNaN(loc.latitude) && 
        !isNaN(loc.longitude)
      )
      
      if (validLocations.length > 0) {
        try {
          const bounds = L.latLngBounds(validLocations.map(loc => [loc.latitude, loc.longitude]))
          map.fitBounds(bounds, { padding: [50, 50] })
        } catch (error) {
          console.error('Error setting map bounds:', error)
        }
      }
    }
  }, [locations, map])
  
  return null
}

// Component to render map markers with numbers
function MapMarkers({ locations, itinerary }) {
  if (!locations || locations.length === 0) return null
  
  // Filter out locations without valid coordinates
  const validLocations = locations.filter(loc => 
    loc && 
    typeof loc.latitude === 'number' && 
    typeof loc.longitude === 'number' &&
    !isNaN(loc.latitude) && 
    !isNaN(loc.longitude)
  )
  
  // Create a map of itinerary IDs to their index (number)
  const itineraryIndexMap = new Map()
  if (itinerary) {
    itinerary.forEach((item, index) => {
      itineraryIndexMap.set(item.id, index + 1)
    })
  }
  
  return (
    <>
      {validLocations.map((location, index) => {
        // Find the number for this location based on its linkedItineraryId
        const markerNumber = location.linkedItineraryId 
          ? itineraryIndexMap.get(location.linkedItineraryId) 
          : null
        
        console.log('Location:', location.name, 'linkedId:', location.linkedItineraryId, 'markerNumber:', markerNumber);
        
        // Create custom numbered icon
        const customIcon = markerNumber ? L.divIcon({
          html: `<div style="background-color: #2563eb; color: white; border-radius: 50%; width: 32px; height: 32px; line-height: 32px; text-align: center; font-weight: bold; font-size: 16px; border: 3px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">${markerNumber}</div>`,
          className: 'custom-numbered-marker',
          iconSize: [32, 32],
          iconAnchor: [16, 16],
          popupAnchor: [0, -16]
        }) : undefined
        
        return (
          <Marker 
            key={index} 
            position={[location.latitude, location.longitude]}
            {...(customIcon && { icon: customIcon })}
          >
            <Popup>
              {markerNumber && (
                <div className="font-bold text-blue-600 mb-1">#{markerNumber}</div>
              )}
              <div className="font-semibold">{location.name || 'Location'}</div>
            </Popup>
          </Marker>
        )
      })}
    </>
  )
}

function App() {
  console.log('App component rendering...')
  const [itinerary, setItinerary] = useState([])
  const [locations, setLocations] = useState([])
  const [prompt, setPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [error, setError] = useState(null)
  const [conversation, setConversation] = useState([]) // Array of {role: 'user'|'assistant', content: string, timestamp: Date}
  const [chatInput, setChatInput] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [options, setOptions] = useState([]) // Array of selectable options (flights, events, hotels)
  const [mounted, setMounted] = useState(false)
  const chatEndRef = useRef(null)
  
  // Check if component mounted
  useEffect(() => {
    console.log('App component mounted successfully')
    setMounted(true)
    return () => console.log('App component unmounting')
  }, [])

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
      
      // Only update itinerary if backend sends new items (preserve user selections)
      if (response.data.itinerary && response.data.itinerary.length > 0) {
        // Merge new items with existing ones, avoiding duplicates by ID
        setItinerary(prevItinerary => {
          const existingIds = new Set(prevItinerary.map(item => item.id))
          const newItems = response.data.itinerary.filter(item => !existingIds.has(item.id))
          return [...prevItinerary, ...newItems]
        })
      }
      
      // Update locations (merge with existing)
      if (response.data.locations && response.data.locations.length > 0) {
        setLocations(prevLocations => {
          const existingIds = new Set(prevLocations.map(loc => loc.linkedItineraryId))
          const newLocations = response.data.locations.filter(loc => !existingIds.has(loc.linkedItineraryId))
          return [...prevLocations, ...newLocations]
        })
      }
      
      const receivedOptions = response.data.options || []
      console.log('Received options from backend:', receivedOptions)
      setOptions(receivedOptions)
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
      
      // Update itinerary if provided - merge with existing items to preserve user selections
      if (response.data.itinerary && response.data.itinerary.length > 0) {
        setItinerary(prevItinerary => {
          const existingIds = new Set(prevItinerary.map(item => item.id))
          const newItems = response.data.itinerary.filter(item => !existingIds.has(item.id))
          return [...prevItinerary, ...newItems]
        })
      }
      // Update locations - merge with existing to preserve user selections
      if (response.data.locations && response.data.locations.length > 0) {
        setLocations(prevLocations => {
          const existingIds = new Set(prevLocations.map(loc => loc.linkedItineraryId))
          const newLocations = response.data.locations.filter(loc => !existingIds.has(loc.linkedItineraryId))
          return [...prevLocations, ...newLocations]
        })
      }
      if (response.data.options) {
        setOptions(response.data.options)
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
  
  // Debug options
  useEffect(() => {
    console.log('Current options state:', options)
  }, [options])
  
  // Check if last message needs clarification
  const needsClarification = conversation.length > 0 && 
    conversation[conversation.length - 1].status === 'needs_clarification'
  
  const handleSelectOption = (option) => {
    // Find the itinerary item to replace (if specified)
    if (option.replaces_itinerary_id) {
      const newItinerary = itinerary.map(item => {
        if (item.id === option.replaces_itinerary_id) {
          // Replace with the selected option
          return {
            ...item,
            title: option.title,
            description: option.description,
            details: option.data
          }
        }
        return item
      })
      setItinerary(newItinerary)
    } else {
      // Add as new itinerary item with unique ID
      const newItem = {
        id: option.option_id || `selected-${Date.now()}-${Math.random()}`,
        title: option.title,
        description: option.description,
        type: option.type === 'flight' ? 'travel' : option.type === 'event' ? 'activity' : 'lodging',
        startTime: option.data.startTime || option.data.start_date || option.data.departure_time || new Date().toISOString(),
        endTime: option.data.endTime || option.data.end_date || option.data.arrival_time || new Date().toISOString(),
        details: option.data
      }
      setItinerary(prev => [...prev, newItem])
      
      // Add location if available
      if (option.data.venue || option.data.arrival_airport) {
        const location = {
          name: option.data.venue?.name || option.data.arrival_airport?.name || option.title,
          latitude: option.data.venue?.latitude || option.data.arrival_airport?.latitude,
          longitude: option.data.venue?.longitude || option.data.arrival_airport?.longitude,
          linkedItineraryId: newItem.id
        }
        if (location.latitude && location.longitude) {
          setLocations(prev => [...prev, location])
        }
      }
    }
    
    // Remove the selected option from options list
    setOptions(options.filter(opt => opt.option_id !== option.option_id))
    setHasChanges(true)
  }

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

  // Extract trip context from itinerary
  const getTripContext = () => {
    if (!itinerary || itinerary.length === 0) return null
    
    const destinations = new Set()
    const dates = new Set()
    
    try {
      itinerary.forEach(item => {
        // Extract destinations from flights
        if (item && item.details && item.details.flight && item.details.flight.arrival_airport) {
          const dest = item.details.flight.arrival_airport
          if (typeof dest === 'object' && dest.code) {
            destinations.add(dest.code)
          } else if (typeof dest === 'string') {
            destinations.add(dest)
          }
        }
        
        // Extract dates
        if (item && item.startTime) {
          try {
            const dateStr = item.startTime.split('T')[0]
            dates.add(dateStr)
          } catch (e) {
            // ignore
          }
        }
      })
    } catch (e) {
      console.error('Error extracting trip context:', e)
      return null
    }
    
    if (destinations.size === 0 && dates.size === 0) return null
    
    return {
      destinations: Array.from(destinations),
      dates: Array.from(dates).sort()
    }
  }

  const tripContext = getTripContext()
  
  console.log('Rendering App with state:', { 
    itineraryLength: itinerary.length, 
    locationsLength: locations.length,
    conversationLength: conversation.length,
    optionsLength: options.length,
    isLoading,
    mounted
  })

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
              
              {/* Trip Context Display */}
              {tripContext && (
                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-start gap-2">
                    <span className="text-blue-600 text-sm">🧠</span>
                    <div className="flex-1">
                      <p className="text-xs font-semibold text-blue-900 mb-1">AI Memory - Current Trip Context:</p>
                      <div className="text-xs text-blue-800 space-y-1">
                        {tripContext.destinations.length > 0 && (
                          <p><span className="font-medium">Destination:</span> {tripContext.destinations.join(', ')}</p>
                        )}
                        {tripContext.dates.length > 0 && (
                          <p><span className="font-medium">Dates:</span> {tripContext.dates[0]} {tripContext.dates.length > 1 ? `to ${tripContext.dates[tripContext.dates.length - 1]}` : ''}</p>
                        )}
                      </div>
                    </div>
                  </div>
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
            
            {/* Options Section - Show FIRST */}
            {!isLoading && options.length > 0 && (
              <div className="mb-8">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                  ✈️ Select Your Travel Options
                </h2>
                <p className="text-sm text-gray-600 mb-4">
                  Choose from the flights and events below to build your perfect itinerary:
                </p>
                
                {/* Group options by type */}
                {options.some(opt => opt.type === 'flight') && (
                  <div className="mb-6">
                    <h3 className="text-lg font-semibold text-gray-800 mb-3">✈️ Available Flights</h3>
                    <div className="space-y-3">
                      {options.filter(opt => opt.type === 'flight').map((option) => {
                        // Debug: log the flight data structure
                        console.log('Flight option data:', option);
                        console.log('Title:', option.title);
                        console.log('Description:', option.description);
                        console.log('legs_out:', option.data.legs_out);
                        
                        // Extract times from legs_out with fallbacks
                        const legsOut = option.data.legs_out || [];
                        let departureTime = null;
                        let arrivalTime = null;
                        
                        if (legsOut.length > 0) {
                          departureTime = legsOut[0].departure_time || legsOut[0].departure || null;
                          arrivalTime = legsOut[legsOut.length - 1].arrival_time || legsOut[legsOut.length - 1].arrival || null;
                          console.log('From legs_out:', { departureTime, arrivalTime });
                        }
                        
                        // Filter out empty strings
                        if (departureTime && typeof departureTime === 'string' && !departureTime.trim()) {
                          departureTime = null;
                        }
                        if (arrivalTime && typeof arrivalTime === 'string' && !arrivalTime.trim()) {
                          arrivalTime = null;
                        }
                        
                        // Fallback to top-level fields if legs_out doesn't have times
                        if (!departureTime) {
                          departureTime = option.data.departure_time || option.data.departure_date || null;
                        }
                        if (!arrivalTime) {
                          arrivalTime = option.data.arrival_time || option.data.arrival_date || null;
                        }
                        
                        // Try to extract from description as last resort (format: "🕐 TIME → TIME")
                        if (!departureTime && option.description) {
                          const timeMatch = option.description.match(/🕐\s*([^→]+)/);
                          if (timeMatch) {
                            departureTime = timeMatch[1].trim();
                            console.log('Extracted departure from description:', departureTime);
                          }
                        }
                        if (!arrivalTime && option.description) {
                          const timeMatch = option.description.match(/→\s*([^|]+)/);
                          if (timeMatch) {
                            arrivalTime = timeMatch[1].trim();
                            console.log('Extracted arrival from description:', arrivalTime);
                          }
                        }
                        
                        console.log('Final extracted times:', { departureTime, arrivalTime });
                        
                        const departureAirport = legsOut.length > 0 ? legsOut[0].departure_airport : option.data.departure_airport;
                        const arrivalAirport = legsOut.length > 0 ? legsOut[legsOut.length - 1].arrival_airport : option.data.arrival_airport;
                        
                        return (
                        <div
                          key={option.option_id}
                          className="p-4 rounded-lg border-2 border-blue-200 bg-blue-50 hover:border-blue-400 hover:shadow-lg transition-all cursor-pointer"
                          onClick={() => handleSelectOption(option)}
                        >
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-xl">✈️</span>
                                <h3 className="font-bold text-lg text-blue-900">
                                  {departureAirport?.code || departureAirport} → {arrivalAirport?.code || arrivalAirport}
                                </h3>
                                {option.data.total_price && (
                                  <span className="px-3 py-1 text-sm rounded-full font-bold bg-green-100 text-green-800">
                                    ${option.data.total_price} {option.data.currency || 'USD'}
                                  </span>
                                )}
                              </div>
                              
                              {/* Title and Description - Always Show */}
                              {option.title && (
                                <div className="mb-2 text-sm font-medium text-blue-800">
                                  {option.title}
                                </div>
                              )}
                              
                              {option.description && (
                                <div className="mb-3 text-sm text-gray-700">
                                  {option.description}
                                </div>
                              )}
                              
                              {/* Departure Time - Prominent if available */}
                              {departureTime && departureTime.trim() && (
                                <div className="mb-3 p-3 bg-white rounded-md border border-blue-300">
                                  <div className="text-xs font-semibold text-blue-600 mb-1">DEPARTURE</div>
                                  <div className="text-lg font-bold text-blue-900">
                                    {formatTime(departureTime)}
                                  </div>
                                </div>
                              )}
                              
                              {/* Flight Details Grid - Always Show Available Info */}
                              <div className="grid grid-cols-2 gap-2 text-sm text-gray-700 mb-2">
                                {legsOut.length > 0 && legsOut[0].airline && (
                                  <p><span className="font-medium">Airline:</span> {legsOut[0].airline}</p>
                                )}
                                {legsOut.length > 0 && legsOut[0].flight_number && (
                                  <p><span className="font-medium">Flight:</span> {legsOut[0].flight_number}</p>
                                )}
                                {option.data.out_duration && (
                                  <p><span className="font-medium">Duration:</span> {Math.floor(option.data.out_duration / 60)}h {option.data.out_duration % 60}m</p>
                                )}
                                {arrivalTime && arrivalTime.trim() && (
                                  <p><span className="font-medium">🕐 Arrives:</span> {formatTime(arrivalTime)}</p>
                                )}
                                {legsOut.length > 0 && legsOut[0].departure_time && (
                                  <p><span className="font-medium">Departs:</span> {legsOut[0].departure_time}</p>
                                )}
                                {legsOut.length > 0 && legsOut[legsOut.length - 1].arrival_time && (
                                  <p><span className="font-medium">Arrives:</span> {legsOut[legsOut.length - 1].arrival_time}</p>
                                )}
                              </div>
                              
                              {/* Show all legs if multiple */}
                              {legsOut.length > 1 && (
                                <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-600">
                                  <p className="font-medium mb-1">{legsOut.length} flight segment(s):</p>
                                  {legsOut.map((leg, idx) => (
                                    <div key={idx} className="ml-2">
                                      {idx + 1}. {leg.departure_airport} → {leg.arrival_airport}
                                      {leg.departure_time && ` (${leg.departure_time})`}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                            
                            <button
                              className="ml-4 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors font-medium"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleSelectOption(option)
                              }}
                            >
                              Select Flight
                            </button>
                          </div>
                        </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                
                {/* Events Section */}
                {options.some(opt => opt.type === 'event') && (
                  <div className="mb-6">
                    <h3 className="text-lg font-semibold text-gray-800 mb-3">🎭 Available Events & Activities</h3>
                    <div className="space-y-3">
                      {options.filter(opt => opt.type === 'event').map((option) => (
                        <div
                          key={option.option_id}
                          className="p-4 rounded-lg border-2 border-purple-200 bg-purple-50 hover:border-purple-400 hover:shadow-lg transition-all cursor-pointer"
                          onClick={() => handleSelectOption(option)}
                        >
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-xl">🎭</span>
                                <h3 className="font-bold text-lg text-purple-900">{option.title}</h3>
                                {option.data.price_text && (
                                  <span className="px-3 py-1 text-sm rounded-full font-bold bg-green-100 text-green-800">
                                    {option.data.price_text}
                                  </span>
                                )}
                              </div>
                              
                              {option.data.description && (
                                <p className="text-sm text-gray-700 mb-2">{option.data.description}</p>
                              )}
                              
                              <div className="grid grid-cols-1 gap-1 text-sm text-gray-700">
                                {option.data.venue?.name && (
                                  <p><span className="font-medium">📍 Venue:</span> {option.data.venue.name}</p>
                                )}
                                {option.data.start_date && (
                                  <p><span className="font-medium">📅 Date:</span> {option.data.start_date} {option.data.start_time && `at ${option.data.start_time}`}</p>
                                )}
                                {option.data.venue?.address && (
                                  <p className="text-xs text-gray-600">{option.data.venue.address}</p>
                                )}
                              </div>
                            </div>
                            
                            <button
                              className="ml-4 px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 transition-colors font-medium"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleSelectOption(option)
                              }}
                            >
                              Select Event
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Hotels Section */}
                {options.some(opt => opt.type === 'hotel') && (
                  <div className="mb-6">
                    <h3 className="text-lg font-semibold text-gray-800 mb-3">🏨 Available Hotels</h3>
                    <div className="space-y-3">
                      {options.filter(opt => opt.type === 'hotel').map((option) => (
                        <div
                          key={option.option_id}
                          className="p-4 rounded-lg border-2 border-green-200 bg-green-50 hover:border-green-400 hover:shadow-lg transition-all cursor-pointer"
                          onClick={() => handleSelectOption(option)}
                        >
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-xl">🏨</span>
                                <h3 className="font-bold text-lg text-green-900">{option.title}</h3>
                                {option.data.price_per_night && (
                                  <span className="px-3 py-1 text-sm rounded-full font-bold bg-green-100 text-green-800">
                                    ${option.data.price_per_night}/night
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-gray-700 mb-2">{option.description}</p>
                            </div>
                            
                            <button
                              className="ml-4 px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition-colors font-medium"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleSelectOption(option)
                              }}
                            >
                              Select Hotel
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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
                          {/* Numbered badge matching map marker */}
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm border-2 border-white shadow-md">
                            {index + 1}
                          </div>
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

            {!isLoading && itinerary.length === 0 && options.length === 0 && (
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

// Wrap App with Error Boundary
function AppWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  )
}

export default AppWithErrorBoundary
