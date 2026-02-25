import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getJobs = (params) => api.get('/jobs', { params })
export const getJob = (id) => api.get(`/jobs/${id}`)
export const deleteJob = (id) => api.delete(`/jobs/${id}`)
export const getStats = () => api.get('/stats')
export const getStatus = () => api.get('/status')
export const startAutomation = (config) => api.post('/start', config)
export const stopAutomation = () => api.post('/stop')
export const getProfile = () => api.get('/profile')
export const updateProfile = (data) => api.post('/profile', data)
export const getResume = (id) => `/api/jobs/${id}/resume`

export function createWS() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const port = import.meta.env.DEV ? '8000' : window.location.port
  return new WebSocket(`${proto}//${host}:${port}/ws`)
}

export default api
