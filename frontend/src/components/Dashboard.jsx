import { useState, useEffect } from 'react'
import { getStats, startAutomation, stopAutomation } from '../api.js'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { Play, Square, RefreshCw, TrendingUp, CheckCircle2, XCircle, Clock, Target, Zap } from 'lucide-react'
import clsx from 'clsx'

const STATUS_COLORS = {
  applied: '#10b981',
  failed: '#ef4444',
  pending: '#f59e0b',
  skipped: '#6b7280',
}

const PIE_COLORS = ['#10b981', '#ef4444', '#f59e0b', '#6b7280']

function StatCard({ icon: Icon, label, value, sub, color = 'blue' }) {
  const colors = {
    blue: 'text-blue-400 bg-blue-900/30 border-blue-800/50',
    green: 'text-emerald-400 bg-emerald-900/30 border-emerald-800/50',
    red: 'text-red-400 bg-red-900/30 border-red-800/50',
    yellow: 'text-yellow-400 bg-yellow-900/30 border-yellow-800/50',
    purple: 'text-purple-400 bg-purple-900/30 border-purple-800/50',
  }
  return (
    <div className={clsx('card p-4 border', colors[color])}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
          <p className="text-2xl font-bold mt-1">{value ?? '—'}</p>
          {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
        </div>
        <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center', colors[color])}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  )
}

function LogLine({ log }) {
  const colors = {
    info: 'text-blue-300',
    success: 'text-emerald-300',
    warning: 'text-yellow-300',
    error: 'text-red-300',
  }
  return (
    <div className="flex gap-2 text-xs font-mono py-0.5">
      <span className="text-gray-600 flex-shrink-0">{log.time}</span>
      <span className={colors[log.level] || 'text-gray-300'}>{log.message}</span>
    </div>
  )
}

export default function Dashboard({ context }) {
  const { liveStatus, setLiveStatus, logs, wsConnected } = context
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchStats = async () => {
    try {
      const res = await getStats()
      setStats(res.data)
    } catch {}
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 15000)
    return () => clearInterval(interval)
  }, [])

  const handleStart = async () => {
    const config = JSON.parse(localStorage.getItem('jobapply_config') || '{}')
    if (!config.search_keywords?.length) {
      alert('Please configure your job search settings first (Settings tab)')
      return
    }
    setLoading(true)
    try {
      await startAutomation(config)
      setLiveStatus((p) => ({ ...p, running: true }))
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to start')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    try {
      await stopAutomation()
      setLiveStatus((p) => ({ ...p, running: false, current_action: 'idle' }))
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to stop')
    }
  }

  const pieData = stats?.by_status?.map((s) => ({
    name: s.status.charAt(0).toUpperCase() + s.status.slice(1),
    value: s.count,
  })) || []

  const sourceData = stats?.by_source?.map((s) => ({
    name: s.source.charAt(0).toUpperCase() + s.source.slice(1),
    count: s.count,
  })) || []

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-500">Real-time job automation control center</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchStats}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-colors"
            title="Refresh stats"
          >
            <RefreshCw size={16} />
          </button>
          {liveStatus.running ? (
            <button
              onClick={handleStop}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors"
            >
              <Square size={14} />
              Stop
            </button>
          ) : (
            <button
              onClick={handleStart}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors disabled:opacity-50"
            >
              <Play size={14} />
              {loading ? 'Starting...' : 'Start Automation'}
            </button>
          )}
        </div>
      </div>

      {/* Live status bar */}
      {liveStatus.running && (
        <div className="card border border-blue-700/50 bg-blue-900/20 px-4 py-3 flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse flex-shrink-0" />
          <span className="text-sm text-blue-300">{liveStatus.current_action}</span>
          <div className="ml-auto flex items-center gap-4 text-xs text-gray-400">
            <span>Found: <strong className="text-white">{liveStatus.jobs_found}</strong></span>
            <span>Applied: <strong className="text-emerald-400">{liveStatus.jobs_applied}</strong></span>
            <span>Failed: <strong className="text-red-400">{liveStatus.jobs_failed}</strong></span>
            {liveStatus.queue_size > 0 && (
              <span>Queue: <strong className="text-yellow-400">{liveStatus.queue_size}</strong></span>
            )}
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard icon={Target} label="Total Found" value={stats?.total} color="blue" />
        <StatCard icon={CheckCircle2} label="Applied" value={stats?.applied} sub={`Today: ${stats?.today ?? 0}`} color="green" />
        <StatCard icon={XCircle} label="Failed" value={stats?.failed} color="red" />
        <StatCard icon={Clock} label="Pending" value={stats?.pending} color="yellow" />
        <StatCard icon={TrendingUp} label="Avg ATS Score" value={stats?.avg_ats_score ? `${stats.avg_ats_score}%` : null} sub={`This week: ${stats?.this_week ?? 0}`} color="purple" />
      </div>

      {/* Charts + Logs */}
      <div className="grid grid-cols-12 gap-4">
        {/* Pie chart */}
        <div className="col-span-12 lg:col-span-4 card p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Status Distribution</h2>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
                  {pieData.map((entry, idx) => (
                    <Cell key={idx} fill={STATUS_COLORS[entry.name.toLowerCase()] || PIE_COLORS[idx % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }} />
                <Legend iconType="circle" iconSize={8} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-gray-600 text-sm">No data yet</div>
          )}
        </div>

        {/* Bar chart — by source */}
        <div className="col-span-12 lg:col-span-4 card p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Jobs by Source</h2>
          {sourceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={sourceData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 10 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }} />
                <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-gray-600 text-sm">No data yet</div>
          )}
        </div>

        {/* Top companies */}
        <div className="col-span-12 lg:col-span-4 card p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Top Companies</h2>
          <div className="space-y-2">
            {(stats?.top_companies || []).slice(0, 8).map((c, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-300 truncate max-w-[150px]">{c.company}</span>
                <span className="text-gray-500 text-xs">{c.count} job{c.count !== 1 ? 's' : ''}</span>
              </div>
            ))}
            {!stats?.top_companies?.length && (
              <p className="text-gray-600 text-sm text-center pt-8">No data yet</p>
            )}
          </div>
        </div>
      </div>

      {/* Live Activity Log */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-300">Live Activity Log</h2>
          <span className="text-xs text-gray-600">{logs.length} entries</span>
        </div>
        <div className="bg-gray-950 rounded-lg p-3 h-48 overflow-y-auto space-y-0.5">
          {logs.length > 0 ? (
            logs.map((log, i) => <LogLine key={i} log={log} />)
          ) : (
            <p className="text-gray-600 text-xs font-mono text-center pt-16">
              Waiting for automation to start...
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
