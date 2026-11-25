# 功能知识图谱 Schema v0.1.0

日期：2026-10-30。适用项目：面向 Web 应用的功能图谱构建与更新智能体。

本文是本项目第一版设计约定，不声称复现参考论文的 Schema。需求依据为用户提供的课程 PPT、《需求.md》《软件需求规格说明书.md》及本次讨论。当前正式任务覆盖 GitLab 15.0、17.0 指定版本用户手册中的全部用户功能；先完成指定文档，不将任意产品、任意格式适配列入首版核心范围。

## 1. 核心决策

1. 领域节点只有 Module（模块）、Feature（功能）、Step（操作步骤）三种。
2. 条件、状态使用带稳定编号与来源的结构化属性，暂不设独立节点。
3. 功能树、功能组成和执行依赖分开表达，关系使用六种受控类型。
4. 一项功能允许多种操作流程，Workflow 是功能内嵌记录，不是第四类领域节点。
5. 关键知识逐项绑定指定版本文档依据；文档没有说明的字段保留缺失状态。
6. 图谱快照与增量操作日志分离，跨版本实体沿用稳定标识。

## 2. 模块、功能与步骤的划分

| 类型 | 定义与判定 | 不应据此建立实体 |
|---|---|---|
| Module | 组织一组相关功能的业务主题或领域；自身不需要具有可执行目标 | 任意章节标题、版本说明、背景说明 |
| Feature | 用户可以理解的能力或操作目标，可由手册描述其作用、条件或结果 | 一个按钮名、孤立术语、每个自然段 |
| Step | 某功能的一种流程中的具体用户动作，按手册支持的粒度记录 | 模型自行补出的点击、页面、字段、等待动作 |

划分规则：

- 模块可以包含子模块或功能。功能只有在有依据的功能分解中才包含子功能。具体功能有可识别目标，组织标题只有分类作用，两者据此区分。
- 功能可以没有已记载的操作步骤。手册只说明能力时，保留功能，把 workflows 标记为 not_documented。
- 步骤优先记录单个明确动作；手册没有拆开的复合动作，不强制补拆。导航、输入、命令执行、接口调用均可成为步骤。
- 同一动作在不同功能中的使用情境不同，可以是不同步骤实体。不能仅因动作文字相同就合并。
- 同一功能在多个文档中出现时，归并为一个功能实体并保留多处依据。相似名称不足以作为合并依据。
- 章节结构是提取线索，不直接等同于功能树。函数名、实现类等源码概念不进入首版用户功能图谱，除非它本身是手册描述的用户功能。

## 3. 节点字段

### 3.1 公共字段

| 字段 | 类型 | 语义 |
|---|---|---|
| id | ID | 实体稳定标识，不使用版本、文档路径、名称或行号直接生成唯一身份 |
| node_type | Module / Feature / Step | 节点类型 |
| name | SupportedText | 可读名称及其依据，允许在不改变含义的情况下规范表述 |
| description | SupportedText / null | 手册支持的说明；未记录时为 null |
| aliases | SupportedText[] | 文档支持的别名，不把模型猜测的同义词当事实 |

### 3.2 功能字段

| 字段 | 类型 | 语义 |
|---|---|---|
| preconditions | ClaimField | 功能执行或可用的条件，保留条件组合逻辑 |
| postconditions | ClaimField | 按手册描述，执行后的预期状态或输出；不表示已实际执行成功 |
| workflows | WorkflowField | 手册记载的替代操作流程及其信息完整度 |

Feature 的父级通过 CONTAINS 记录，不重复保存 parent_id，避免两处数据冲突。属于同一功能的步骤通过 HAS_STEP 关联。

### 3.3 步骤字段

| 字段 | 类型 | 语义 |
|---|---|---|
| workflow_id | ID | 所属功能的一种具体流程 |
| action | SupportedText | 明确的动作内容及依据 |
| action_type | 枚举 | navigate、click、input、select、submit、command、api_call、other、unspecified |
| ui_context.page | SupportedText / null | 手册明确说明的页面 |
| ui_context.element | SupportedText / null | 手册明确说明的界面元素；不生成 DOM/CSS 选择器 |
| document_order | integer / null | 在该流程文档中的出现次序，仅为展示信息 |
| preconditions | ClaimField | 该步骤独有的条件，不无条件复制整个功能的条件 |
| postconditions | ClaimField | 该步骤的预期状态或输出 |

