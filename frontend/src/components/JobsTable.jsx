import { useState, useEffect } from 'react'
import { getJobs, deleteJob, getResume } from '../api.js'
import { Search, ExternalLink, Trash2, FileText, ChevronLeft, ChevronRight, Filter } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

const STATUS_BADGES = {
  applied: 'badge-applied',
  failed: 'badge-failed',
  pending: 'badge-pending',
  skipped: 'badge-skipped',
}

const SOURCE_ICONS = {
  linkedin: '🔵',
  indeed: '🟦',
  glassdoor: '🟩',
  dice: '🎲',
  remotive: '🌐',
  weworkremotely: '🏠',
  ziprecruiter: '⚡',
  greenhouse: '🌱',
}

function Badge({ text, className }) {
  return (
    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', className)}>
      {text}
    </span>
  )
}

function ATSBar({ score }) {
  if (!score) return <span className="text-gray-600 text-xs">—</span>
  const color = score >= 80 ? 'bg-emerald-500' : score >= 60 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-gray-400">{score.toFixed(0)}%</span>
    </div>
  )
}

export default function JobsTable() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [page, setPage] = useState(0)
  const [selectedJob, setSelectedJob] = useState(null)
  const PAGE_SIZE = 25

  const fetchJobs = async () => {
    setLoading(true)
    try {
      const res = await getJobs({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        status: statusFilter || undefined,
        source: sourceFilter || undefined,
        search: search || undefined,
      })
      setJobs(res.data)
    } catch {}
    setLoading(false)
  }

  useEffect(() => {
    fetchJobs()
  }, [page, statusFilter, sourceFilter, search])

  const handleDelete = async (id, e) => {
    e.stopPropagation()
    if (!confirm('Delete this record?')) return
    await deleteJob(id)
    setJobs((j) => j.filter((x) => x.id !== id))
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Applications</h1>
          <p className="text-sm text-gray-500">All job applications tracked by the bot</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0) }}
            placeholder="Search jobs..."
            className="pl-9 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 w-56"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(0) }}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 focus:outline-none focus:border-blue-500"
        >
          <option value="">All Status</option>
          <option value="applied">Applied</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
          <option value="skipped">Skipped</option>
        </select>

        <select
          value={sourceFilter}
          onChange={(e) => { setSourceFilter(e.target.value); setPage(0) }}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-300 focus:outline-none focus:border-blue-500"
        >
          <option value="">All Sources</option>
          <option value="linkedin">LinkedIn</option>
          <option value="indeed">Indeed</option>
          <option value="glassdoor">Glassdoor</option>
          <option value="dice">Dice</option>
          <option value="remotive">Remotive</option>
          <option value="weworkremotely">WeWorkRemotely</option>
          <option value="ziprecruiter">ZipRecruiter</option>
          <option value="greenhouse">Greenhouse</option>
        </select>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/50">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Job</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Company</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Source</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">ATS</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">When</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {loading ? (
                <tr>
                  <td colSpan={7} className="text-center py-16 text-gray-600">Loading...</td>
                </tr>
              ) : jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-16 text-gray-600">
                    No applications found. Start the automation to begin applying!
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="hover:bg-gray-800/30 cursor-pointer transition-colors"
                    onClick={() => setSelectedJob(job)}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-200 max-w-[220px] truncate">{job.title}</div>
                      {job.location && (
                        <div className="text-xs text-gray-500 mt-0.5">{job.location}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-gray-300 max-w-[150px] truncate block">{job.company}</span>
                      {job.remote && (
                        <span className="text-xs text-blue-400">Remote</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-gray-400 text-xs">
                        {SOURCE_ICONS[job.source] || '?'} {job.source}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        text={job.status}
                        className={STATUS_BADGES[job.status] || 'bg-gray-800 text-gray-400'}
                      />
                      {job.failure_reason && (
                        <div className="text-xs text-red-400 mt-1 max-w-[160px] truncate" title={job.failure_reason}>
                          {job.failure_reason}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <ATSBar score={job.ats_score} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {job.applied_at || job.scraped_at
                        ? formatDistanceToNow(new Date(job.applied_at || job.scraped_at), { addSuffix: true })
                        : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <a
                          href={job.job_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-gray-500 hover:text-blue-400 transition-colors"
                          title="View job"
                        >
                          <ExternalLink size={14} />
                        </a>
                        {job.resume_path && (
                          <a
                            href={getResume(job.id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-gray-500 hover:text-emerald-400 transition-colors"
                            title="Download resume"
                          >
                            <FileText size={14} />
                          </a>
                        )}
                        <button
                          onClick={(e) => handleDelete(job.id, e)}
                          className="text-gray-500 hover:text-red-400 transition-colors"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
          <span className="text-xs text-gray-500">
            Page {page + 1} · Showing {jobs.length} records
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1.5 rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={jobs.length < PAGE_SIZE}
              className="p-1.5 rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Job detail modal */}
      {selectedJob && (
        <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />
      )}
    </div>
  )
}

function JobDetailModal({ job, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="card w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-white">{job.title}</h2>
            <p className="text-gray-400">{job.company} · {job.location}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl leading-none">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Source</span>
            <div className="text-gray-200 mt-1">{SOURCE_ICONS[job.source]} {job.source}</div>
          </div>
          <div>
            <span className="text-gray-500">Status</span>
            <div className="mt-1">
              <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium', STATUS_BADGES[job.status])}>
                {job.status}
              </span>
            </div>
          </div>
          <div>
            <span className="text-gray-500">ATS Score</span>
            <div className="mt-1"><ATSBar score={job.ats_score} /></div>
          </div>
          <div>
            <span className="text-gray-500">Salary</span>
            <div className="text-gray-200 mt-1">{job.salary || '—'}</div>
          </div>
        </div>

        {job.failure_reason && (
          <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-3 text-sm text-red-300">
            <strong>Failure reason:</strong> {job.failure_reason}
          </div>
        )}

        {job.matched_skills?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2">Matched Skills</p>
            <div className="flex flex-wrap gap-1.5">
              {job.matched_skills.map((s) => (
                <span key={s} className="px-2 py-0.5 bg-emerald-900/40 text-emerald-300 text-xs rounded border border-emerald-700/50">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {job.description && (
          <div>
            <p className="text-xs text-gray-500 mb-2">Job Description</p>
            <p className="text-sm text-gray-400 whitespace-pre-wrap max-h-48 overflow-y-auto">{job.description.slice(0, 1500)}</p>
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <a href={job.job_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors">
            <ExternalLink size={14} /> View Job
          </a>
          {job.resume_path && (
            <a href={getResume(job.id)} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition-colors">
              <FileText size={14} /> Download Resume
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

function ATSBar({ score }) {
  if (!score) return <span className="text-gray-600 text-xs">—</span>
  const color = score >= 80 ? 'bg-emerald-500' : score >= 60 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-gray-400">{score.toFixed(0)}%</span>
    </div>
  )
}
