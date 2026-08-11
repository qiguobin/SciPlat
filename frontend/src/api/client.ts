import axios from 'axios'
import { notifyOperation } from '../utils/notify'

export const api = axios.create({ baseURL: '/api' })

// 操作记录：所有写操作成功后自动生成系统通知
api.interceptors.response.use(
  (response) => {
    const { method, url } = response.config
    if (method && url) {
      notifyOperation(method, url)
    }
    return response
  },
  (error) => Promise.reject(error),
)
