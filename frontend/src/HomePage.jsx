import React from 'react'
import { Link } from 'react-router-dom'

function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-[#483D8B] via-[#2d2654] to-[#19192F] flex items-center justify-center p-6 page-enter">
      <div className="max-w-4xl w-full">
        <div className="text-center space-y-8">
          {/* Hero Section */}
          <div className="space-y-4">
            <h1 className="text-6xl font-bold text-white tracking-tight animate-on-load animate-fade-in-up delay-100">
              Proactive Life Manager
            </h1>
            <p className="text-2xl text-purple-100 max-w-2xl mx-auto animate-on-load animate-fade-in-up delay-300">
              Your AI-powered assistant for planning and managing life activities
            </p>
          </div>

          {/* Features Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 py-8 animate-on-load animate-fade-in delay-500">
            <div className="bg-white/95 backdrop-blur-sm p-6 rounded-xl shadow-lg border border-purple-200/30 hover-lift">
              <div className="text-4xl mb-3">🤖</div>
              <h3 className="font-semibold text-lg text-gray-900 mb-2">AI-Powered Planning</h3>
              <p className="text-gray-600 text-sm">
                Autonomous goal decomposition and intelligent itinerary creation
              </p>
            </div>
            
            <div className="bg-white/95 backdrop-blur-sm p-6 rounded-xl shadow-lg border border-purple-200/30 hover-lift">
              <div className="text-4xl mb-3">🗺️</div>
              <h3 className="font-semibold text-lg text-gray-900 mb-2">Interactive Maps</h3>
              <p className="text-gray-600 text-sm">
                Visual representation of your planned locations with real-time updates
              </p>
            </div>
            
            <div className="bg-white/95 backdrop-blur-sm p-6 rounded-xl shadow-lg border border-purple-200/30 hover-lift">
              <div className="text-4xl mb-3">✏️</div>
              <h3 className="font-semibold text-lg text-gray-900 mb-2">Fully Editable</h3>
              <p className="text-gray-600 text-sm">
                Delete, reorder, and refine your plans with instant synchronization
              </p>
            </div>
          </div>

          {/* CTA Button */}
          <div className="pt-4 animate-on-load animate-fade-in-up delay-700">
            <Link
              to="/planner"
              className="inline-block px-8 py-4 bg-white text-[#483D8B] text-lg font-semibold rounded-xl hover-lift shadow-2xl"
            >
              Start Planning Your Life →
            </Link>
          </div>

          {/* Example Use Cases */}
          <div className="pt-8 space-y-3 animate-on-load animate-fade-in delay-800">
            <p className="text-sm text-purple-200 font-medium">Try asking for:</p>
            <div className="flex flex-wrap justify-center gap-2">
              <span className="px-4 py-2 bg-white/10 backdrop-blur-sm border border-purple-300/30 rounded-full text-sm text-purple-100">
                "Plan a cheap cultural weekend in Chicago"
              </span>
              <span className="px-4 py-2 bg-white/10 backdrop-blur-sm border border-purple-300/30 rounded-full text-sm text-purple-100">
                "Organize a business trip to New York"
              </span>
              <span className="px-4 py-2 bg-white/10 backdrop-blur-sm border border-purple-300/30 rounded-full text-sm text-purple-100">
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
