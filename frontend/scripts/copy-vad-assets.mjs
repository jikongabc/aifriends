// 把语音 VAD 运行时资源从 node_modules 拷到 public/vad/。
// Microphone.vue 把 baseAssetPath 和 ort.wasmPaths 都指向 /vad/，
// 所以 vad worklet、silero onnx 模型、onnxruntime 的 wasm 都要落在这里。
// public/vad/ 被 .gitignore 忽略，故用脚本生成；postinstall 会自动调用。
import { mkdirSync, copyFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dest = join(root, 'public', 'vad')
const vadDist = join(root, 'node_modules', '@ricky0123', 'vad-web', 'dist')
const ortDist = join(root, 'node_modules', 'onnxruntime-web', 'dist')

const files = [
  [vadDist, 'vad.worklet.bundle.min.js'],
  [vadDist, 'silero_vad_v5.onnx'],
  [vadDist, 'silero_vad_legacy.onnx'],
  [ortDist, 'ort-wasm-simd-threaded.wasm'],
  [ortDist, 'ort-wasm-simd-threaded.mjs'],
  [ortDist, 'ort-wasm-simd-threaded.jsep.wasm'],
  [ortDist, 'ort-wasm-simd-threaded.jsep.mjs'],
]

mkdirSync(dest, { recursive: true })

let copied = 0
let missing = 0
for (const [dir, name] of files) {
  const src = join(dir, name)
  if (existsSync(src)) {
    copyFileSync(src, join(dest, name))
    copied++
  } else {
    console.warn(`[copy-vad-assets] 缺少源文件，跳过: ${src}`)
    missing++
  }
}

console.log(`[copy-vad-assets] 已拷贝 ${copied} 个文件到 public/vad/${missing ? `（${missing} 个缺失）` : ''}`)
