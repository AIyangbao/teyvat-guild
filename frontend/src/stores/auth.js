import { reactive } from 'vue'

// 组合式 store：项目规模小，不引 pinia；规模上来再迁移
export const auth = reactive({
  token: localStorage.getItem('token') || '',
  user: JSON.parse(localStorage.getItem('user') || 'null'),

  setLogin(data) {   // data: TokenOut {access_token, user_id, role, nickname}
    this.token = data.access_token
    this.user = { id: data.user_id, role: data.role, nickname: data.nickname }
    localStorage.setItem('token', this.token)
    localStorage.setItem('user', JSON.stringify(this.user))
  },

  logout() {
    this.token = ''
    this.user = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  },
})
