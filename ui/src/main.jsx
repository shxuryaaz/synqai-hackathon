import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Auth from './Auth.jsx'

createRoot(document.getElementById('root')).render(<StrictMode><Auth>{(auth) => <App auth={auth} />}</Auth></StrictMode>)
if ('serviceWorker' in navigator && import.meta.env.PROD) navigator.serviceWorker.register('/sw.js')
