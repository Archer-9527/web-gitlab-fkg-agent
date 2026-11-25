# 验证记录（2026-11-02）

## 实际执行

- `python -m pytest tests -q ...`：**57 passed**（最新完整回归），覆盖来源/Schema/关系、AND/OR、未知状态、文档迁移、局部增改删、依赖影响、身份、人工冲突、失败保护、幂等、模型映射、断连、超时、取消、原会话续跑、替换会话检查点、累计费用及 MCP stdio。
- 原 `schema/validate_fkg.py fixtures/synthetic/fkg.example.json --source-root fixtures/synthetic`：PASS。
- Python compileall、`node --check web/app.js`：通过。
- Windows 本机 OpenCode **2.0.32**，真实 API 契约与官方固定版本源码对照；/api/info /openapi.json /api/agent /api/model /api/mcp 实际访问。
- Agent gitlab-fkg 已被发现，60 steps；领域 MCP fkg 实际状态 connected。
- 创建真实持久化会话、带自定义消息 ID 的 resume=false prompt 入队成功。**没有 resume 模型推理**。完整关联见 connection-probe.json。
- 本机真实 Uvicorn `127.0.0.1:8765` HTTP：导入隔离虚构样本 → 树局部接口 → 依赖邻域 → 原文定位 → 合法编辑预览 → 确认新快照 → 旧快照保留 → 合法 JSON 导出 → 非法悬空关系拒绝，全部通过。graph/source/preview ID 见 http-acceptance.json。
- 官方 GitLab 两标签 commit 和 doc 根目录实际核实，证据保存在 docs/upstream；核心依赖版本发布元数据经 PyPI 核实。

## 测试环境问题及处理

沙箱限制 pytest 默认临时目录，首次运行产生 PermissionError；转到批准的工作区测试目录并正常权限重跑。不将环境权限错误当成功。修复了测试中与原始 Schema 不符的 aliases 数据（必须 SupportedText，不是字符串）、dangling 错误断言，然后完整通过。

实现过程中补充修复：MCP 进程不应把运行中任务当服务重启而改状态；取消标记不被检查点覆盖；恢复引用原会话；confirmed HTTP404 才替换会话；失效会话成本保留；按当前消息等待而不是误取旧回复；待处理旧依据只允许中间检查点暂缓，最终严格检查；stage 前必须原文读取和同候选 validate 审计。

## 明确未执行 / 不可据此宣称完成

- 指定 DeepSeek v4 flash、GLM 5.3 的真实实验模型联调。
- 模型在 OpenCode 中实际调用领域工具并产出图谱的语义闭环。
- 全范围 GitLab 手册下载/全功能抽取/覆盖审查/正式 E1—E4/正式精确率召回率。
- 真实模型下取消、断连续跑的供应商侧表现（目前离线契约测试）。
- 浏览器 UI 视觉检查：可用工具返回浏览器 inventory 为空，无法打开浏览器；没有用截图或模拟页伪装视觉通过。
- WSL2 实机执行。

测试 double 只在 tests 内定义，正式应用无 mock 模式、无用虚构抽取替代正式模型的降级路径。未给出的模型配置不会自动推测；正式任务明确报错“模型映射待配置”。
