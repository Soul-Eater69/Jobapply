import { useState, useEffect } from 'react'
import { getProfile, updateProfile } from '../api.js'
import { Save, Plus, X, User, Briefcase, Code, GraduationCap, Key } from 'lucide-react'

const DEFAULT_CONFIG = {
  search_keywords: ['software engineer', 'backend developer'],
  locations: ['United States', 'Remote'],
  target_companies: [],
  blocked_companies: [],
  job_types: ['full-time'],
  max_applications_per_run: 20,
  max_applications_per_day: 50,
  sources: ['linkedin', 'indeed', 'glassdoor', 'dice', 'remotive'],
  check_interval_minutes: 30,
  min_ats_score: 60,
  auto_apply: true,
  remote_only: false,
  salary_min: null,
  experience_level: ['mid', 'senior'],
}

const ALL_SOURCES = ['linkedin', 'indeed', 'glassdoor', 'dice', 'remotive', 'weworkremotely', 'ziprecruiter', 'greenhouse']
const ALL_JOB_TYPES = ['full-time', 'part-time', 'contract', 'internship']
const ALL_EXP_LEVELS = ['entry', 'mid', 'senior', 'staff']

function TagInput({ label, value, onChange, placeholder }) {
  const [input, setInput] = useState('')
  const addTag = () => {
    const t = input.trim()
    if (t && !value.includes(t)) onChange([...value, t])
    setInput('')
  }
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {value.map((tag) => (
          <span key={tag} className="flex items-center gap-1 px-2 py-0.5 bg-blue-900/50 text-blue-300 text-xs rounded border border-blue-700/50">
            {tag}
            <button onClick={() => onChange(value.filter((t) => t !== tag))} className="hover:text-white">
              <X size={10} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
          placeholder={placeholder}
          className="flex-1 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
        />
        <button onClick={addTag} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm">
          <Plus size={14} />
        </button>
      </div>
    </div>
  )
}

function CheckboxGroup({ label, options, value, onChange }) {
  const toggle = (opt) => {
    if (value.includes(opt)) onChange(value.filter((v) => v !== opt))
    else onChange([...value, opt])
  }
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-2">{label}</label>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt}
            onClick={() => toggle(opt)}
            className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors capitalize ${
              value.includes(opt)
                ? 'bg-blue-600/30 text-blue-300 border-blue-600/50'
                : 'bg-gray-800 text-gray-500 border-gray-700 hover:border-gray-500'
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}

function Section({ icon: Icon, title, children }) {
  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-gray-800">
        <Icon size={16} className="text-blue-400" />
        <h2 className="text-sm font-semibold text-gray-200">{title}</h2>
      </div>
      {children}
    </div>
  )
}

export default function SettingsPage({ context }) {
  const [config, setConfig] = useState(DEFAULT_CONFIG)
  const [profile, setProfile] = useState({})
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')

  useEffect(() => {
    const saved = localStorage.getItem('jobapply_config')
    if (saved) setConfig({ ...DEFAULT_CONFIG, ...JSON.parse(saved) })
    getProfile().then((r) => setProfile(r.data || {})).catch(() => {})
  }, [])

  const saveConfig = () => {
    localStorage.setItem('jobapply_config', JSON.stringify(config))
    setSavedMsg('Automation config saved!')
    setTimeout(() => setSavedMsg(''), 3000)
  }

  const saveProfile = async () => {
    setSaving(true)
    try {
      await updateProfile(profile)
      setSavedMsg('Profile saved!')
      setTimeout(() => setSavedMsg(''), 3000)
    } catch {
      setSavedMsg('Error saving profile')
    }
    setSaving(false)
  }

  const setC = (key) => (val) => setConfig((c) => ({ ...c, [key]: val }))
  const setP = (key) => (e) => setProfile((p) => ({ ...p, [key]: e.target.value }))

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Settings</h1>
          <p className="text-sm text-gray-500">Configure automation and your profile</p>
        </div>
        {savedMsg && (
          <span className="text-sm text-emerald-400 bg-emerald-900/30 px-3 py-1.5 rounded-lg border border-emerald-700/50">
            {savedMsg}
          </span>
        )}
      </div>

      {/* ── Automation Config ── */}
      <Section icon={Briefcase} title="Automation Settings">
        <TagInput label="Search Keywords" value={config.search_keywords} onChange={setC('search_keywords')} placeholder="e.g. python developer" />
        <TagInput label="Locations" value={config.locations} onChange={setC('locations')} placeholder="e.g. New York, Remote" />
        <TagInput label="Target Companies (optional)" value={config.target_companies || []} onChange={setC('target_companies')} placeholder="e.g. Google, Meta" />
        <TagInput label="Blocked Companies" value={config.blocked_companies || []} onChange={setC('blocked_companies')} placeholder="e.g. Staffing Agency" />

        <div className="grid grid-cols-2 gap-4">
          <CheckboxGroup label="Job Sources" options={ALL_SOURCES} value={config.sources} onChange={setC('sources')} />
          <CheckboxGroup label="Job Types" options={ALL_JOB_TYPES} value={config.job_types || []} onChange={setC('job_types')} />
        </div>

        <CheckboxGroup label="Experience Levels" options={ALL_EXP_LEVELS} value={config.experience_level || []} onChange={setC('experience_level')} />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { key: 'max_applications_per_run', label: 'Max per Run', type: 'number' },
            { key: 'max_applications_per_day', label: 'Max per Day', type: 'number' },
            { key: 'check_interval_minutes', label: 'Check Interval (min)', type: 'number' },
            { key: 'min_ats_score', label: 'Min ATS Score (%)', type: 'number' },
          ].map(({ key, label, type }) => (
            <div key={key}>
              <label className="block text-xs text-gray-500 mb-1">{label}</label>
              <input
                type={type}
                value={config[key] || ''}
                onChange={(e) => setC(key)(type === 'number' ? Number(e.target.value) : e.target.value)}
                className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-blue-500"
              />
            </div>
          ))}
        </div>

        <div className="flex gap-6">
          {[
            { key: 'auto_apply', label: 'Auto Apply' },
            { key: 'remote_only', label: 'Remote Only' },
          ].map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config[key] || false}
                onChange={(e) => setC(key)(e.target.checked)}
                className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-0"
              />
              <span className="text-sm text-gray-300">{label}</span>
            </label>
          ))}
        </div>

        <button
          onClick={saveConfig}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={14} /> Save Automation Config
        </button>
      </Section>

      {/* ── Personal Profile ── */}
      <Section icon={User} title="Personal Profile">
        <div className="grid grid-cols-2 gap-4">
          {[
            { key: 'first_name', label: 'First Name' },
            { key: 'last_name', label: 'Last Name' },
            { key: 'email', label: 'Email' },
            { key: 'phone', label: 'Phone' },
            { key: 'current_role', label: 'Current Role / Title' },
            { key: 'years_experience', label: 'Years of Experience' },
            { key: 'linkedin_url', label: 'LinkedIn URL' },
            { key: 'github_url', label: 'GitHub URL' },
            { key: 'portfolio_url', label: 'Portfolio / Website' },
            { key: 'desired_salary', label: 'Desired Salary' },
          ].map(({ key, label }) => (
            <div key={key}>
              <label className="block text-xs text-gray-500 mb-1">{label}</label>
              <input
                value={profile[key] || ''}
                onChange={setP(key)}
                className="w-full px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-blue-500"
              />
            </div>
          ))}
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Professional Summary</label>
          <textarea
            rows={4}
            value={profile.summary || ''}
            onChange={setP('summary')}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-blue-500 resize-none"
            placeholder="Brief professional summary used as base for AI-generated resumes..."
          />
        </div>

        <button
          onClick={saveProfile}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          <Save size={14} /> {saving ? 'Saving...' : 'Save Profile'}
        </button>
      </Section>

      {/* ── API Keys ── */}
      <Section icon={Key} title="API Keys & Credentials">
        <p className="text-xs text-gray-500">
          Credentials are stored in your <code className="bg-gray-800 px-1.5 py-0.5 rounded text-gray-300">.env</code> file.
          Edit it directly to set credentials securely.
        </p>
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-xs font-mono space-y-1 text-gray-400">
          <div>ANTHROPIC_API_KEY=sk-ant-...</div>
          <div>LINKEDIN_EMAIL=your@email.com</div>
          <div>LINKEDIN_PASSWORD=yourpassword</div>
          <div>INDEED_EMAIL=your@email.com</div>
          <div>INDEED_PASSWORD=yourpassword</div>
          <div>PROXY_LIST=http://proxy1:port,http://proxy2:port</div>
          <div>HEADLESS=true</div>
        </div>
        <p className="text-xs text-yellow-500">
          ⚠ Set HEADLESS=false to see the browser automation in action for debugging.
        </p>
      </Section>
    </div>
  )
}
