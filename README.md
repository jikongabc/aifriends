# aifriends

> ⭐ **If aifriends helps you, please drop a star** — it keeps the project moving and new features coming.

[English](README.md) · [简体中文](docs/README_zh-CN.md)

A real-time **voice** AI companion app. Create a virtual character, then hold a multi-turn spoken conversation with it: you talk, the character replies **in its own cloned voice**, streaming audio that **starts playing before the model has finished the sentence**. At any moment you can **barge in** — start talking over the AI and it stops mid-word and listens.

> Engineering thesis: a **real-time, multimodal, low-latency async streaming agent**. The bottleneck is I/O (waiting on LLM tokens, TTS audio, ASR), not compute — so the core is `asyncio` concurrency orchestration + a full-duplex streaming pipeline + latency observability, not offline batch processing.

> ⚠️ **Needs OpenAI-compatible LLM and realtime-speech endpoints.** Generation uses an OpenAI-compatible chat/embedding API (developed against DeepSeek + Alibaba Cloud Bailian); ASR/TTS and voice cloning use Alibaba Cloud Bailian's realtime-speech WebSocket. Fill in your own keys in `backend/.env`.

## Features

- **Full-duplex streaming voice pipeline** — ASR (speech→text) → LangGraph agent generation → TTS (streaming synthesis) run concurrently; text is fed into TTS as it is generated, so **the first audio packet starts playing while the LLM is still mid-sentence**.
- **Barge-in / interruption** — browser-side VAD detects the user starting to speak and aborts the live SSE connection; the backend flips a `stop_event` and a watchdog coroutine actively closes the upstream LLM/TTS sockets, so **discarded tokens stop being billed** instead of streaming into the void.
- **LangGraph agent** — an `agent → tools → agent` conditional loop with built-in `get_time` and `search_knowledge_base` (RAG) tools; the graph is compiled once as a process singleton and a `checkpointer` natively manages per-`thread_id` conversation state.
- **Layered memory** — dialogue history is persisted to the database (Django ORM); long-term memory is distilled asynchronously by a background task every N turns and injected into the system prompt. Only durable state is the source of truth, so a restart replays cleanly.
- **Per-character voices** — each character is assigned a cosyvoice voice and speaks in it during chat. Voice-cloning API helpers (create / list / delete enrolled voices) are included but not yet wired to a route — see [Known Limitations](#known-limitations).
- **Latency observability** — every turn records `ttft` (time-to-first-token), `ttfa` (time-to-first-audio) and `total`, written as JSONL; `scripts/latency_report.py` aggregates p50/p95/p99 and the barge-in rate.



1. **Voice chat.** Pick a character, tap the mic, and talk; the reply streams back as text and audio while you can interrupt at any time.

   ![Voice chat](./docs/images/voice-chat.png)

   ![Voice chat](./docs/images/voice-chat1.png)

2. **Character creation.** Build a character — avatar, persona, chat background — and pick a voice from the preset list.

   ![Character creation](./docs/images/create-character.png)

## Quick Start

```bash
# Backend
make install            # pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # fill in API_KEY / API_BASE / WSS_URL / VOICE_URL
make migrate            # python manage.py migrate
make run                # python manage.py runserver  (http://127.0.0.1:8000)

# Frontend (second terminal)
make install-frontend   # cd frontend && npm install
make frontend           # npm run dev  (Vite dev server)
```

Backend deps live in [backend/requirements.txt](backend/requirements.txt); frontend deps in [frontend/package.json](frontend/package.json). Requirements: Python 3.13 (developed on 3.13), Node `^20.19 || >=22.12`, and OpenAI-compatible LLM + Alibaba Cloud Bailian realtime-speech credentials. Copy `backend/.env.example` to `backend/.env` and set the four keys before `make run`.

> **Local dev:** set `const platform = 'vue'` in `frontend/src/js/config/config.js` so the frontend calls your local backend at `127.0.0.1:8000` (switch back to `'cloud'` for the deployed build). Open the **Vite** URL (e.g. `http://localhost:5173`), not the backend port. Voice-input assets are copied into `frontend/public/vad/` automatically on `npm install` (or run `npm run setup:vad`).

## How to Use

1. **Register / log in** — JWT auth; the access token lives in memory and the refresh token in an HttpOnly cookie (silently refreshed by the axios interceptor).
2. **Create a character** — set name, persona (the system prompt), avatar and chat background, and pick a voice from the preset list.
3. **Start chatting** — open a character to create a *friend* relationship (which carries that pairing's long-term memory) and a chat window.
4. **Talk or type** — type text, or tap the mic for voice. In voice mode, VAD auto-detects when you start and stop speaking; starting to speak interrupts the AI mid-reply.
5. **Watch the latency badge** — each turn shows live `ttfa` / `ttft`; run `make latency` to aggregate p50/p95/p99 over the JSONL log.

## Tech Stack

- **Frontend** — [Vue 3](https://vuejs.org/) · [Vite](https://vitejs.dev/) · [`@microsoft/fetch-event-source`](https://github.com/Azure/fetch-event-source) (SSE) · [`@ricky0123/vad-web`](https://github.com/ricky0123/vad) (browser VAD) · MediaSource Extensions streaming playback · Pinia · Vue Router · Tailwind/daisyUI.
- **Backend** — [Django](https://www.djangoproject.com/) + [DRF](https://www.django-rest-framework.org/) + [SimpleJWT](https://django-rest-framework-simplejwt.readthedocs.io/); an `asyncio` + [`websockets`](https://websockets.readthedocs.io/) full-duplex pipeline running in a background thread, bridged to Django's sync world; SSE via `StreamingHttpResponse`.
- **Agent** — [LangGraph](https://langchain-ai.github.io/langgraph/) (process singleton + `checkpointer`) over [LangChain](https://www.langchain.com/), generation by an OpenAI-compatible LLM (DeepSeek).
- **Data / retrieval** — [LanceDB](https://lancedb.com/) vector store + `text-embedding-v4` for the RAG tool; SQLite for history and memory.
- **Speech** — Alibaba Cloud Bailian: `gummy` (ASR), `cosyvoice-v3-flash` (TTS); voice-clone API helpers included (not yet routed).

## Architecture

```text
┌──────────────── Browser (Vue 3 + Vite) ───────────────┐
│  mic → VAD ──(speech start = barge-in)──► AbortController│
│     │ PCM                                        ▲       │
│     ▼                          SSE: text / audio / metrics
└─────┼────────────────────────────────────────────┼─────┘
      │ POST audio                                   │ POST text
      ▼                                              │
┌──── Django + DRF backend ───────────────────────────┼───┐
│  ASRView                               MessageChatView (SSE)
│  (ws duplex)                                        │
│                      ┌──── background thread (asyncio) ───┐
│                      │  LangGraph.astream ──text──► TTS (ws duplex)
│                      │        ▲                        │ audio
│                      │   checkpointer           stop_event / watchdog
│                      └─────────────────────────────────────┘
│                                  │
│  LanceDB (vector / RAG)   SQLite (history / memory)   logs/latency.jsonl
└──────────────────────────────────────────────────────────────┘
```

The browser captures mic audio, runs VAD locally, and POSTs PCM to the ASR view; the recognized text is POSTed to `MessageChatView`, which returns an SSE stream of `text` / `audio` / `metrics` events. Inside the chat view, a background thread runs an `asyncio` event loop that fans out three coroutines — `tts_sender` (pull LLM tokens, feed TTS), `tts_receiver` (collect audio frames), and `watch_stop` (the barge-in watchdog) — bridged back to Django through a thread-safe queue.

## Streaming Pipeline

The heart of the project is `MessageChatView` (`backend/web/views/friend/message/chat/chat.py`) and its agent graph (`graph.py`).

1. **Build inputs** — history is managed natively by the LangGraph `checkpointer` per `thread_id`; only on a cold start (no in-process state) are the last ~10 turns reloaded from the `Message` table, so context survives restarts.
2. **Generate + synthesize concurrently** — `tts_sender` consumes `app.astream(..., stream_mode="messages")` and forwards each text delta to the TTS WebSocket *and* to the client queue; `tts_receiver` reads back audio frames, base64-encodes them, and enqueues them. The two run under one `asyncio.gather`, so audio for the first clause is already playing while later clauses are still being generated.
3. **Barge-in** — when the client aborts the SSE connection (browser VAD fired, or the user hit stop), the generator's `GeneratorExit` sets `stop_event`; `watch_stop` closes the upstream TTS/LLM sockets, unblocking the senders/receivers immediately. The interruption is logged with how much had been generated, so the report can measure wasted work.
4. **Persist + distill memory** — after a completed turn the exchange is written to `Message`; every `MEMORY_UPDATE_EVERY` turns a background thread distills long-term memory (a separate one-node LangGraph) and saves it to the friend, where `_build_system_prompt` injects it on the next turn (the system prompt deliberately stays outside checkpointer state so memory updates take effect immediately).

**Agent graph.** `agent → tools → agent` with a conditional edge: the model node injects the dynamic system prompt and calls the LLM; if the reply contains `tool_calls` the graph routes to a `ToolNode` (`get_time`, `search_knowledge_base` over LanceDB) and loops back, otherwise it ends. The graph is compiled once via a double-checked singleton (`get_app`) — compiling per request would needlessly reconnect LanceDB and recompile the graph.

## Latency & Observability

Each turn emits a structured JSONL record to `backend/logs/latency.jsonl`:

- `ttft_ms` — time to first text token
- `ttfa_ms` — time to first audio packet (the metric that actually governs perceived responsiveness)
- `total_ms` — end-to-end turn duration
- a separate `chat_interrupted` event records how much had been generated at barge-in time

```bash
make latency        # python scripts/latency_report.py
```

aggregates p50 / p95 / p99 / max for each metric plus the completed-vs-interrupted barge-in rate — pure standard library, no Django required, CI-friendly.

## Project Layout

```text
aifriends/
├── backend/                       # Django + DRF API and streaming pipeline
│   ├── backend/                   # project settings, urls, asgi/wsgi
│   ├── web/
│   │   ├── models/                # Character, Voice, Friend, Message, SystemPrompt, UserProfile
│   │   ├── views/
│   │   │   ├── friend/message/chat/    # chat.py (SSE full-duplex), graph.py (LangGraph agent)
│   │   │   ├── friend/message/asr/     # streaming ASR view
│   │   │   ├── friend/message/memory/  # long-term memory distillation graph
│   │   │   ├── create/character/       # character CRUD (+ voice-clone helpers, not routed)
│   │   │   └── user/ · homepage/ · …   # JWT auth, profiles, homepage feed
│   │   └── documents/             # LanceDB knowledge base + custom embeddings
│   ├── scripts/latency_report.py  # p50/p95/p99 + barge-in rate from latency.jsonl
│   ├── requirements.txt
│   └── .env.example
├── frontend/                      # Vue 3 + Vite SPA
│   └── src/
│       ├── components/character/chat_field/  # ChatField, InputField, Microphone (VAD), history
│       ├── js/http/               # api.js (axios + JWT refresh), streamApi.js (SSE client)
│       └── stores/ · router/ · views/
├── docs/                          # README_zh-CN and screenshots
└── Makefile                       # install / migrate / run / frontend / latency
```

## Configuration

Copy `backend/.env.example` to `backend/.env` (gitignored) and fill in:

| Variable | Purpose |
| --- | --- |
| `API_KEY` | OpenAI-compatible LLM + embedding API key (DeepSeek + Alibaba Cloud Bailian) |
| `API_BASE` | OpenAI-compatible endpoint base URL (`.../v1`) |
| `WSS_URL` | Realtime-speech duplex WebSocket for ASR/TTS (Alibaba Cloud Bailian) |
| `VOICE_URL` | Voice-cloning REST endpoint |

Memory cadence (`MEMORY_UPDATE_EVERY`) and the cold-start history window are set in code (`chat.py` / `build_inputs`).

## Development

| Command | Description |
| --- | --- |
| `make install` | Install backend dependencies |
| `make install-frontend` | Install frontend dependencies |
| `make migrate` | Apply database migrations |
| `make run` | Start the Django backend |
| `make frontend` | Start the Vite dev server |
| `make build` | Build the frontend production bundle |
| `make latency` | Aggregate the latency report |
| `make check` | Django system checks |

Comment convention: every function/class carries one concise single-line comment. The `@tool` docstrings in `graph.py` are sent to the LLM as tool descriptions — keep them as docstrings, don't convert them to `#` comments.

## Known Limitations

- **Conversation state is in-process.** The LangGraph `checkpointer` is `MemorySaver`, so hot conversation state lives in one process; multi-worker or restart loses the hot state and replays from the DB. For multi-worker sharing, swap in `PostgresSaver`/`SqliteSaver`.
- **Speech provider lock-in.** ASR/TTS/voice-clone are wired to Alibaba Cloud Bailian's realtime WebSocket/REST shapes; another provider needs an adapter.
- **Single-pass memory.** Long-term memory distillation is a simple periodic one-node graph, not a full memory store with retrieval.
- **Voice cloning not wired up.** The enrollment helpers (`create_voice` / `list_voice` / `delete_voice`) exist but have no route or UI yet; characters use preset cosyvoice voices selected at creation time.
- **RAG knowledge base ships empty.** The `search_knowledge_base` tool degrades gracefully when no LanceDB index is built; populate `web/documents/data.txt` and run `insert_documents` to enable real retrieval.
- **No automated tests yet** beyond `make check` / `make build`; the latency report is the main runtime signal.

## Troubleshooting

- **SSE hangs / no audio** — confirm `WSS_URL` is reachable and `API_KEY` is valid; the TTS worker logs to the backend console. A character with no voice set is rejected up front (set a voice on the character).
- **`VOICE_URL` errors / 500 on voice clone** — make sure `VOICE_URL` is set; the client returns `{'error': ...}` rather than crashing when it's missing or the request fails.
- **401 loops on the frontend** — the axios interceptor refreshes via the HttpOnly `refresh_token` cookie; if it's missing/expired you'll be logged out. Check that the backend set the cookie on login (HTTPS/SameSite settings).
- **Latency report says "no data"** — there are no `chat_latency` records yet; have at least one completed turn so `backend/logs/latency.jsonl` is populated.
