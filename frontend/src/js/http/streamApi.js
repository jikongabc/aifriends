// 流式请求工具：自动带 access token，401 时静默刷新后重试原请求。
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useUserStore } from "@/stores/user.js";
import api from "./api.js";
import CONFIG_API from "@/js/config/config.js";

const BASE_URL = CONFIG_API.HTTP_URL

// 发起一次 SSE 流式请求；options 含 method/body/signal/onmessage/onerror/onclose。
export default async function streamApi(url, options = {}) {
    const userStore = useUserStore();

    const startFetch = async () => {
        return await fetchEventSource(BASE_URL + url, {
            method: options.method || 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${userStore.accessToken}`,
                ...options.headers,
            },
            body: JSON.stringify(options.body || {}),

            // 打断（barge-in）：调用方传入 AbortController.signal，
            // abort 时立即断开 SSE 连接，后端据此取消上游 LLM/TTS。
            signal: options.signal,

            openWhenHidden: true,  // 允许后台运行，防止浏览器因隐藏页面而强制关闭它
            async onopen(response) {
                // 1. 处理 401 Token 过期
                if (response.status === 401) {
                    try {
                        // 触发 api.js 中的 Axios 拦截器进行静默刷新
                        await api.post('/api/user/account/refresh_token/', {});
                        // 抛出特定错误触发下面的 onerror 重试逻辑
                        throw new Error("TOKEN_REFRESHED");
                    } catch (err) {
                        // 如果刷新失败（refresh_token也过期），直接报错由上层处理
                        throw err;
                    }
                }

                if (!response.ok || !response.headers.get('content-type')?.includes('text/event-stream')) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `请求失败: ${response.status}`);
                }
            },

            onmessage(msg) {
                if (msg.data === '[DONE]') {
                    if (options.onmessage) options.onmessage('', true);
                    return
                }
                try {
                    const json = JSON.parse(msg.data);
                    if (options.onmessage) options.onmessage(json, false);
                } catch (e) {
                    console.error("流解析失败:", e);
                }
            },

            onerror(err) {
                // 2. 捕获重试信号并递归
                if (err.message === "TOKEN_REFRESHED") {
                    return startFetch();
                }

                // 主动打断导致的 abort 不算错误，静默结束即可
                if (err?.name === 'AbortError') {
                    throw err;
                }

                // 其他错误则按用户定义的 onerror 处理
                if (options.onerror) {
                    options.onerror(err);
                }
                throw err; // 停止自动重试
            },

            onclose: options.onclose,
        });
    };

    return await startFetch();
}
