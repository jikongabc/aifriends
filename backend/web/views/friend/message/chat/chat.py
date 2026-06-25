import asyncio
import base64
import json
import logging
import os
import threading
import uuid
from queue import Queue
from time import perf_counter

import websockets
from websockets.exceptions import ConnectionClosed
from django.db import connection as db_connection
from django.http import StreamingHttpResponse
from langchain_core.messages import HumanMessage, BaseMessageChunk, AIMessage
from rest_framework.renderers import BaseRenderer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.friend import Friend, Message
from web.views.friend.message.chat.graph import get_app
from web.views.friend.message.memory.update import update_memory


# 延迟埋点专用 logger：只写结构化 JSON 行，落 logs/latency.jsonl（保持纯 JSONL）。
latency_logger = logging.getLogger('aifriends.latency')
# 错误/异常用普通 logger，避免 traceback 污染 latency.jsonl。
logger = logging.getLogger(__name__)

# 长期记忆每隔多少轮对话更新一次（旧实现是 count() % 1 == 0，恒为 True，
# 等于每条消息都同步调一次 LLM 更新记忆，阻塞响应又烧 token）。
MEMORY_UPDATE_EVERY = 6


# 流式剥离 <thinking>...</thinking>：模型有时把思考过程当正文吐出，
# 既不该显示也不该送进 TTS。逐块喂入，跨块的半截标签会被缓冲到下次。
class ThinkingFilter:
    OPEN = '<thinking>'
    CLOSE = '</thinking>'

    def __init__(self):
        self.buf = ''
        self.in_think = False

    # 求 s 的最长后缀，使其同时是 tag 的前缀（用于判断半截标签要不要留到下次）。
    @staticmethod
    def _tail(s, tag):
        for k in range(min(len(s), len(tag) - 1), 0, -1):
            if s[-k:] == tag[:k]:
                return k
        return 0

    # 喂入一段增量，返回可安全输出的文本（thinking 区间内的内容被丢弃）。
    def feed(self, text):
        self.buf += text
        out = ''
        while True:
            if not self.in_think:
                i = self.buf.find(self.OPEN)
                if i == -1:
                    keep = self._tail(self.buf, self.OPEN)
                    out += self.buf[:len(self.buf) - keep]
                    self.buf = self.buf[len(self.buf) - keep:]
                    return out
                out += self.buf[:i]
                self.buf = self.buf[i + len(self.OPEN):]
                self.in_think = True
            else:
                j = self.buf.find(self.CLOSE)
                if j == -1:
                    keep = self._tail(self.buf, self.CLOSE)
                    self.buf = self.buf[len(self.buf) - keep:]
                    return out
                self.buf = self.buf[j + len(self.CLOSE):]
                self.in_think = False

    # 流结束时输出残留（仅当不在 thinking 区间内）。
    def flush(self):
        if self.in_think:
            return ''
        out, self.buf = self.buf, ''
        return out


# DRF 渲染器：让 SSE 字节流原样透传，不做 JSON 序列化。
class SSERenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'txt'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


# 构造本轮 graph 输入；历史由 checkpointer 按 thread_id 管理，无需手动拼接。
def build_inputs(app, config, friend, message):
    new_messages = []
    state = app.get_state(config)
    # 进程内无会话状态时（冷启动 / 换 worker），从 DB 回灌最近 10 轮，避免上下文丢失。
    if not (state.values and state.values.get('messages')):
        history = list(Message.objects.filter(friend=friend).order_by('-id')[:10])
        history.reverse()
        for m in history:
            new_messages.append(HumanMessage(m.user_message))
            new_messages.append(AIMessage(m.output))
    new_messages.append(HumanMessage(message))
    return {'messages': new_messages}