document_order 不等于执行依赖。只有文档支持执行顺序时才建立 NEXT_STEP。命令和接口步骤的 ui_context 可以全为 null。

## 4. 条件和状态使用结构化属性

首版不把权限、角色、资源、页面、条件、状态全部拆成独立节点，以控制抽取、合并与增量对齐的复杂度。条件和状态仍可有自己的 ID，供依赖关系精确引用。

### 4.1 ClaimField 与缺失语义

| status | expression | 含义 |
|---|---|---|
| recorded | 非空表达式 | 已记录有依据的条件或状态 |
| not_documented | null | 在本次已读取依据中没有找到说明，不表示条件不存在或必然满足 |
| unresolved | 表达式或 null | 存在歧义、冲突或提取未完成，需要核查 |

解析失败或遗漏待处理不能标记为 not_documented。普通可选说明如 description、page、element 用 null 表示未记录；需要表达冲突时保留 unresolved 的条件/状态和任务诊断记录。

### 4.2 原子知识 ClaimAtom

| 字段 | 语义 |
|---|---|
| kind | 固定 atom |
| id | 原子条件或状态的稳定编号 |
| text | 手册支持的自然语言表述 |
| category | permission、configuration、resource_state、input、navigation、feedback、other |
| support | 来源与推导信息 |

同样的文字若对应不同资源、主体或作用范围，不共享 Claim ID。首版不将自然语言状态当作可执行逻辑程序，不能仅凭文字相似就自动证明满足关系。

### 4.3 条件组合

使用递归表达式：atom 表示一条知识，all 表示同时满足，any 表示至少满足一项。all、any 的 items 至少两项，可以嵌套。否定条件直接保留在原子表述中，不擅自改写其作用范围。

例如“拥有权限，并且满足条件甲或条件乙”写成 all(权限, any(甲, 乙))。不能把“至少其一”改成“全部”，不能把“例如”解释为穷举约束。逻辑不明确时使用 unresolved。

条件放在 preconditions，预期状态或输出放在 postconditions；两者可以描述同一类资源事实，但角色不同。

### 4.4 将来何时升级为独立节点

当确实需要对条件或状态做统一检索、跨大量功能共享、状态迁移分析时，可以在新版本 Schema 中引入独立节点。届时保留现有 Claim ID 或提供迁移映射。当前通过 claim ID 与输出绑定已能表达必要的跨功能引用。

## 5. 多种流程 Workflow

同一目标的 UI、API、CLI 实现通常记录为一个 Feature 下的不同 Workflow，避免串成必须依次执行的步骤。若手册证明目标、权限或语义本身不同，则可以分成不同功能，不只按名称强行合并。

Workflow 字段：id、label（SupportedText/null）、channel（ui/api/cli/mixed/unspecified）、sequence_status（documented/partial/not_documented）、support。

- WorkflowField 的 status 为 recorded、not_documented 或 unresolved，items 保存流程记录。
- not_documented 时 items 必须为空；recorded 时至少一个流程。
- 每个 Step 恰好属于一个 Feature 和其内部一个 Workflow。
- NEXT_STEP 只连接同一 Workflow 的步骤。不同流程不能互相串接。
- 分支通过 NEXT_STEP.guard 表达，重试边标记 flow_kind=retry。只有有依据时才建立。
- 部分顺序未知时 sequence_status=partial；无顺序依据时为 not_documented，不制造步骤间边。

## 6. 允许的关系与方向

所有关系都有 id、relation_type、source_id、target_id、support、details。source/target 必须引用本快照中的节点。关系类型由系统控制，模型不能自由新增枚举。

