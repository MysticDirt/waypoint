import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './Router.jsx'
import './index.css'
import 'leaflet/dist/leaflet.css'

console.log('main.jsx loading...')
const rootElement = document.getElementById('root')
console.log('Root element:', rootElement)

if (!rootElement) {
  console.error('Root element not found!')
} else {
  console.log('Creating React root...')
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <AppRouter />
    </React.StrictMode>,
  )
  console.log('React app rendered')
}