# 实时语音对话主入口：校验后以 SSE 流式返回文本 + 音频 + 延迟指标。
class MessageChatView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [SSERenderer]

    # 校验消息/好友/音色，启动 SSE 流式响应。
    def post(self, request):
        friend_id = request.data['friend_id']
        message = request.data['message'].strip()
        if not message:
            return Response({
                'result': '消息不能为空'
            })
        friends = Friend.objects.filter(pk=friend_id, me__user=request.user)
        if not friends.exists():
            return Response({
                'result': '好友不存在'
            })
        friend = friends.first()
        # voice 外键允许为空，但 TTS 必须有 voice_id；缺失时快速失败，
        # 否则后续在生成器里链式访问 .voice.voice_id 会抛 AttributeError。
        if not (friend.character.voice and friend.character.voice.voice_id):
            return Response({
                'result': '该角色还没有设置音色'
            })
        app = get_app()

        config = {'configurable': {'thread_id': str(friend.id), 'friend_id': friend.id}}
        inputs = build_inputs(app, config, friend, message)

        response = StreamingHttpResponse(
            self.event_stream(app, inputs, config, friend, message),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


    # 把一段文本送进 TTS websocket 并投进客户端队列（已剥离 thinking）。
    async def _emit_text(self, text, mq, ws, task_id):
        if not text:
            return
        await ws.send(json.dumps({
            "header": {
                "action": "continue-task",
                "task_id": task_id,  # 随机uuid
                "streaming": "duplex"
            },
            "payload": {
                "input": {
                    "text": text,
                }
            }
        }))
        mq.put_nowait({'content': text})

    # 流式拉取 LLM 文本，剥离 thinking 后边生成边喂给 TTS，同时把文本投进队列。
    async def tts_sender(self, app, inputs, config, mq, ws, task_id, stop_event):
        tf = ThinkingFilter()
        try:
            async for msg, metadata in app.astream(inputs, config=config, stream_mode="messages"):
                if stop_event.is_set():  # 打断：立即停止生成，不再向 TTS 投喂文本
                    return
                if isinstance(msg, BaseMessageChunk):
                    if msg.content:
                        await self._emit_text(tf.feed(msg.content), mq, ws, task_id)
                    if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                        mq.put_nowait({'usage': msg.usage_metadata})
            await self._emit_text(tf.flush(), mq, ws, task_id)
        except ConnectionClosed:
            return  # 打断时 watcher 主动关闭了 ws
        if stop_event.is_set():
            return
        await ws.send(json.dumps({
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex"
            },
            "payload": {
                "input": {}  # input不能省去，否则会报错
            }
        }))


    # 接收 TTS 返回的音频帧，base64 编码后投进队列。
    async def tts_receiver(self, mq, ws, stop_event):
        try:
            async for msg in ws:
                if stop_event.is_set():
                    return
                if isinstance(msg, bytes):
                    audio = base64.b64encode(msg).decode('utf-8')
                    mq.put_nowait({'audio': audio})
                else:
                    data = json.loads(msg)
                    event = data['header']['event']
                    if event in ['task-finished', 'task-failed']:
                        break
        except ConnectionClosed:
            return


    # 打断看门狗：stop_event 置位即关闭上游 ws，解除 sender/receiver 的阻塞。
    async def watch_stop(self, ws, stop_event):
        try:
            while not stop_event.is_set():
                await asyncio.sleep(0.05)
            await ws.close()
        except asyncio.CancelledError:
            pass


    # 建立 TTS websocket，并发跑 sender/receiver/看门狗三个协程。
    async def run_tts_tasks(self, app, inputs, config, mq, voice_id, stop_event):
        task_id = uuid.uuid4().hex
        api_key = os.getenv('API_KEY')
        wss_url = os.getenv('WSS_URL')
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        async with websockets.connect(wss_url, additional_headers=headers) as ws:
            await ws.send(json.dumps({
                "header": {
                    "action": "run-task",
                    "task_id": task_id,  # 随机uuid
                    "streaming": "duplex"
                },
                "payload": {
                    "task_group": "audio",
                    "task": "tts",
                    "function": "SpeechSynthesizer",
                    "model": "cosyvoice-v3-flash",
                    "parameters": {
                        "text_type": "PlainText",
                        "voice": voice_id,  # 音色
                        "format": "mp3",  # 音频格式
                        "sample_rate": 22050,  # 采样率
                        "volume": 50,  # 音量
                        "rate": 1.25,  # 语速
                        "pitch": 1  # 音调
                    },
                    "input": {  # input不能省去，不然会报错
                    }
                }
            }))
            async for msg in ws:
                if json.loads(msg)['header']['event'] == 'task-started':
                    break
            watcher = asyncio.create_task(self.watch_stop(ws, stop_event))
            try:
                await asyncio.gather(
                    self.tts_sender(app, inputs, config, mq, ws, task_id, stop_event),
                    self.tts_receiver(mq, ws, stop_event),
                )
            finally:
                watcher.cancel()


    # 后台线程入口：在独立事件循环里跑 TTS 管线，结束时投 None 作为队列哨兵。
    def work(self, app, inputs, config, mq, voice_id, stop_event):
        try:
            asyncio.run(self.run_tts_tasks(app, inputs, config, mq, voice_id, stop_event))
        except Exception:
            logger.exception('tts worker failed')
        finally:
            mq.put_nowait(None)


    # SSE 生成器：消费队列向前端推 text/audio/metrics，落库并埋点首字/首音频延迟。
    def event_stream(self, app, inputs, config, friend, message):
        mq = Queue()
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self.work,
            args=(app, inputs, config, mq, friend.character.voice.voice_id, stop_event),
            daemon=True,
        )

        # 延迟埋点：实时语音 agent 最关键的工程指标。
        # ttft = 首个文字 token 的延迟；ttfa = 首个音频包的延迟（time-to-first-audio）。
        t_start = perf_counter()
        ttft = None
        ttfa = None
        thread.start()

        full_output = ''
        full_usage = {}
        try:
            while True:
                msg = mq.get()
                if not msg:
                    break
                if msg.get('content', None):
                    if ttft is None:
                        ttft = perf_counter() - t_start
                    full_output += msg['content']
                    yield f'data: {json.dumps({'content': msg['content']}, ensure_ascii=False)}\n\n'
                if msg.get('audio', None):
                    if ttfa is None:
                        ttfa = perf_counter() - t_start
                    yield f'data: {json.dumps({'audio': msg['audio']}, ensure_ascii=False)}\n\n'
                if msg.get('usage', None):
                    full_usage = msg['usage']
        except GeneratorExit:
            # 客户端断连即一次 barge-in：通知 worker 取消上游 LLM/TTS，停止烧 token。
            stop_event.set()
            latency_logger.info(json.dumps({
                'event': 'chat_interrupted',
                'friend_id': friend.id,
                'elapsed_ms': round((perf_counter() - t_start) * 1000, 1),
                'chars_so_far': len(full_output),
            }, ensure_ascii=False))
            raise

        total = perf_counter() - t_start
        metrics = {
            'ttft_ms': round(ttft * 1000, 1) if ttft is not None else None,
            'ttfa_ms': round(ttfa * 1000, 1) if ttfa is not None else None,
            'total_ms': round(total * 1000, 1),
        }
        latency_logger.info(json.dumps(
            {'event': 'chat_latency', 'friend_id': friend.id, **metrics},
            ensure_ascii=False,
        ))
        yield f'data: {json.dumps({'metrics': metrics}, ensure_ascii=False)}\n\n'
        yield 'data: [DONE]\n\n'

        input_tokens = full_usage.get('input_tokens', 0)
        output_tokens = full_usage.get('output_tokens', 0)
        total_tokens = full_usage.get('total_tokens', 0)
        Message.objects.create(
            friend=friend,
            user_message=message[:500],
            input=json.dumps(
                [m.model_dump() for m in inputs['messages']],
                ensure_ascii=False,
            )[:10000],
            output=full_output[:500],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        if Message.objects.filter(friend=friend).count() % MEMORY_UPDATE_EVERY == 0:
            self.schedule_memory_update(friend.id)


    # 后台异步蒸馏长期记忆，避免阻塞 SSE 连接关闭。
    @staticmethod
    def schedule_memory_update(friend_id):
        def _run():
            try:
                update_memory(Friend.objects.get(pk=friend_id))
            except Exception:
                logger.exception('update_memory failed for friend %s', friend_id)
            finally:
                db_connection.close()

        threading.Thread(target=_run, daemon=True).start()