| 关系类型 | 允许端点与方向 | 准确含义 | 关键约束 |
|---|---|---|---|
| CONTAINS | Module → Module/Feature；Feature → Feature | 功能组织与有依据的子功能分解 | 构成单根树；每个非根模块/功能有唯一父级，无环 |
| HAS_STEP | Feature → Step | 步骤属于该功能的某个流程 | 每个步骤唯一所属功能；workflow_id 必须在该功能内 |
| NEXT_STEP | Step → Step | 同一流程中，源步骤之后允许进入目标步骤 | 不从文档排版自动推断；guard 支持条件分支 |
| REQUIRES_FEATURE | Feature → Feature | 源功能依赖目标功能能力可用或已启用 | 不表示目标功能必须执行一次；不从同模块或同名词推断 |
| REQUIRES_COMPLETION | Feature/Step → Feature/Step | 在给定上下文中，执行源功能/步骤必须先完成目标功能/步骤 | 必须有执行先决关系依据；details.guard 可限制适用情境 |
| USES_OUTPUT_OF | Feature/Step → Feature/Step | 源实体需要使用目标实体产生的具体输出 | details.bindings 必须把源的输入条件与目标的输出状态明确关联 |

NEXT_STEP 的方向是先到后；后三种依赖方向是依赖方到被依赖方。界面应显示关系名称与箭头，不能只凭箭头猜含义。

### 6.1 NEXT_STEP.details

- flow_kind=sequence，guard=null：文档支持的普通后继。
- flow_kind=branch，guard=ClaimExpression：条件满足时进入的后继。
- flow_kind=retry，guard=ClaimExpression：文档支持的返回/重试，并给出触发条件。
- 删除 retry 边后，单个流程不应仍存在循环。若真实流程无法按该约定表达，应报告模型限制并升级 Schema，不能篡改文档。

### 6.2 USES_OUTPUT_OF.details

bindings 中每条包含 consumer_condition_id 与 producer_state_id。前者必须指向 source 节点 preconditions 中的原子条件，后者必须指向 target 节点 postconditions 中的原子输出状态。两者还需要语义上确实是对应输入与输出，引用合法本身不证明语义正确。

本关系只在文档明确说明输出流向，或文档证据足以支持这种推导时建立。仅仅“输出都叫项目”不能建立该关系。

### 6.3 禁止的依赖推断

- “执行需要某资源已存在”只记录资源状态条件，不自动连到“创建该资源”。资源可能已有，文档未必要求当前执行创建。
- “功能 B 的输出可满足 A 的条件”不自动意味着“只有 B 能产生该状态”。没有指定输出流向的依据时，不生成 USES_OUTPUT_OF 或强制完成依赖。
- 两功能出现在同一章、使用同一个词、名称相似，不构成依赖。
- 不根据世界常识补权限要求、功能开关、默认步骤、失败恢复或隐含 UI 行为。
- 不使用 RELATED_TO、DEPENDS_ON 这类没有进一步语义的自由关系，也不添加 CONFLICTS_WITH 等首版未定义的关系。新增类型需升级 Schema。
- 已支持的依赖仍须保留直接/推导标记。核查状态不是“模型认为正确”的概率。

## 7. 文档依据与推导

SupportedText={text, support}。support 字段如下：

| 字段 | 语义 |
|---|---|
| mode | explicit：直接有据的提取或保义规范化；inferred：结合文档作出的推导 |
| evidence_ids | 至少一条当前快照中的 Evidence ID |
| rationale | inferred 必填推导理由；explicit 为 null |
| review_status | unreviewed 或 accepted；accepted 表示已经过约定的核查，不由输出置信度代替 |

被否决的候选知识保留在诊断/候选记录中，不作为有效图谱事实。未核查推导必须在展示和导出中保留标记。正式实验应统一说明候选处理口径，不能把直接生成结果当作标准答案。

Evidence 字段：id、document_id、heading_path、line_start、line_end、quote、fragment_sha256。quote 是原始文件连续行范围的正文，按 LF 换行拼接、不含末尾换行。以原始文件快照为准，不以模型改写文本为依据。

Document 字段：id、path、locator、application_version、content_sha256、processing_status（processed/failed/pending）、error。当前以原始 Markdown 文件行为定位坐标，不对未来 HTML/PDF 支持作承诺。

## 8. 图谱顶层结构

