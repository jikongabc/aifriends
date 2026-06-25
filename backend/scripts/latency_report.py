#!/usr/bin/env python3
# 实时语音对话延迟报告：读 logs/latency.jsonl，聚合 ttft/ttfa/total 的 p50/p95/p99 及打断率。
# 用法: python scripts/latency_report.py [path/to/latency.jsonl]（纯标准库，可进 CI）。
import json
import sys
from pathlib import Path


# 线性插值计算第 p 百分位。
def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 1)


# 打印单个指标的 n / p50 / p95 / p99 / max。
def summarize(name, values):
    if not values:
        print(f'  {name:8s}  (无数据)')
        return
    print(
        f'  {name:8s}  n={len(values):<4d} '
        f'p50={percentile(values, 50):>8.1f}  '
        f'p95={percentile(values, 95):>8.1f}  '
        f'p99={percentile(values, 99):>8.1f}  '
        f'max={max(values):>8.1f}   (ms)'
    )


# 解析日志、分类聚合 chat_latency / chat_interrupted 事件并输出报告。
def main():
    default = Path(__file__).resolve().parent.parent / 'logs' / 'latency.jsonl'
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not path.exists():
        print(f'未找到日志文件: {path}')
        sys.exit(1)

    ttft, ttfa, total = [], [], []
    completed = interrupted = 0
    interrupt_elapsed = []

    with path.open(encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = rec.get('event')
            if event == 'chat_latency':
                completed += 1
                if rec.get('ttft_ms') is not None:
                    ttft.append(rec['ttft_ms'])
                if rec.get('ttfa_ms') is not None:
                    ttfa.append(rec['ttfa_ms'])
                if rec.get('total_ms') is not None:
                    total.append(rec['total_ms'])
            elif event == 'chat_interrupted':
                interrupted += 1
                if rec.get('elapsed_ms') is not None:
                    interrupt_elapsed.append(rec['elapsed_ms'])

    print(f'\n延迟报告  <{path}>')
    print('-' * 64)
    summarize('ttft', ttft)    # 首字延迟
    summarize('ttfa', ttfa)    # 首音频延迟 (time-to-first-audio)
    summarize('total', total)  # 端到端总时长
    print('-' * 64)
    turns = completed + interrupted
    rate = (interrupted / turns * 100) if turns else 0
    print(f'  完成 {completed} 轮 · 被打断 {interrupted} 轮 · 打断率 {rate:.1f}%')
    if interrupt_elapsed:
        print(f'  打断时已生成时长 p50={percentile(interrupt_elapsed, 50)}ms '
              f'p95={percentile(interrupt_elapsed, 95)}ms')
    print()


if __name__ == '__main__':
    main()
