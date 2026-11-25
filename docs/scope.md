# 手册版本、范围和数据隔离

## 已读取的用户材料

已阅读根目录 `完成GitLab功能图谱智能体_开发提示词.md`、`需求.md`、`软件需求规格说明书.md`，以及解压目录 `FKG_Schema_v0.1` 中说明、Schema、配套校验脚本、示例 JSON 和虚构原文。没有找到压缩包，已有解压材料可用。**课程 PPT 未提供/未找到**；不声称读过 PPT。原 Schema 优先于早期 SRS 中独立 Condition/State 节点建议。

## 官方来源核验（2026-11-02）

固定官方项目：GitLab `gitlab-org/gitlab`，GitLab API project ID 278964。

| 版本 | 实际标签 | tag object target（不是 commit） | 解引用 commit |
|---|---|---|---|
| 15.0 | v15.0.0-ee | 85269c3cc14edb9823783f1e3653be5c28a1d179 | 3b397c1753233301037d0ca3caae23ce116505d3 |
| 17.0 | v17.0.0-ee | a433f5b31d814db8b0f7a36845d2fc7309bbde8f | 8c75d0bf4a4190d94326f1a854d0a102ceca4392 |

官方 tags 和 `repository/tree?ref=标签&path=doc` 的实际响应保存在 `docs/upstream/.gitlab*-tag.json` / `.gitlab*-doc-tree.json`。二者文档根均为 `doc`，`doc/user`、`doc/ci`、`doc/api`、`doc/administration` 等均实际存在；未猜测成不存在的 docs/ 目录。正式下载以解引用 commit 固定，每次再次校验标签。

## 默认的宽范围清单（待用户最终确认）

不是只选几个模块：导入 `doc` 下**所有递归 Markdown**，仅排除下表明确目录。包括普通用户功能、CI/CD、API 替代流程、管理员用户操作、集成、订阅、安全设置、教程、通用操作等。保留其他未知目录，防止因版本新增目录造成静默漏抽。`doc/index.md` 作为入口材料，不自动等同实体。页面/图片/代码链接不当作额外版本事实来源。

范围内目录举例（以实际枚举为准，非模块白名单）：user、ci、api、administration、gitlab-basics、integration、security、subscriptions、topics、tutorials、operations、policy、cloud_seed、editor_extensions、solutions、drawers 等。只要不在明确排除列表，新目录和文档仍入清单。

| 排除项 | 理由 |
|---|---|
| development、architecture | GitLab 产品开发/内部架构，不是本期面向使用者的功能手册 |
| install、update、downgrade_ee_to_ce | 部署安装、升级/降级；与普通/管理员产品操作边界区别记录 |
| raketasks | 部署维护脚本资料，本期不抽取部署运维命令能力 |
| .vale、.markdownlint | 文档质量工具配置 |
| 非 Markdown 文件 | 当前可验证行定位适配器只处理原始 Markdown，不把图片或二进制内容伪装解析成功 |

每个被排除的 Markdown 文件写入 source_snapshot.excluded_documents，含具体 path/reason。下载失败的范围内文件留在 documents，状态 failed+错误；不能移入排除项掩盖失败。无差别全量推理前应确认该边界与课程 PPT 的边界一致。

下载完整范围 ≠ 完整功能覆盖，所有自动图谱始终 partial。不存在可绕过审核的 complete 开关。未来需人工功能覆盖证书后再设计 complete 赋权，不改原 Schema 的枚举。

## 本地文件与样本

- 未验证本地输入只能 example；允许任意清晰声明版本用于受控实验，不与 production 混淆。
- 本地 GitLab 正式输入可逐文件与上述 commit 的对应原始字节核对；提供 repo_prefix，记录真实仓库路径，验证失败不晋级 production。
- 小范围正式字节核验仍是 partial，不因来源真实就称全范围完成。
- 虚构数据仅在 fixtures/synthetic，不作为 GitLab 事实或 E1—E4 结果。
- data 原文副本按来源 ID 隔离，读前核对 SHA256；导入后修改用户原件不会改变快照。

## 尚未执行

本轮核实标签、commit、doc 顶层目录；**未下载全部手册、未运行全部用户功能抽取、未核查覆盖**。正式边界需后续用户确认；允许先验证小范围，但不更改以上正式目标。
