import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000
})

export const api = {
  health: () => client.get('/health').then((res) => res.data),
  campusLocations: () => client.get('/campus/locations').then((res) => res.data),
  campusOccupancy: (payload) => client.post('/campus/occupancy', payload).then((res) => res.data),
  validateConfig: (config) => client.post('/config/validate', config).then((res) => res.data),
  runSimulation: (config) => client.post('/sim/run', config).then((res) => res.data),
  stepSimulation: (payload) => client.post('/sim/step', payload).then((res) => res.data),
  getRecords: (runId) => client.get(`/run/${runId}/records`).then((res) => res.data),
  getMetrics: (runId) => client.get(`/run/${runId}/metrics`).then((res) => res.data),
  recommend: (payload) => client.post('/optimize/recommend', payload).then((res) => res.data),
  explain: (payload) => client.post('/explain', payload).then((res) => res.data),
  exportUrl: (runId) => `/api/export/${runId}`
}
