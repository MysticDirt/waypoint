import React from 'react'
import { Routes, Route } from 'react-router-dom'
import HomePage from './HomePage'
import PlannerPage from './PlannerPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/planner" element={<PlannerPage />} />
    </Routes>
  )
}

export default App
