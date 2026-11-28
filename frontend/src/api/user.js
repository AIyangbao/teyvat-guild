import request from './request'

// 个人资料：身份全部来自 Bearer token，不传 user_id
export const getMyProfile = () => request.get('/users/me')
export const updateMyNickname = nickname =>
  request.put('/users/me', { nickname })

// FormData 不要手动设 Content-Type：浏览器会自动补 multipart boundary
export const uploadAvatar = rawFile => {
  const form = new FormData()
  form.append('file', rawFile)
  return request.post('/users/me/avatar', form)
}

export const updateMyAdventurer = data =>
  request.put('/users/adventurers/me', data)
