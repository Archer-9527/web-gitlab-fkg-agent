# 架构与接入契约

## 决策

1. Python + FastAPI + SQLite + 原生 JS：Windows 现有 Python 可运行，前端无需打包/Node 运行服务；SQLite 事务保存图谱和日志，业务逻辑与运行时隔离。锁定依赖而非追逐最新版；核心发布元数据已从 PyPI 核验并保存。
2. 原始 Schema 文件和校验脚本原样保留。应用附加来源绑定、人工审核保护、更新影响约束，不修改领域契约。
3. OpenCode v2.0.32：实际执行 `opencode --version`、`serve --help`，读取真实 `/openapi.json`，对照官方固定版本 TypeScript 源码；不是凭旧版记忆编写 `/session/{id}/message` 等接口。
4. Agent 定义位于项目 opencode.json 的 agents.gitlab-fkg.system；正文来自 instructions/gitlab-fkg.md。按 v2 的 mcp.servers 注册 app.tools。无需不确定的 SDK 方法或动态 Skills 机制。
5. 自定义 MCP 工具：fkg_context/schema/read/search/entities/identity/diff/validate/stage，共 9 个；参数在 app/tools.py 声明。普通文本消息只能返回 artifact_id；产物必须由实际领域工具暂存，不信任直接贴在文本的最终图谱。
6. Agent 权限规则先 deny *，再 allow fkg_*；MCP codemode=false 直接暴露领域工具，不授予 shell、编辑、网络或文件系统广泛操作。源码验证 MCP 权限命名为 server_tool。应用工具仅可读授权 source_id，无法提交正式快照。

## 实际 v2 端点

| 用途 | 接口与关键字段 |
|---|---|
| 身份 | GET /api/info → version |
| 契约 | GET /openapi.json |
| Agent / 模型 / MCP | GET /api/agent、/api/model、/api/mcp；location[directory] 为实际项目绝对路径 |
| 创建会话 | POST /api/session，id、agent、model:{id,providerID,variant?}、location:{directory} |
| 提交任务 | POST /api/session/{sessionID}/prompt，id=msg_…、text、resume:true |
| 会话状态与用量 | GET /api/session/{sessionID} → data，outcome/tokens/cost |
| 消息与工具 | GET /api/session/{sessionID}/message，按 cursor.next 分页，assistant.content 中 text/tool |
| 取消 | POST /api/session/{sessionID}/interrupt?resume=false |
| 事件读取 | GET /api/experimental/session/{sessionID}/log?follow=false，保留上游实际 event/id 与数据哈希 |

没有把项目类 OpenCodeRunner 冒充官方 SDK 类。对不支持版本拒绝执行，后续接入版本变化需要新契约测试。真实连接层证据见 connection-probe.json；probe 使用 resume:false，明确没有执行推理。

## 生成闭环

输入清单/哈希 → 章节块队列 → 为当前块建立隔离 OpenCode 会话（同一 run 共用持久化候选，不共享其他 run 模型输出）→ 指定真实 provider/model → 原文读取/检索/身份查询 → Agent 候选 → fkg_validate → 补证/修正（最多3次候选）→ fkg_stage → 后端再次校验 → 应用候选 → 下一块 → 保存 partial 快照。

工具记录必须证明读取当前块完整行窗且对**同一 patch**调用过 validate 后才能 stage。声明推理或私有思维链不当证据，不存 reasoning 部分。所有字段/原子条件/关系依据仍需人工 entailment 核查，Schema 本身不提供语义真值。

## 增量更新

旧图谱与绑定旧手册校验 → 新旧同应用/范围 → 文件内容哈希对齐、相同内容移动识别 → 章节块哈希过滤、模糊改写候选 → changed_chunks → 来源涉及的直接实体 → 沿层级/步骤传播和反向依赖传播 → Agent 对变化块及按需关联原文作语义判断 → 局部操作集。

精确引文自动重定位归为元数据操作；找不到/多重匹配的旧依据不删除，留待 Agent 补证。多块更新可暂存还未轮到处理的旧依据错误，但不会放松其他校验；最后一块必须所有引用合法，任何正式快照无悬空依据。删除须有 deletion_confirmed 和新版证据，缺失文本本身不够。

未影响节点业务字段不得随意变化；无影响关系也不得随意改写。人工标记继承，命中时拒绝自动覆盖，需明确核查列表后预览。确认事务同时写新快照、来源绑定和独立变更日志；base 快照不变。确认幂等，重复点击不生成多个版本。

## 恢复与用量

- 提交键+请求摘要保存在 SQLite，同键不同请求拒绝。
- 会话 ID 和消息 ID 在请求前持久化；提交断连保留未知入队状态，恢复时查原消息身份，避免重新生成候选。
- 原会话 interrupted/failed 时显式在原会话提交新的 continuation 消息，并记录前后消息映射。
- 仅确认 HTTP404 才切换新会话；记录 replaces_session_id，恢复依据是应用候选检查点，不假称 OpenCode 上下文恢复成功。
- 已完成块不再次执行；每个会话累计 token/cost 只汇总一次，失效会话记录也加入合计，避免漏计失败消耗。
- 区分应用候选重试和可观察的 OpenCode message.retry。缺失的实际字段不填零；OpenCode 全零费用在没确认定价时未知；Codex 开发会话不计入。
- token/美元预算在轮询点检查，无法保证终止正在外部执行的单次账单增长；配置 Provider/网关硬限额。

## 数据契约限制 / 最小迁移建议

本轮**未更改 Schema**。

1. sources/evidence 主要适合原始 Markdown 连续行；真实 PDF、HTML/图中说明不能硬塞成伪 Markdown 坐标。后续可版本化增加 locator_kind/页码/DOM 坐标；首版只接受可校验 Markdown。
2. 多版本引用只能经当前快照 documents 注册，不适合将多版本事实混存；运行历史置于外部 run/change 表，遵守指定版本事实约束。
3. 根模块及隐式组织结构仍需来源支持；若真实手册不能直接/推导支撑某字段，应标记 unresolved/诊断或提出最小迁移，不发明依据。
4. complex 执行环必须使用 retry 且去掉 retry 后无环；若真实业务不能表达，保存诊断提出流程 Schema 升级，不改原文语义。
5. 当前自动覆盖没有外部核查证书，complete 一律阻止；最小增强应为独立覆盖核查表，不把运行完毕等同语义覆盖。
6. 语义归并依赖 gitlab-fkg 模型+原文；确定性比较只产出上下文名称候选，不能当通用语义匹配 oracle。

## 已知工程边界

单机单进程串行队列；正式大量手册运行会产生大量隔离会话和完整候选检查点，需先用小范围实测上下文、性能和成本。图树客户端分页，依赖仅显示邻域；后端当前快照 JSON 仍整体读取，超大图应评估索引化节点表。搜索为本地词面召回，Agent 可以换词检索，但不是向量语义检索。模型网关协议/采样能力、真实语义产物和浏览器视觉尚未验证；不把这些写成“已完成”。
