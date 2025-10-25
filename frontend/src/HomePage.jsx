import React from 'react'
import { Link } from 'react-router-dom'

function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-6">
      <div className="max-w-4xl w-full">
        <div className="text-center space-y-8">
          {/* Hero Section */}
          <div className="space-y-4">
            <h1 className="text-6xl font-bold text-gray-900 tracking-tight">
              Proactive Life Manager
            </h1>
            <p className="text-2xl text-gray-600 max-w-2xl mx-auto">
              Your AI-powered assistant for planning and managing life activities
            </p>
          </div>

          {/* Features Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 py-8">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
              <div className="text-4xl mb-3">🤖</div>
              <h3 className="font-semibold text-lg text-gray-900 mb-2">AI-Powered Planning</h3>
              <p className="text-gray-600 text-sm">
                Autonomous goal decomposition and intelligent itinerary creation
              </p>
            </div>
            
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
              <div className="text-4xl mb-3">🗺️</div>
              <h3 className="font-semibold text-lg text-gray-900 mb-2">Interactive Maps</h3>
              <p className="text-gray-600 text-sm">
                Visual representation of your planned locations with real-time updates
              </p>
            </div>
            
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
              <div className="text-4xl mb-3">✏️</div>
              <h3 className="font-semibold text-lg text-gray-900 mb-2">Fully Editable</h3>
              <p className="text-gray-600 text-sm">
                Delete, reorder, and refine your plans with instant synchronization
              </p>
            </div>
          </div>

          {/* CTA Button */}
          <div className="pt-4">
            <Link
              to="/planner"
              className="inline-block px-8 py-4 bg-blue-600 text-white text-lg font-semibold rounded-xl hover:bg-blue-700 transform hover:scale-105 transition-all shadow-lg hover:shadow-xl"
            >
              Start Planning Your Life →
            </Link>
          </div>

          {/* Example Use Cases */}
          <div className="pt-8 space-y-3">
            <p className="text-sm text-gray-500 font-medium">Try asking for:</p>
            <div className="flex flex-wrap justify-center gap-2">
              <span className="px-4 py-2 bg-white border border-gray-200 rounded-full text-sm text-gray-700">
                "Plan a cheap cultural weekend in Chicago"
              </span>
              <span className="px-4 py-2 bg-white border border-gray-200 rounded-full text-sm text-gray-700">
                "Organize a business trip to New York"
              </span>
              <span className="px-4 py-2 bg-white border border-gray-200 rounded-full text-sm text-gray-700">
                "Create a romantic getaway itinerary"
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default HomePage
