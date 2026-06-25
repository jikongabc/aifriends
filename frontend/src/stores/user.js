import {defineStore} from "pinia";
import {ref} from "vue";

// 全局用户状态：登录态、access token 与用户资料。
export const useUserStore = defineStore('user', () => {
    const id = ref(0)
    const username = ref('')
    const photo = ref('')
    const profile = ref('')
    const accessToken = ref('')
    const hasPulledUserInfo = ref(false)

    // 是否已登录（凭是否持有 access token 判断）。
    function isLogin() {
        return !!accessToken.value  // 必须带value!!!!!!!!!
    }

    // 写入 access token。
    function setAccessToken(token) {
        accessToken.value = token
    }

    // 批量写入用户资料。
    function setUserInfo(data) {
        id.value = data.user_id
        username.value = data.username
        photo.value = data.photo
        profile.value = data.profile
    }

    // 登出：清空内存中的用户状态。
    function logout() {
        id.value = 0
        username.value = ''
        photo.value = ''
        profile.value = ''
        accessToken.value = ''
    }

    // 标记是否已拉取过用户信息（用于路由守卫避免误跳登录页）。
    function setHasPulledUserInfo(newStatus) {
        hasPulledUserInfo.value = newStatus
    }

    return {
        id,
        username,
        photo,
        profile,
        accessToken,  // 千万不要忘了！！！！
        isLogin,
        setAccessToken,
        setUserInfo,
        logout,
        hasPulledUserInfo,
        setHasPulledUserInfo,
    }
})
