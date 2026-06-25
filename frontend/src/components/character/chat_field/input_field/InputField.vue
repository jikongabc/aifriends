<script setup>
// 输入区：文本/语音发消息，SSE 流式接收文本与音频并用 MSE 边收边播，支持打断。
import SendIcon from "@/components/character/icons/SendIcon.vue";
import MicIcon from "@/components/character/icons/MicIcon.vue";
import {onUnmounted, ref, useTemplateRef} from "vue";
import streamApi from "@/js/http/streamApi.js";
import Microphone from "@/components/character/chat_field/input_field/Microphone.vue";

const props = defineProps(['friendId'])
const emit = defineEmits(['pushBackMessage', 'addToLastMessage'])
const inputRef = useTemplateRef('input-ref')
const message = ref('')
let processId = 0
const showMic = ref(false)
const lastMetrics = ref(null)   // 最近一轮延迟指标（ttft / ttfa / total）
let currentController = null     // 当前流的 AbortController，用于打断

// 打断当前对话：真正断开 SSE 连接（后端据此取消上游 LLM/TTS）+ 停止本地音频
function abortCurrent() {
  ++ processId
  if (currentController) {
    currentController.abort()
    currentController = null
  }
  stopAudio()
}

let mediaSource = null;
let sourceBuffer = null;
let audioPlayer = new Audio(); // 全局播放器实例
let audioQueue = [];           // 待写入 Buffer 的二进制队列
let isUpdating = false;        // Buffer 是否正在写入

// 初始化 MediaSource 流式播放器，准备接收音频分片。
const initAudioStream = () => {
    audioPlayer.pause();
    audioQueue = [];
    isUpdating = false;

    mediaSource = new MediaSource();
    audioPlayer.src = URL.createObjectURL(mediaSource);

    mediaSource.addEventListener('sourceopen', () => {
        try {
            sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
            sourceBuffer.addEventListener('updateend', () => {
                isUpdating = false;
                processQueue();
            });
        } catch (e) {
            console.error("MSE AddSourceBuffer Error:", e);
        }
    });

    audioPlayer.play().catch(e => console.error("等待用户交互以播放音频"));
};

// 把队列里的音频分片依次写入 SourceBuffer（串行，避免并发写入报错）。
const processQueue = () => {
    if (isUpdating || audioQueue.length === 0 || !sourceBuffer || sourceBuffer.updating) {
        return;
    }

    isUpdating = true;
    const chunk = audioQueue.shift();
    try {
        sourceBuffer.appendBuffer(chunk);
    } catch (e) {
        console.error("SourceBuffer Append Error:", e);
        isUpdating = false;
    }
};

// 停止播放并释放 MediaSource 资源。
const stopAudio = () => {
    audioPlayer.pause();
    audioQueue = [];
    isUpdating = false;

    if (mediaSource) {
        if (mediaSource.readyState === 'open') {
            try {
                mediaSource.endOfStream();
            } catch (e) {
            }
        }
        mediaSource = null;
    }

    if (audioPlayer.src) {
        URL.revokeObjectURL(audioPlayer.src);
        audioPlayer.src = '';
    }
};

const handleAudioChunk = (base64Data) => {  // 将语音片段添加到播放器队列中
    try {
        const binaryString = atob(base64Data);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        audioQueue.push(bytes);
        processQueue();
    } catch (e) {
        console.error("Base64 Decode Error:", e);
    }
};

onUnmounted(() => {
    audioPlayer.pause();
    audioPlayer.src = '';
});

// 聚焦输入框（暴露给父组件）。
function focus() {
  inputRef.value.focus()
}

// 发送消息：打断上一轮后开启新 SSE 流，分发文本/音频/延迟指标。
async function handleSend(event, audio_msg) {
  let content
  if (audio_msg) {
    content = audio_msg.trim()
  } else {
    content = message.value.trim()
  }
  if (!content) return

  // 发新消息即打断上一轮（barge-in）：中止旧流再开新流
  abortCurrent()
  initAudioStream()

  const curId = processId
  const controller = new AbortController()
  currentController = controller
  message.value = ''

  emit('pushBackMessage', {role: 'user', content: content, id: crypto.randomUUID()})
  emit('pushBackMessage', {role: 'ai', content: '', id: crypto.randomUUID()})

  try {
    await streamApi('/api/friend/message/chat/', {
      body: {
        friend_id: props.friendId,
        message: content,
      },
      signal: controller.signal,
      onmessage(data, isDone) {
        if (curId !== processId) return

        if (data.content) {
          emit('addToLastMessage', data.content)
        }
        if (data.audio) {
          handleAudioChunk(data.audio)
        }
        if (data.metrics) {
          lastMetrics.value = data.metrics
        }
      },
      onerror(err) {
      },
    })
  } catch (err) {
    // AbortError 为主动打断，忽略
  } finally {
    if (currentController === controller) currentController = null
  }
}

// 关闭输入区并打断当前对话（暴露给父组件）。
function close() {
  abortCurrent()
  showMic.value = false
}

// 手动停止当前对话。
function handleStop() {
  abortCurrent()
}

defineExpose({
  focus,
  close,
})
</script>

<template>
  <div
      v-if="lastMetrics && lastMetrics.ttfa_ms != null"
      class="absolute -top-7 left-2 text-xs text-white/60 bg-black/30 backdrop-blur-sm rounded-lg px-2 py-0.5"
  >
    首音频 {{ lastMetrics.ttfa_ms }}ms · 首字 {{ lastMetrics.ttft_ms }}ms
  </div>
  <form v-if="!showMic" @submit.prevent="handleSend" class="absolute bottom-4 left-2 h-12 w-86 flex items-center">
    <input
        ref="input-ref"
        v-model="message"
        class="input bg-black/30 backdrop-blur-sm text-white text-base w-full h-full rounded-2xl pr-20"
        type="text"
        placeholder="文本输入..."
    >
    <div @click="handleSend" class="absolute right-2 w-8 h-8 flex justify-center items-center cursor-pointer">
      <SendIcon />
    </div>
    <div @click="showMic = true" class="absolute right-10 w-8 h-8 flex justify-center items-center cursor-pointer">
      <MicIcon />
    </div>
  </form>
  <Microphone
      v-else
      @close="showMic = false"
      @send="handleSend"
      @stop="handleStop"
  />
</template>

<style scoped>

</style>