import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// 所有请求都写成 /api/...，由 Vite proxy 转发到 FastAPI，避免组件里散落后端地址。
export const api = {
  // /health：页面右上角后端连通性检查。
  health: () => client.get('/health').then((res) => res.data),
  // /campus/locations：加载食堂、教学楼和步行时间基础数据。
  campusLocations: () => client.get('/campus/locations').then((res) => res.data),
  // /campus/occupancy：按实时、随机或手动来源生成校园到达人数。
  campusOccupancy: (payload) => client.post('/campus/occupancy', payload).then((res) => res.data),
  // /config/validate：把前端配置交给后端 Pydantic 和业务规则校验。
  validateConfig: (config) => client.post('/config/validate', config).then((res) => res.data),
  // /sim/run：一次性完整运行仿真，适合直接进入结果分析。
  runSimulation: (config) => client.post('/sim/run', config).then((res) => res.data),
  // /sim/step：实时仿真单步接口，每次推进一分钟并返回状态快照。
  stepSimulation: (payload) => client.post('/sim/step', payload).then((res) => res.data),
  // /run/{runId}/records：按运行编号读取已保存的分钟过程记录。
  getRecords: (runId) => client.get(`/run/${runId}/records`).then((res) => res.data),
  // /run/{runId}/metrics：按运行编号读取最终指标汇总。
  getMetrics: (runId) => client.get(`/run/${runId}/metrics`).then((res) => res.data),
  // /optimize/recommend：提交候选范围，后端枚举并返回推荐排序。
  recommend: (payload) => client.post('/optimize/recommend', payload).then((res) => res.data),
  // /explain：根据瓶颈和推荐结果生成本地规则化说明文本。
  explain: (payload) => client.post('/explain', payload).then((res) => res.data),
  // /export/{runId}：浏览器直接打开该 URL 下载 CSV 过程记录。
  exportUrl: (runId) => `/api/export/${runId}`
}
