import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './LandingPage'
import PlannerApp from './PlannerApp'

function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/app" element={<PlannerApp />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default AppRouter
