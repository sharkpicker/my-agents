# 贡献指南

## 如何新增 agent

1. 在 `agents/` 创建 `<name>.md`(workflow 层)或 `<name>.agent.md`(TRAE IDE 层)
2. 遵循现有格式:
   - YAML frontmatter(name / description / tools)
   - 章节:# <角色名> / 角色 / 输入 / 处理流程 / 输出契约 / 铁律
3. 创建对应的 prompt 模板在 `.trae/skills/stock-analysis/role-prompts/<category>/`
4. 更新 `agents-roster.md`
5. 添加单元测试或集成测试

## 如何新增工作流

1. 在 `.trae/skills/stock-analysis/` 创建 `workflow-<name>.md`
2. 在 `SKILL.md` 添加工作流引用
3. 更新 `data_tools/detect.py` 增加类型识别
4. 添加端到端测试在 `tests/e2e/`

## 如何新增测试

- **单元测试**:`tests/unit/test_<module>.py`(测试单个函数/类)
- **集成测试**:`tests/integration/test_<workflow>.py`(测试 8 步流程)
- **E2E 测试**:`tests/e2e/test_<scenario>_e2e.py`(测试完整场景)

所有测试都通过 `pytest -v` 跑通。

## 代码风格

- Python:PEP 8, type hints, docstring
- Markdown:统一 4 段结构(标题/职责/输入/铁律)
- 提交信息:Conventional Commits(`feat:` / `fix:` / `docs:` / `test:` / `chore:`)