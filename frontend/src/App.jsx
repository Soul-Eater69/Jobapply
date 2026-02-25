import { useState, useEffect, useCallback, useRef } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Briefcase, Settings, Zap, Activity } from 'lucide-react'
import Dashboard from './components/Dashboard.jsx'
import JobsTable from './components/JobsTable.jsx'
import SettingsPage from './components/Settings.jsx'
import { createWS } from './api.js'
import clsx from 'clsx'

function NavItem({ to, icon: Icon, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
          isActive
            ? 'bg-blue-600/20 text-blue-400 border border-blue-600/30'
            : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
        )
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  )
}

export default function App() {
  const [wsState, setWsState] = useState({ connected: false })
  const [liveStatus, setLiveStatus] = useState({
    running: false,
    jobs_found: 0,
    jobs_applied: 0,
    jobs_failed: 0,
    current_action: 'idle',
    queue_size: 0,
  })
  const [logs, setLogs] = useState([])
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  const connectWS = useCallback(() => {
    try {
      const ws = createWS()
      wsRef.current = ws

      ws.onopen = () => setWsState({ connected: true })
      ws.onclose = () => {
        setWsState({ connected: false })
        reconnectTimer.current = setTimeout(connectWS, 3000)
      }
      ws.onerror = () => ws.close()

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'status') {
            setLiveStatus((prev) => ({ ...prev, ...msg.data }))
          } else if (msg.type === 'log') {
            setLogs((prev) => [
              { ...msg.data, time: new Date().toLocaleTimeString() },
              ...prev.slice(0, 199),
            ])
          } else if (msg.type === 'applied') {
            setLiveStatus((prev) => ({
              ...prev,
              jobs_applied: prev.jobs_applied + 1,
            }))
          } else if (msg.type === 'queue_stats') {
            setLiveStatus((prev) => ({ ...prev, queue_size: msg.data.queue_size || 0 }))
          } else if (msg.type === 'stopped') {
            setLiveStatus((prev) => ({ ...prev, running: false, current_action: 'idle' }))
          }
        } catch {}
      }
    } catch {
      reconnectTimer.current = setTimeout(connectWS, 3000)
    }
  }, [])

  useEffect(() => {
    connectWS()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connectWS])

  const context = { liveStatus, setLiveStatus, logs, wsConnected: wsState.connected }

  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-gray-950">
        {/* Sidebar */}
        <aside className="w-56 flex-shrink-0 border-r border-gray-800 flex flex-col">
          {/* Logo */}
          <div className="px-4 py-5 border-b border-gray-800">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
                JA
              </div>
              <div>
                <div className="text-sm font-semibold text-white">JobApply AI</div>
                <div className="text-xs text-gray-500">Automation Platform</div>
              </div>
            </div>
          </div>

          {/* Live status pill */}
          <div className="px-4 pt-3 pb-2">
            <div className={clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border',
              liveStatus.running
                ? 'bg-emerald-900/40 text-emerald-400 border-emerald-700/50'
                : 'bg-gray-800 text-gray-500 border-gray-700'
            )}>
              <span className={clsx(
                'w-1.5 h-1.5 rounded-full',
                liveStatus.running ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600'
              )} />
              {liveStatus.running ? 'Running' : 'Stopped'}
            </div>
          </div>

          {/* Nav */}
          <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
            <NavItem to="/" icon={LayoutDashboard} label="Dashboard" />
            <NavItem to="/jobs" icon={Briefcase} label="Applications" />
            <NavItem to="/settings" icon={Settings} label="Settings" />
          </nav>

          {/* WS indicator */}
          <div className="px-4 py-3 border-t border-gray-800">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Activity size={12} className={wsState.connected ? 'text-emerald-400' : 'text-red-400'} />
              {wsState.connected ? 'Live connected' : 'Reconnecting...'}
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard context={context} />} />
            <Route path="/jobs" element={<JobsTable />} />
            <Route path="/settings" element={<SettingsPage context={context} />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
