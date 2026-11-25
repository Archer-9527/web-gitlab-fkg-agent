# 需求 → 实现 → 验证

本表映射《需求.md》的 FR 编号；最新开发提示词的 OpenCode/Schema 约束优先。代码入口可用不代表正式全范围实验已完成。

| 编号 | 实现 | 验证与状态 |
|---|---|---|
| FR-01～05 | documents.py / imports.py / sources API；local、verified-local、固定官方地址、原始清单、失败与重复提示、引用保护 | 本地读写/哈希/失败/越界和 URL 测试通过；官方 tags/tree 实际核实；全量下载未执行 |
| FR-06～09 | instructions/gitlab-fkg.md、tools.py、runner.py、runtime.py；模块/功能/流程/步骤、结构条件、归并、依赖规则 | 候选工具闭环离线契约通过；实际模型语义质量未验证 |
| FR-10～11 | 原 validate_fkg.py + graphs.py，SQLite 快照和 run 绑定 | 结构/来源/流程/输出绑定/失败保护测试通过 |
| FR-12～16 | diff_sources、changed_chunks、rebase_evidence、affected_entities、Agent update 指令 | 移动、改写待确认、纯行移、直接/间接影响测试通过；真实 GitLab 语义变化待模型联调 |
| FR-17～22 | merge_patch、preview_update、preview confirm、manual 表、changes 日志 | 增改删局部操作、before 冲突、删除完整性、旧快照/ID 稳定、人工覆盖拒绝、确认幂等通过 |
| FR-23～27 | web 功能树分页、属性 JSON、局部依赖、原文定位、编辑器、导出、预览 | 真实 HTTP 功能入口验收通过；浏览器视觉未验收 |
| FR-28～29 | 两模型实际引用配置、Agent/provider 职责分离、版本/提示词/工具摘要 | 离线检查请求和实际 assistant.model 不符拒绝通过；指定 API 及模型映射待提供 |
| FR-30～32 | 串行队列、阶段进度、最多3次候选、cancel/resume、会话映射和预算 | 断连/超时/取消/幂等/会话丢失/重试成本测试通过；真实推理恢复未验证 |
| FR-33～35 | experiments.py E1/E2/E3/E4_old/E4_update、独立会话、比较/核查 API、分项/合计 | 无标签不伪造精确率召回率；正式四组实验尚未执行 |

## 非功能约束

- NFR-01/02：原文校验、unresolved/partial、版本绑定；不等于自动证明语义正确和全覆盖。
- NFR-03/09：可展开树、局部关系、真实后端任务状态与错误；视觉布局未实机核查。
- NFR-04/05：ID 不按版本/行号生成，语义身份由 Agent 决定；更新只允许影响范围，比较不按随机 ID。
- NFR-06/07：不可变快照+事务、独立审计、会话/消息/工具/事件关联。
- NFR-08/12：累计用量、重试、阶段配置、输入/指令摘要；实际模型网关账单尚未核对。
- NFR-10：本地监听、来源根限制、同源写保护、浏览器无秘密、隐藏 reasoning；部署为多用户服务前还须登录/RBAC/网络安全设计。
- NFR-11：解析/工具/Agent/适配层/存储/显示模块隔离，原 Schema 保持不变。

## 仍需外部条件的验收项

1. 明确指定实验模型的真实 provider/model_id、接口协议、工具调用能力、采样参数与额度；不能用机器上名称相近的模型替代。
2. 确认用户手册完整边界（scope.md）及未提供的课程 PPT 约束。
3. 真正模型驱动的小范围前后端完整流程，包括实际工具调用、候选修正及语义有效图谱，然后真实增量更新。
4. 完整两版手册处理、遗漏核查、E1—E4 和评估抽样/金标准。
5. 浏览器控制环境或用户人工视觉验收，以及 WSL 实机启动测试。
