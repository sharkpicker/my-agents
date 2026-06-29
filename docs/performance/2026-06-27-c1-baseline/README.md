# 性能基线:C-1 工作流(2026-06-27)

## 场景
9 只基金真实持仓的 C-1(多基金组合)工作流,跑完整 8 步,采集每步耗时。

## 文件清单

| 文件 | 说明 |
|------|------|
| `holdings.json` | 9 基金原始持仓(代码 + 名称 + 金额 + 收益) |
| `run_workflow.py` | 工作流运行脚本(真实计算 + mock subagent) |
| `perf.json` | 各步骤耗时 JSON |
| `report.html` | 渲染出的 C-1 报告(4,294 bytes) |

## 关键数据

- **HHI**: 0.2179(中等分散)
- **穿透权益占比**: 73.9%
- **本地 + mock 总耗时**: 3,442.32 ms
- **真实计算(Step 2.5)**: 0.07 ms

## 真实运行预测

- 真实 LLM 调用时(假设每 subagent 5-15 秒):
  - Step 1: 35-105 秒(63 subagent 并发)
  - 其他步骤: ~30 秒
  - **预估总时间: 1-3 分钟**
  - **预估 token 数: ~945k**

## P2 Backlog 决策

详见 spec 附录 B.5 — 全部 P2 优化暂不启用,待真实 LLM 数据。

## 复现命令

```bash
cd d:\01_coding\my_agents
python docs/performance/2026-06-27-c1-baseline/run_workflow.py
```