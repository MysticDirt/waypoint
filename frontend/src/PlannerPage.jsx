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

function PlannerPage() {
  const [itinerary, setItinerary] = useState([])
  const [locations, setLocations] = useState([])
  const [prompt, setPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!prompt.trim()) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await axios.post('http://127.0.0.1:8000/plan', { prompt })
      setItinerary(response.data.itinerary || [])
      setLocations(response.data.locations || [])
      setHasChanges(false)
    } catch (err) {
      console.error('Error planning:', err)
      setError('Failed to create plan. Please try again.')
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
    
    try {
      const response = await axios.post('http://127.0.0.1:8000/refine', {
        itinerary,
        locations
      })
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
    <div className="min-h-screen bg-gradient-to-br from-[#483D8B] via-[#2d2654] to-[#19192F] page-enter">
      <div className="grid grid-cols-1 md:grid-cols-2 h-screen">
        {/* Left Column - Itinerary */}
        <div className="flex flex-col h-full overflow-hidden">
          <div className="bg-white/95 backdrop-blur-sm shadow-lg border-b border-purple-200/30">
            <div className="p-6">
              <h1 className="text-3xl font-bold text-[#483D8B] mb-6">
                Proactive Life Manager
              </h1>
              
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Enter your goal (e.g., 'Plan a cheap cultural weekend in Chicago')"
                    className="flex-1 px-4 py-2 border border-purple-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#483D8B]"
                    disabled={isLoading}
                  />
                  <button
                    type="submit"
                    disabled={isLoading || !prompt.trim()}
                    className="px-6 py-2 bg-[#483D8B] text-white rounded-lg hover:bg-[#5a4da3] disabled:bg-gray-400 disabled:cursor-not-allowed hover-lift"
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
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 bg-gradient-to-b from-white/90 to-purple-50/90 backdrop-blur-sm">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <div className="text-center">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[#483D8B]"></div>
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
                      className="px-4 py-2 bg-[#483D8B] text-white rounded-lg hover:bg-[#5a4da3] hover-lift"
                    >
                      Yes, update plan
                    </button>
                  )}
                </div>

                {itinerary.map((item, index) => (
                  <div
                    key={item.id}
                    className={`p-4 rounded-lg border-2 ${getTypeColor(item.type)} hover-lift`}
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
        <div className="h-full bg-purple-900/20 relative">
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

export default PlannerPage
