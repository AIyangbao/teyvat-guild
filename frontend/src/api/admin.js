import request from './request'

// 管理端：全部带 Bearer token（request 拦截器自动加），后端 require_admin 兜底
export const listPendingAdventurers = params =>
  request.get('/admin/adventurers/pending', { params })
export const auditAdventurer = (id, target) =>
  request.put(`/admin/adventurers/${id}/audit`, { target })
