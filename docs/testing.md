# 测试运行指南

## 快速开始

```bash
# 全量测试
pytest -v

# 仅单元测试(< 5 秒)
pytest tests/unit -v

# 集成测试(< 5 秒)
pytest tests/integration -v

# E2E 测试(< 30 秒)
pytest tests/e2e -v

# 特定文件
pytest tests/unit/test_detect.py -v
```

## Mock 策略

- **单元测试**:直接测函数,无外部依赖
- **集成测试**:用 `tests/conftest.py` 的 `workflow_runner` fixture(mock 8 步)
- **E2E 测试**:用 `tests/e2e/conftest.py` 的 `e2e_runner` fixture(更真实)

## CI 矩阵

| 触发条件 | 跑哪些 | 期望耗时 |
|---------|-------|---------|
| PR | unit + integration | < 30s |
| main 推送 | unit + integration | < 30s |
| 定时(每日 02:00) | unit + integration + e2e | < 5min |
| 手动触发 | 全量 + 覆盖率 | < 5min |