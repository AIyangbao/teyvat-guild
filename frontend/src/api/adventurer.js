import request from './request'

// 公开读侧：名录、档案、评价分页，全部免登录
export const listAdventurers = params => request.get('/adventurers', { params })
export const getAdventurer = id => request.get(`/adventurers/${id}`)
export const listAdventurerReviews = (id, params) =>
  request.get(`/adventurers/${id}/reviews`, { params })
