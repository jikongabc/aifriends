// axios 实例：请求自动带 access token；响应 401 时用 refresh_token 刷新并重发，刷新失败则登出。
import axios from "axios"
import {useUserStore} from "@/stores/user.js";
import CONFIG_API from "@/js/config/config.js";

const BASE_URL = CONFIG_API.HTTP_URL

const api = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,
})

api.interceptors.request.use(config => {
    const user = useUserStore()
    if (user.accessToken) {
        config.headers.Authorization = `Bearer ${user.accessToken}`
    }
    return config
})

let isRefreshing = false
let refreshSubscribers = []

// 登记一个回调，等待 token 刷新完成后被唤醒。
function subscribeTokenRefresh(callback) {
    refreshSubscribers.push(callback)
}

// 刷新成功：用新 token 唤醒所有挂起请求。
function onRefreshed(token) {
    refreshSubscribers.forEach(cb => cb(token))
    refreshSubscribers = []
}

// 刷新失败：通知所有挂起请求报错。
function onRefreshFailed(err) {
    refreshSubscribers.forEach(cb => cb(null, err))
    refreshSubscribers = []
}

api.interceptors.response.use(
    response => response,
    async error => {
        const user = useUserStore()
        const originalRequest = error?.config
        if (!originalRequest) {
            return Promise.reject(error)
        }

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true

            return new Promise((resolve, reject) => {
                subscribeTokenRefresh((token, error) => {
                    if (error) {
                        reject(error)
                    } else {
                        originalRequest.headers.Authorization = `Bearer ${token}`
                        resolve(api(originalRequest))
                    }
                })

                if (!isRefreshing) {
                    isRefreshing = true
                    axios.post(
                        `${BASE_URL}/api/user/account/refresh_token/`,
                        {},
                        {withCredentials: true, timeout: 5000}
                    ).then(res => {
                        user.setAccessToken(res.data.access)
                        onRefreshed(res.data.access)
                    }).catch(error => {
                        user.logout()
                        onRefreshFailed(error)
                        reject(error)
                    }).finally(() => {
                        isRefreshing = false
                    })
                }
            })
        }

        return Promise.reject(error)
    }
)

export default api
