import request from './request'

// 管理端：全部带 Bearer token（request 拦截器自动加），后端 require_admin 兜底
export const listPendingAdventurers = params =>
  request.get('/admin/adventurers/pending', { params })
export const auditAdventurer = (id, target) =>
  request.put(`/admin/adventurers/${id}/audit`, { target })
// 经营看板：一次拉全部维度，days 控制趋势图天数
export const getStatsOverview = days =>
  request.get('/admin/stats/overview', { params: { days } })