| 字段 | 语义 |
|---|---|
| schema_version | 固定 0.1.0 |
| graph_id | 本次图谱快照标识，新快照使用新 ID |
| lineage_id | 同一图谱演化链标识，跨版本更新保持 |
| application / application_version | 应用名称和当前手册对应版本 |
| created_at | 快照创建时间，含时区 |
| purpose | production 或 example，虚构例子必须为 example |
| root_module_id | 功能树根模块 |
| source_snapshot | 来源、tag、commit、文档清单摘要、范围描述与排除记录 |
| coverage_status | complete 或 partial，仅针对已明确的用户手册边界 |
| documents / evidence | 输入文档清单与知识依据注册表 |
| nodes / relations | 三类领域节点与六类关系 |

正式 GitLab 数据须记录核实后的具体 tag 和 commit，不能只用可变化的最新版链接。documents 清单应覆盖声明输入范围内的全部文件，即使文件处理失败也保留记录。excluded_documents 记录用户手册范围外文件及排除原因，不能用它悄悄缩减已约定的用户功能范围。

manifest_sha256 定义为按 path 升序，将各范围内文档的 path + TAB + content_sha256 + LF 拼接，按 UTF-8 求 SHA-256。原文件摘要按原始字节求 SHA-256。

coverage_status=complete 的前提包括：完整范围已经确认，所有范围内文档处理完成，遗漏与 unresolved 已核查。不能仅因程序跑完或结构校验通过就宣称功能覆盖完全。

模型、提示词、运行耗时与 token 放入运行记录，通过 graph_id 关联，不作为功能事实混进 nodes。增量更新成本单独统计，保留旧版生成成本。

## 9. 稳定标识与增量更新

- 同一业务实体的名称规范化、章节移动、说明改写、版本升级，不应自动改变实体 ID。
- 步骤重排而动作语义与所属流程不变时，尽量保留步骤 ID，并更新顺序边。
- 发生实体拆分或合并时，记录旧新 ID 映射，不强制伪装成一对一相同实体。
- 不以跨版本重新排序序号、文档行号、名称哈希作为稳定身份。
- 同一文档来源位置可变化，更新来源定位不等于功能事实变化。比较时区分业务字段与依据/快照元数据。
- 不能因为新版本某处没有出现旧功能，就立即删除节点。先排查移动、改名、解析失败和范围不一致。
- 有效图谱快照不包含悬空引用。删除节点需要处理关联关系；旧快照与删除前信息保留在更新日志。
- 更新日志应单独记录 base_graph_id、target_graph_id、增删改实体、before/after、原因、旧新文档依据。日志不是本文件 JSON Schema 的验证对象，后续实现时单独定义。

## 10. 校验职责

随包 fkg.schema.json 采用 JSON Schema Draft 2020-12，校验字段、枚举、必填性、基本类型、组合条件结构等。Schema 不能自动证明来源支持、实体身份和依赖语义。

配套 validate_fkg.py 还检查：全局 ID 唯一、引用完整、根节点与层级树、唯一归属、流程一致性、后继关系和重试环、输出绑定、文档版本、来源行范围、清单摘要。提供 --source-root 时还能核对原文和摘要。

语义核查另行完成：

1. 名称与功能粒度是否合理，是否重复或漏抽。
2. 引用原文是否真正支持该字段、条件组合与依赖。
3. 推导是否成立，是否混入版本外知识或常识。
4. 同一 ID 是否确实表示跨版本同一实体。
5. 功能全覆盖、增量影响范围和实体匹配是否满足评测口径。

## 11. 包内文件与用法

- Schema说明_v0.1.md：本说明。
- fkg.schema.json：图谱快照的可执行结构约束。
- fkg.example.json：结构示例，来源仅为同包虚构手册，不是 GitLab 图谱。
- synthetic_manual.md：用于理解和核对示例的虚构手册。
- validate_fkg.py：结构与关键关联校验工具，需要 Python 和 jsonschema 包。

```bash
python -m pip install jsonschema
python validate_fkg.py fkg.example.json --source-root .
```

示例展示模块、功能、两种替代流程、具体步骤、先后关系与输出依赖。REQUIRES_FEATURE、REQUIRES_COMPLETION、分支和重试在 Schema 中允许，但不为了凑齐关系而向示例手册补造知识。
