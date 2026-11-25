# GitLab 功能图谱构建与更新智能体 · Windows 操作手册

项目目录：`D:\fkg-agent\gitlab-fkg-agent`。本文所有命令均在 **Windows PowerShell** 中运行，命令里的目录如与本机不同，请先替换。

本项目使用 Python 3.11+、FastAPI、SQLite 和原生 JavaScript；语义抽取仅通过 **OpenCode → `gitlab-fkg` Agent → FKG MCP 工具**执行，不会在连接失败时降级为模拟生成或后端直连模型。

## 你现在应该做什么

你已经在“运行配置 → 读取 OpenCode 可用模型”看到自定义模型，说明**项目的模型清单发现已打通**，但不代表 API Key 有效、账户有额度、协议兼容，或模型已经能调用工具保存图谱。

接下来依次做：

1. 核对并保存两个模型映射，见 **2.5**；不要选择同名或近似名称的默认模型。
2. 执行离线回归，见 **第 3 章**。
3. 导入两版官方手册，见 **4.1**；导入只下载和核验文档，不调用模型。
4. 从官方快照取一份小文档，分别用 DeepSeek、GLM 跑通真实工具闭环，见 **4.2**。
5. 小范围联调通过、范围和预算确认后，再执行 **4.3—4.8** 的 E1—E4、更新确认、导出与比较。

> 验证边界：模型配置和离线测试不能作为真实推理成功证据；本文不声称已完成你的真实 E1—E4。本次文档更新时已重新执行离线回归，**61 项通过**（6.83 秒）；你的环境仍请按第 3 章重新检查。历史 `docs/connection-probe.json` 是连接层证据，`docs/http-acceptance.json` 是受控样本接口证据，都不是正式 GitLab 图谱。

## 目录

1. [项目配置要求及检查配置指令](#1-项目配置要求及检查配置指令)
2. [项目启动全流程步骤](#2-项目启动全流程步骤)
3. [项目回归测试步骤](#3-项目回归测试步骤)
4. [真实 GitLab 两版本两模型四份结果的全流程操作步骤](#4-真实-gitlab-两版本两模型四份结果的全流程操作步骤)

---

## 1. 项目配置要求及检查配置指令

### 1.1 必需组件与网络

| 项目 | 要求 / 用途 |
|---|---|
| Windows PowerShell | 推荐使用 Windows PowerShell 5.1 或 PowerShell 7；无需激活虚拟环境 |
| Python | 3.11 或以上；使用 `requirements.lock` 中的固定依赖 |
| OpenCode | 当前适配器严格支持 **2.0.32**；不是“版本越新越好”，其他版本会被拒绝，需要另行验证协议 |
| 浏览器 | 打开 `http://127.0.0.1:8765` |
| 模型账户 | DeepSeek 和智谱官方平台的 API Key、所指定模型的权限与可用额度 |
| 网络 | 能访问 GitLab 官方 API、DeepSeek、智谱；安装依赖时需访问 Python 包源 |
| 磁盘与时间 | 两版文档、下载缓存、SQLite、模型会话和导出会持续占用空间；全范围分块推理可能耗时、耗费大量额度 |
| Node.js | **不是启动必需项**；仅在可选 JavaScript 语法检查中使用 |

先进入项目并选择实际 Python。**每个新的操作终端都需要重新设置 `$Python`**：

```powershell
Set-Location D:\fkg-agent\gitlab-fkg-agent
$Python = if (Test-Path .\.venv\Scripts\python.exe) {
    (Resolve-Path .\.venv\Scripts\python.exe).Path
} elseif (Test-Path ..\.venv\Scripts\python.exe) {
    (Resolve-Path ..\.venv\Scripts\python.exe).Path
} else {
    $null
}
if (-not $Python) { throw '尚无虚拟环境，请先执行 1.2 的首次安装，再运行本段。' }
& $Python --version
& $Python -m pip check
Get-Command opencode | Select-Object Source
opencode --version
```

预期：Python ≥ 3.11、`No broken requirements found.`、OpenCode `2.0.32`。启动脚本优先使用项目内 `.venv`，其次使用父目录 `D:\fkg-agent\.venv`；不要在检查时用一套环境、启动时用另一套环境。

### 1.2 首次安装依赖（已有可用环境则跳过）

```powershell
Set-Location D:\fkg-agent\gitlab-fkg-agent
python --version
# 仅在项目内尚无 .venv、且确实要新建时执行；不要覆盖正在使用的环境。
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip check
```

如果 `python` 不在 PATH，先安装 Python，或用 `py -3` 代替前两条 Python 命令。安装后重新执行 1.1，获得 `$Python`。不需要执行 `Activate.ps1`，也不需要全局修改 PowerShell 执行策略。

### 1.3 两个模型的配置地址、协议与密钥位置

以下值按照你提供的官方地址和模型 ID 配置，**不自动换成近似模型**：

| 项目 | DeepSeek | GLM |
|---|---|---|
| 密钥申请 / 管理平台 | <https://platform.deepseek.com/> | <https://open.bigmodel.cn/> |
| OpenCode `providerID` | `fkg-deepseek` | `fkg-glm` |
| 实际模型 `id` | `deepseek-flash` | `glm-5.3` |
| 应用中的实验显示标签 | `DeepSeek v4 flash` | `GLM 5.3` |
| Base URL | `https://api.deepseek.com` | `https://open.bigmodel.cn/api/v1` |
| 协议 | OpenAI-compatible Chat Completions | OpenAI-compatible **Responses** |
| OpenCode provider package | `@opencode/ai/providers/openai-compatible` | `@opencode/ai/providers/openai-compatible/responses` |
| 本机密钥文件 | `.secrets\deepseek.api-key` | `.secrets\glm.api-key` |

DeepSeek 的界面标签是项目沿用的实验标签；**真正发送的模型 ID 是 `deepseek-flash`**。不要将显示标签填进 model ID。GLM 不能因为报错就改用 Chat Completions 或其他 API 版本。

配置入口是项目根目录 **`opencode.json → providers → 对应 provider → settings`**。其中 `apiKey` 引用 `{file:.secrets/deepseek.api-key}` / `{file:.secrets/glm.api-key}`，不把 Key 写进网页或 README。

如尚未填写：

```powershell
notepad .secrets\deepseek.api-key
notepad .secrets\glm.api-key
```

每个文件只放对应平台的 Key 本身，不加 `API_KEY=`、`Bearer `、引号或 JSON。以 UTF-8 文本保存。已有密钥不要覆盖为占位符。

只检查文件存在且不是空白，**不输出密钥**：

```powershell
'.secrets\deepseek.api-key', '.secrets\glm.api-key' | ForEach-Object {
    $exists = Test-Path -LiteralPath $_
    $nonempty = $false
    if ($exists) {
        $nonempty = -not [string]::IsNullOrWhiteSpace(
            [IO.File]::ReadAllText((Resolve-Path -LiteralPath $_).Path)
        )
    }
    [pscustomobject]@{ File = $_; Exists = $exists; NonEmpty = $nonempty }
}
```

两个 `NonEmpty` 应为 `True`；这仍不验证密钥真实性。`.secrets/` 已被 Git 忽略，但属于**本机明文秘密**；备份、压缩、共享项目时要排除它和 `.env`，不要发送完整 OpenCode 服务日志。

### 1.4 检查 Agent、MCP、Provider，不打印认证信息

```powershell
$oc = Get-Content .\opencode.json -Raw -Encoding UTF8 | ConvertFrom-Json
$oc.agents.PSObject.Properties.Name
$oc.mcp.servers.fkg | Select-Object command, cwd, environment
foreach ($provider in 'fkg-deepseek', 'fkg-glm') {
    $p = $oc.providers.$provider
    [pscustomobject]@{
        Provider = $provider
        Package = $p.package
        BaseURL = $p.settings.baseURL
        Models = ($p.models.PSObject.Properties.Name -join ', ')
    }
}
$mcpPython = $oc.mcp.servers.fkg.command[0]
[pscustomobject]@{
    AppPython = $Python
    McpPython = $mcpPython
    McpPythonExists = (Test-Path -LiteralPath $mcpPython)
}
```

核对：

- Agent 清单包含 `gitlab-fkg`，MCP 服务名为 `fkg`。
- MCP `command` 使用存在的 Python，后续参数为 `-m app.tools`；`cwd` 是本项目绝对路径。建议和 `$Python` 一致，至少要有同一套依赖。
- MCP `environment.FKG_DATA_DIR` 与应用的 `FKG_DATA_DIR` 必须指向**同一个数据目录**。
- 两个 provider 的 package、Base URL 和模型 ID 与 1.3 一致。

你现在已经能发现模型，通常**无需重新生成配置**。仅在新环境初始化或迁移 Python 路径时，停止相关服务、备份并检查差异后，才考虑：

```powershell
# 首次创建 Agent/MCP；已有配置不同会拒绝直接覆盖。
& $Python scripts\configure_opencode.py
# 若明确需要刷新项目 Agent/MCP，再执行下行；会保留备份与已有 providers。
# 注意：会按当前项目默认 data 路径重建 MCP，自定义目录需要再次对齐。
# & $Python scripts\configure_opencode.py --refresh

# 仅在模型配置 / 应用映射缺失时初始化，不是每次启动必需项。
& $Python scripts\configure_models.py
# 自定义数据目录时改用：
# & $Python scripts\configure_models.py --data-dir 'D:\实际数据目录'
```

`configure_models.py` 不覆盖已有密钥、保留其他 provider；同名 provider 内容不同会拒绝覆盖，需要人工合并。它会写入所指定数据库的两模型映射，别在正式实验中途运行。

### 1.5 `.env` 与数据目录

若尚无 `.env`，只复制一次：

```powershell
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
notepad .env
```

最小内容如下。`OPENCODE_PASSWORD` 填本次 OpenCode 服务实际认证密码，**不是 DeepSeek / GLM API Key**。不要把下面的说明文字当成密码。

```dotenv
FKG_DATA_DIR=./data
OPENCODE_URL=http://127.0.0.1:4096
OPENCODE_DIRECTORY=D:\fkg-agent\gitlab-fkg-agent
OPENCODE_PASSWORD=在本机填入OpenCode服务密码
PYTHONUTF8=1
```

- `.env` 由 `scripts/start.ps1` 加载，值不加引号；其他独立 Python 脚本不会自动加载它。
- `OPENCODE_DIRECTORY` 是 OpenCode 能看到的项目绝对路径；必须从该项目配置上下文发现 Agent 和 provider。
- 默认原始文档快照：`data\sources\<source_id>\raw\...`；SQLite：`data\fkg.sqlite3`；下载缓存：`data\imports\...`。
- 自定义 `FKG_DATA_DIR` 时同步修改 OpenCode MCP 的环境配置，重启两个服务。后文命令也要使用实际数据目录。
- 本地导入默认允许项目目录及其父目录内的文件。如需其他目录，在 `.env` 中设置 `FKG_IMPORT_ROOTS`，Windows 用分号分隔多个**允许根目录**，然后重启应用。不要开放整个磁盘。
- `config/models.example.json` 是模板 / 说明，**不是应用启动时自动读取的运行配置**。实际映射保存在对应数据目录的 SQLite 中，通过网页或 `/api/config` 检查。

---

## 2. 项目启动全流程步骤

### 2.1 启动前检查端口

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 4096, 8765 } |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

没有输出表示端口未监听。如果已有服务，先确认是否就是当前项目的服务，不要重复启动或直接强杀不明进程。

### 2.2 终端 A：启动 / 复用 OpenCode

```powershell
Set-Location D:\fkg-agent\gitlab-fkg-agent
opencode --version
opencode serve --hostname 127.0.0.1 --port 4096
```

保持终端运行。若已有正确目录与版本的服务则直接复用。若刚补 Key 或更改 `opencode.json`，应在原服务终端按 `Ctrl+C` 停止后重启，确保新配置生效。

将本次服务的认证密码填入 `.env` 的 `OPENCODE_PASSWORD=`。服务重启后密码如变化，需要同步更新，并重启应用；不要把密码发给他人。

### 2.3 终端 B：启动 Web 应用

```powershell
Set-Location D:\fkg-agent\gitlab-fkg-agent
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

保持终端运行，浏览器访问 **<http://127.0.0.1:8765>**。服务仅监听本机，不能直接暴露到公网；**不要加 `--workers`，不要同时启动两份使用相同数据库的应用**，当前任务队列仅支持单进程串行。

### 2.4 终端 C：检查应用连接并准备操作命令

终端 A、B 不动。新开 PowerShell，先执行 1.1 的目录和 `$Python` 选择代码，再执行：

```powershell
$Api = 'http://127.0.0.1:8765'
$status = Invoke-RestMethod "$Api/api/status"
$status.connection | Format-List
(Invoke-RestMethod "$Api/api/models") |
    Where-Object { $_.providerID -in 'fkg-deepseek', 'fkg-glm' } |
    Select-Object providerID, id, enabled
(Invoke-RestMethod "$Api/api/config").models | ConvertTo-Json -Depth 10
```

预期 `connected=True`、`version=2.0.32`、`agent_available=True`、`mcp_connected=True`。任何一个未满足，先修复，不能只看页面能打开。

后续 API 操作统一使用下面两个帮助函数，避免 Windows PowerShell 把中文 JSON 用错误编码发送或保存：

```powershell
function Send-FkgJson {
    param([string]$Path, [object]$Body, [string]$Method = 'Post')
    $json = ConvertTo-Json -InputObject $Body -Depth 100
    Invoke-RestMethod -Uri ($Api + $Path) -Method $Method `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($json))
}
function Save-FkgJson {
    param([string]$Path, [object]$Value)
    $full = [IO.Path]::GetFullPath($Path)
    $json = ConvertTo-Json -InputObject $Value -Depth 100
    [IO.File]::WriteAllText($full, $json, [Text.UTF8Encoding]::new($false))
}
```

本章以后的 API 命令默认在**同一个终端 C**执行，保留 `$Api`、`$Python` 和函数；换终端需要重新设置。

### 2.5 网页：保存确切模型映射与预算

进入“运行配置”，读取模型后，填写并点击 **“保存任务配置”**：

| 输入框 | 填写值 |
|---|---|
| DeepSeek providerID | `fkg-deepseek` |
| DeepSeek 实际 model ID | `deepseek-flash` |
| GLM providerID | `fkg-glm` |
| GLM 实际 model ID | `glm-5.3` |

- 若已是上述值，核对即可；读取模型清单**不等于自动选择、保存或测试**。
- 首次小范围任务可先设置保守的 token / 美元预算和合适的每会话超时。具体额度按账户与价格决定，本文不提供虚假的“必定够用”数值。
- 界面的“总 token / 总美元上限”是**单个运行任务内各会话累计上限**，不是整套 E1—E4 的总上限。E4 有两个运行，需分别计费。
- 空值代表不限；正式全量前明确是否接受这一风险。预算在轮询点检查，单次请求可能越限；若 provider 未提供价格，美元限制不能替代平台侧额度限制。
- 默认会话超时为 900 秒；这是每会话而非整场实验时长。并发固定为 1，候选修正最多 3 次。采样参数与 OpenCode 内部重试在 OpenCode 配置中控制。

保存后在终端 C 再读一次：

```powershell
Invoke-RestMethod "$Api/api/config" | ConvertTo-Json -Depth 20
```

### 2.6 日常启动、停止和备份

以后通常只需：启动终端 A → 检查 `.env` 服务密码 → 启动终端 B → 打开页面。不要重复安装、重建数据库或重新初始化 provider。

停止前先检查任务。若正在推理，使用页面“取消”，等待任务停止 / 保存检查点，再在终端 B、A 分别按 `Ctrl+C`。重启后原运行会进入检查点状态，需要显式恢复，不会偷偷从头重跑。

需要完整备份时，**先停止应用与 OpenCode/MCP 写入**，再复制整个 `data` 目录。只拷贝正在写入的 `fkg.sqlite3` 可能漏掉 SQLite WAL 数据。秘密文件另行安全保管，不放入可公开的实验附件。不要修改或删除 `data\sources\...\raw` 原始手册，否则哈希和引文校验会失败。

---

## 3. 项目回归测试步骤

建议顺序：离线单元 / 集成回归 → 原始 Schema 校验 → 可选受控 HTTP 验收 → 第 4.2 节真实模型小样本。**前几项通过不等于真实模型已通过。**

### 3.1 离线自动化回归（不消耗模型额度）

在终端 C、项目根目录执行：

```powershell
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw '依赖检查失败' }
$TestTemp = '.test-work-readme-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
& $Python -m pytest tests -q "--basetemp=$TestTemp" -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw '回归测试失败，请先查看失败项，暂不执行正式实验' }
```

本次文档更新时，在父目录虚拟环境执行完整回归得到 `61 passed in 6.83s`；代码、测试或所选环境有变化时以本机实际输出为准。测试使用受控样本和隔离临时目录 / 替身，不会证明官方平台鉴权或推理成功，也不应当被写成正式实验结果。使用新的临时目录，不指向 `data` 或其他已有重要目录。

### 3.2 原始 Schema、引用与前端语法

```powershell
& $Python schema\validate_fkg.py fixtures\synthetic\fkg.example.json `
    --source-root fixtures\synthetic
if ($LASTEXITCODE -ne 0) { throw '原始 Schema 样本校验失败' }
& $Python -m compileall -q app scripts
if ($LASTEXITCODE -ne 0) { throw 'Python 语法检查失败' }

# 可选：仅当本机有 Node.js 时检查前端语法；不是前端构建步骤。
if (Get-Command node -ErrorAction SilentlyContinue) {
    node --check web\app.js
    if ($LASTEXITCODE -ne 0) { throw 'JavaScript 语法检查失败' }
}
```

原始脚本输出 `PASS: structure and implemented graph invariants...` 表示结构与已实现不变量通过，**不是原文语义蕴含或全覆盖证明**。

### 3.3 受控 HTTP 验收（需要应用已启动；不调用模型，但会写数据）

```powershell
& $Python scripts\verify_http.py
if ($LASTEXITCODE -ne 0) { throw 'HTTP 验收失败' }
```

此脚本访问 `127.0.0.1:8765`，会在**当前应用数据库**中创建明确标记为非 GitLab 的样本来源、图谱、人工修改预览、新快照和审计记录，并覆盖 `docs/http-acceptance.json`。它**不是只读探活**；在正式实验前运行一次即可，不要在正式结果中途反复添加样本。

检查报告 `checks` 中各项为 `true`，并在网页人工检查：

- “功能图谱”：功能树、节点详情、依赖方向、条件 / Workflow、原文定位。
- “更新与核查”：样本的 before/after、已确认状态、旧快照保留。
- “导出合法 JSON”：下载成功。

样本 `purpose=example`，不能选作 E1—E4 来源。浏览器视觉核查仍需你实际查看，脚本不会替你证明页面视觉完全正确。

### 3.4 真实模型回归与故障处理

真实回归必须执行 **4.2 的两个独立小范围任务**，并检查实际模型、Agent、工具、结构、引文和最终保存，不能只执行“读取可用模型”。之后改动 Key、协议、provider、Agent 或工具，也应重新跑小样本。

| 现象 | 排查顺序 |
|---|---|
| 页面打不开 | 终端 B 是否仍运行、8765 是否被占用、Python 依赖是否正确 |
| OpenCode 未连接 / 401 | 4096 服务、`.env` 的 URL / 服务密码、应用是否重启；先区分服务鉴权还是模型平台鉴权 |
| Agent 未发现 | OpenCode 工作目录、`OPENCODE_DIRECTORY`、项目 `opencode.json` |
| MCP 未连接 / 找不到任务数据 | MCP Python 路径、依赖、cwd、两个 `FKG_DATA_DIR` 是否一致 |
| 模型列出但推理 401/403 | 对应密钥、账号额度 / 模型权限、Key 修改后是否重启 OpenCode |
| 404 / 不支持参数 / Responses 错误 | 完整 Base URL、协议 package、实际模型 ID、官方账号支持情况；不静默换模型或协议 |
| GitLab 导入失败 / 429 | 网络、GitLab API 限流、错误日志；等待后恢复原导入检查点，不重复新建全量导入 |
| 运行 `checkpointed` / `failed` | 查看任务详情中的 `error`、session 和已完成分块；修复后恢复原任务，不重复提交同一实验 |
| 预算到达 | 保留检查点；运行记录保存了提交时的预算配置，修改网页全局预算不一定能改变原运行的快照。不要改数据库绕过；需调整实现或以明确记录的新条件重启实验 |
| 校验失败 / 引文不能迁移 / 人工编辑冲突 | 核查来源与操作，补充新版本证据或审核冲突；未解决前不确认，不篡改原文 / 强制标记成功 |

---

## 4. 真实 GitLab 两版本两模型四份结果的全流程操作步骤

### 实验设计：先明确“四份结果”是什么

| 组别 | 模型 | 输入与流程 | 最终输出 |
|---|---|---|---|
| E1 | DeepSeek / `deepseek-flash` | 从同一份 17.0 官方来源独立生成 | 17.0 图谱 1 |
| E2 | DeepSeek / `deepseek-flash` | 再次独立生成；不是复制 E1 或把 E1 当输入 | 17.0 图谱 2 |
| E3 | GLM / `glm-5.3` | 从与 E1/E2 相同的 17.0 来源独立生成 | 17.0 图谱 3 |
| E4 | DeepSeek / `deepseek-flash` | 先生成 15.0 旧图，再用 17.0 来源增量更新并人工确认 | 17.0 图谱 4，另保留 15.0 旧图 |

因此是 **5 个运行任务、4 份最终 17.0 图谱、另加 1 份 15.0 中间快照**。不是简单的“15.0/17.0 × DeepSeek/GLM”四格组合，不需要额外生成 GLM 15.0 来替代 E2。

### 4.1 导入并核验两版官方手册（不调用模型）

#### A. 先确认正式范围

阅读 [docs/scope.md](docs/scope.md)。默认从官方 `gitlab-org/gitlab` 项目（API project ID `278964`）固定 commit 导入 `doc` 下所有递归 Markdown，而非当前最新在线文档，也不是只挑几个功能模块。

| 版本 | tag | 固定 commit |
|---|---|---|
| 15.0 | `v15.0.0-ee` | `3b397c1753233301037d0ca3caae23ce116505d3` |
| 17.0 | `v17.0.0-ee` | `8c75d0bf4a4190d94326f1a854d0a102ceca4392` |

包含用户、CI/CD、API、管理员操作、安全、集成等范围；明确排除 `development`、`architecture`、`install`、`update`、`downgrade_ee_to_ce`、`raketasks`、`.vale`、`.markdownlint` 下的 Markdown，以及所有非 Markdown 文件。排除明细在来源快照中保留。

**正式全量推理前应确认这符合你的研究 / 课程范围**；如需改变边界，要同步调整并重新导入两版，不能仅对一版改范围。两版文件数量不必相同，但范围规则必须一致。

当前实现没有人工全覆盖认证入口，来源 `scope_confirmed=False`、自动图谱 `coverage_status=partial` 是保守设计，不能手改成 `complete` 来宣称完成。

#### B. 提交后台导入

网页：“文档与版本” → “指定官方仓库” → 选 15.0 → “导入官方完整范围”；15.0 完成后同样导入 17.0。也可用以下 API，**二选一，不要网页和命令各提交一次**：

```powershell
# 使用 2.4 中的 $Api 和 Send-FkgJson。已有可用来源时跳过提交，直接查看 /api/imports。
$Import15 = Send-FkgJson '/api/sources/official' @{ version = '15.0' }
$Import15 | Select-Object id, version, status, stage
```

用下面的命令查看进度，必要时重复执行（或使用网页“刷新状态”）：

```powershell
(Invoke-RestMethod "$Api/api/imports") |
    Select-Object id, version, status, stage, processed, total, source_id, error |
    Format-Table -AutoSize -Wrap
```

导入阶段为 `verify_tag → enumerate → download → snapshot`。开始时 `total` 可能未知，不表示失败。**POST 返回的是 import job，不是 source_id；提交成功或页面提示不代表下载已经完成。**以 `/api/imports` 中 `status=succeeded` 且有 `source_id` 为准。

如 `checkpointed`，先查看 `error`，修复网络 / 限流后恢复**原导入 ID**：

```powershell
# 替换为真实 import_... ID；不要把 source_id 填到这里。
# Send-FkgJson '/api/imports/import_实际ID/resume' @{}
```

恢复会复用通过哈希核验的下载缓存，并可能创建新的来源快照。必须使用**最后成功导入记录指向的 source_id**；失败文件不会被偷偷排除。

15.0 导入成功后，再提交 17.0（网页已经提交过的请跳过），同样检查导入进度，直至成功：

```powershell
$Import17 = Send-FkgJson '/api/sources/official' @{ version = '17.0' }
$Import17 | Select-Object id, version, status, stage
```

#### C. 记录来源 ID 并检查

```powershell
(Invoke-RestMethod "$Api/api/sources") |
    Select-Object id, version, purpose, verified, commit, manifest_sha256 |
    Format-Table -AutoSize -Wrap

# 从成功导入记录复制真实 ID，替换下列占位符。
$Source15 = 'src_替换为15版正式来源ID'
$Source17 = 'src_替换为17版正式来源ID'
$S15 = Invoke-RestMethod "$Api/api/sources/$Source15"
$S17 = Invoke-RestMethod "$Api/api/sources/$Source17"
foreach ($s in @($S15, $S17)) {
    [pscustomobject]@{
        ID = $s.id; Version = $s.version; Purpose = $s.purpose
        Verified = $s.verified; Commit = $s.commit
        Documents = @($s.documents).Count; Chunks = @($s.chunks).Count
        FailedDocuments = @($s.documents | Where-Object processing_status -eq 'failed').Count
        Manifest = $s.manifest_sha256
    }
}
$S15.scope_description -eq $S17.scope_description
```

通过条件：版本分别为 15.0/17.0，`purpose=production`、`verified=True`、commit 与上表一致，文档与分块非空、失败文件为 0，最后的范围比较为 `True`。保存来源 ID 和哈希用于复现。

来源中的文档 `processing_status=pending` 通常只是**尚未进行功能抽取**，不等于下载失败；`failed` 才需要处理。不要误选普通“本地只读导入”产生的 `example`，也不要把下一节的单文件试验来源当全范围来源。

### 4.2 分别跑通两个模型的小范围真实联调（会消耗额度）

**不要直接对全部官方来源试错。**一个任务会处理所选来源的全部分块，当前页面没有“仅处理前 N 个分块”的开关，必须创建独立的小范围来源。

下面从已下载的 17.0 官方快照选一份不超过 8 KB 的用户文档，按原字节复制，并经官方接口再次核验。示例使用默认数据目录；自定义目录请修改 `$DataDir`。

```powershell
$DataDir = (Resolve-Path .\data).Path
$Raw17 = Join-Path $DataDir "sources\$Source17\raw"
$Candidates = @($S17.documents | Where-Object {
    $_.processing_status -ne 'failed' -and $_.path -like 'doc/user/*.md'
})
$PilotDoc = $Candidates | Where-Object {
    $f = Get-Item -LiteralPath (Join-Path $Raw17 $_.path)
    $f.Length -gt 0 -and $f.Length -le 8192
} | Select-Object -First 1
if (-not $PilotDoc) { throw '没有找到小文档，请从已核验的 doc/... Markdown 中人工选择一个较小文件。' }
$PilotDir = Join-Path $PWD ('manuals\pilot-17-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $PilotDir -Force | Out-Null
$PilotFile = Join-Path $PilotDir ([IO.Path]::GetFileName($PilotDoc.path))
Copy-Item -LiteralPath (Join-Path $Raw17 $PilotDoc.path) -Destination $PilotFile
$RepoPrefix = $PilotDoc.path.Substring(0, $PilotDoc.path.LastIndexOf('/'))
$Pilot = Send-FkgJson '/api/sources/local' @{
    path = $PilotFile; version = '17.0'; verify_official = $true
    repo_prefix = $RepoPrefix
    scope = 'PILOT ONLY: one pinned official 17.0 document; not formal full scope'
}
$Pilot | Select-Object id, version, verified, purpose, scope_description
```

注意：本地导入网页目前没有官方核验字段，所以这里使用 API 的 `verify_official=true` 和真实 `doc/...` 前缀。仅复制、普通导入或手填“17.0”不能证明官方来源。核验需要访问 GitLab；原始文件不要编辑或重编码。

网页“概览与任务 → 提交真实 Agent 任务”：

1. 目标文档选择刚创建的小范围 17.0 来源，用 `source_id`、文件数量和范围说明确认，不要误选全量来源。
2. 处理流程选“单版生成”，旧图谱不选。
3. 模型选“DeepSeek v4 flash”，提交，等待成功。
4. 同一小范围来源再独立提交一次，模型改为“GLM 5.3”，等待成功。

若下拉列表不易区分，可直接用 API 指定精确来源。**使用 API 后，不要再在网页重复提交同一试验**：

```powershell
$PilotDs = Send-FkgJson '/api/runs' @{
    mode = 'generate'; source_id = $Pilot.id; model_label = 'DeepSeek v4 flash'
}
$PilotDs | Select-Object id, status
```

每个任务必须核对：

```powershell
# 先查看 DeepSeek；检查 GLM 时改用其真实 run ID。
$PilotRunId = $PilotDs.id
$PilotRun = Invoke-RestMethod "$Api/api/runs/$PilotRunId"
$PilotRun | Select-Object id, status, requested_model, graph_id, error, usage
Invoke-RestMethod "$Api/api/runs/$PilotRunId/tools" | ConvertTo-Json -Depth 20
# 更多详情：网页任务“详情”，或 $PilotRun | ConvertTo-Json -Depth 100
```

**联调通过清单：**

- 任务为 `succeeded` 且有 `graph_id`，不是仅创建会话或输出一段文本。
- 任务详情 / OpenCode 消息中实际 provider、model 与指定值一致，Agent 是 `gitlab-fkg`，无默认模型替代。应用也会校验实际消息身份。
- `/tools` 中存在真实 FKG 工具调用与成功结果；可以追溯读取原文、候选校验和结果制品 / 保存，而非空日志或仅模型自述“已完成”。
- 打开图谱能看到与该文档相关的结构；依据引用对应 17.0 原文与连续行，下载“导出合法 JSON”成功。人工抽查事实，不接受虽然合法但与文档无关的空壳图谱。
- 记录运行 ID、耗时、token、成本与错误。`usd=null` 表示未知，不代表免费；OpenCode 估算成本也不是平台账单。

如果使用 API 提交，DeepSeek 完成并通过以上检查后，再运行下段提交 GLM，然后把前面检查代码的 `$PilotRunId` 改为 `$PilotGlm.id`，重复同样的核查：

```powershell
$PilotGlm = Send-FkgJson '/api/runs' @{
    mode = 'generate'; source_id = $Pilot.id; model_label = 'GLM 5.3'
}
$PilotGlm | Select-Object id, status
```

如果小文档本身没有可抽取功能，换一份包含明确用户操作的小文档再试；不要用“空图校验通过”代替语义闭环。两模型都通过后再继续。小样本即使标记 `production/verified`，也仍是 **PILOT 范围**，不得冒充正式全范围输入。

### 4.3 正式实验前冻结条件

正式提交前，逐项确认并记入实验备注 / 附件：

- [ ] 正式来源使用 **4.1 的 `$Source15`、`$Source17`**，不是 4.2 的 `$Pilot.id`，两版按同一全范围规则导入且无失败文件。
- [ ] 两个小范围真实模型任务都已验证工具闭环。
- [ ] 网页保存的是确切的两个 provider / model ID。
- [ ] 全量预算、单会话超时、账户余额和平台限制可接受；E4 是两次运行，整场没有单独的总费用硬上限。
- [ ] Agent 指令、工具、Schema、provider、采样 / 重试策略、应用版本不在实验中途修改；E1/E2 同输入、同条件，仅运行独立。
- [ ] 从试验预算切换为正式预算并保存；**运行创建时会保存当时配置，整套实验不是提前一次性冻结所有未来运行**，因此执行中不要再改全局配置。
- [ ] 不在实验运行中进行人工图谱编辑、删来源、升级 OpenCode、重建环境或重复提交四组实验。

可先记录环境和配置摘要（不含 Key）：

```powershell
& $Python --version
opencode --version
Get-FileHash instructions\gitlab-fkg.md, schema\fkg.schema.json -Algorithm SHA256
Invoke-RestMethod "$Api/api/config" | ConvertTo-Json -Depth 30
# 如本项目由 Git 管理，可另记 git rev-parse HEAD 和 git status --short。
```

### 4.4 一次提交 E1—E4 并查看状态

网页“实验与比较”：选择 4.1 的 15.0、17.0 正式来源 → **“执行四组实验（消耗模型额度）”**。系统串行调度 E1 → E2 → E3 → E4_old → E4_update，不需要你分别点击五次。

或在终端 C 使用 API（二选一）：

```powershell
$Experiment = Send-FkgJson '/api/experiments' @{
    source15 = $Source15; source17 = $Source17
}
$ExperimentId = $Experiment.id
$ExperimentId
```

如果通过网页提交，从下列结果复制完整实验 ID，然后设置 `$ExperimentId`。命令行客户端也是同一入口，**不要再执行 start 重复创建**：

```powershell
(Invoke-RestMethod "$Api/api/experiments") |
    Select-Object id, source15, source17, status, error | Format-Table -AutoSize -Wrap
# 网页提交的用户需填写：
# $ExperimentId = 'experiment_实际ID'

# 可选 CLI 查询：
& $Python scripts\experiments.py status
# 等价启动语法，仅供参考，不要对已提交实验再执行：
# & $Python scripts\experiments.py start --source15 $Source15 --source17 $Source17
```

阶段性检查（反复执行即可，不要反复提交）：

```powershell
$E = (Invoke-RestMethod "$Api/api/experiments") |
    Where-Object id -eq $ExperimentId
$E | Select-Object id, status, runs, error, E4_total_usd, E4_total_tokens
foreach ($entry in $E.runs.PSObject.Properties) {
    $r = Invoke-RestMethod "$Api/api/runs/$($entry.Value)"
    [pscustomobject]@{
        Group = $entry.Name; Run = $r.id; Status = $r.status
        Progress = $r.progress; Graph = $r.graph_id; Preview = $r.preview_id
        Model = ($r.requested_model | ConvertTo-Json -Compress); Error = $r.error
    }
}
```

状态含义：

| 状态 | 操作 |
|---|---|
| `queued` / `running` | 等待；在“概览与任务”看详情与分块，不重复提交 |
| run 为 `checkpointed` / `failed` / `cancelled`，实验为 `stopped` | 先核查并修复错误，再恢复原实验，保留原运行 / session 检查点 |
| `awaiting_E4_confirmation` | 正常人工关口，进入 4.5；不是已经有四份最终结果 |
| `succeeded` | 仍需核查五个运行、导出、引文与事实，不能只凭状态认为质量合格 |

修复后恢复整个原实验，**不要同时逐个恢复子任务又恢复整场**：

```powershell
# 仅在原实验已停止、错误已处理且确定可以恢复时执行。
# Send-FkgJson "/api/experiments/$ExperimentId/resume" @{}
```

若要从头重做，明确建立新的实验 ID 并保留旧失败记录，不要改失败记录冒充一次成功。断点恢复依赖服务会话和持久化检查点；不保证所有外部服务中断都能无成本续跑。

### 4.5 核查并确认 E4 更新（必做）

E4_update 完成候选后，运行状态为 `awaiting_confirmation`，实验通常为 `awaiting_E4_confirmation`。此时**还没有最终 E4 17.0 快照**。

1. “概览与任务”找到 `E4_update` 对应 run → “核查更新”；或把任务详情的 `preview_id` 粘贴到“更新与核查 → 读取预览”。
2. 检查文件差异 `diff`、直接 / 间接影响 `impact`、每项 `operations` 的 `before/after`、变更理由及原文证据。
3. 检查新增、修改、删除是否有 17.0 依据；“新版本没找到旧文本”不能直接证明功能已删除。
4. 检查旧证据是否迁移到正确的新版本文档 / 连续行，未受影响实体是否保持稳定 ID，关系方向、条件、Workflow 与输出绑定是否正确。
5. 有人工编辑冲突、未解决引文迁移或校验错误时，先解决；不要修改原手册、数据库或跳过保护。简单点击“恢复”不能替代人工冲突审核。当前 UI 不是通用自动冲突解决器。
6. 认可候选后，点击 **“确认并保存新快照”**。旧 15.0 图保留，生成新 `graph_id`、延续 `lineage_id`，并产生变更审计记录。

终端可先只读查看完整候选：

```powershell
$E = (Invoke-RestMethod "$Api/api/experiments") | Where-Object id -eq $ExperimentId
$UpdateRun = Invoke-RestMethod "$Api/api/runs/$($E.runs.E4_update)"
$Preview = Invoke-RestMethod "$Api/api/previews/$($UpdateRun.preview_id)"
$Preview | Select-Object id, status, base_graph_id, target_graph_id
$Preview.operations | ConvertTo-Json -Depth 100
$Preview.impact | ConvertTo-Json -Depth 30
# 确认应在你完成审核之后由网页执行，不在本手册自动批量确认。
```

确认后重新查询 `/api/experiments`，应显示 `succeeded`，`E4_update` run 应有最终 `graph_id`。**页面顶部“正式全量实验：未完成”和 `/api/status.formal_experiments_completed` 目前是固定交付提示，不会自动变更**；不能用它们判断本次实验成败，应以 `/api/experiments`、五个运行及实际快照为准。

### 4.6 导出四份最终结果、旧图和审计附件

网页导出：“功能图谱”中分别选择 E1、E2、E3、E4_update 对应的 `graph_id` → “导出合法 JSON”。不要按“最新一份图”猜组别，应从实验 `runs` 映射定位。

以下命令一次归档 **5 份图谱**与运行、工具、来源、预览、变更、统计；不会发起新推理或替你确认更新。导出前需已完成 4.5，且终端 C 保留 2.4 的函数。

```powershell
$E = (Invoke-RestMethod "$Api/api/experiments") | Where-Object id -eq $ExperimentId
if (-not $E -or $E.status -ne 'succeeded') { throw '实验尚未成功，先完成错误处理和 E4 确认' }
$Out = Join-Path $PWD ("outputs\$ExperimentId-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $Out -Force | Out-Null
Save-FkgJson (Join-Path $Out 'experiment.json') $E
Save-FkgJson (Join-Path $Out 'config-at-export.json') (Invoke-RestMethod "$Api/api/config")

$Groups = 'E1', 'E2', 'E3', 'E4_old', 'E4_update'
$Results = @{}
foreach ($group in $Groups) {
    $rid = $E.runs.$group
    if (-not $rid) { throw "缺少运行：$group" }
    $run = Invoke-RestMethod "$Api/api/runs/$rid"
    if ($run.status -ne 'succeeded' -or -not $run.graph_id) {
        throw "$group 尚无成功快照，停止归档"
    }
    $Results[$group] = $run
    Save-FkgJson (Join-Path $Out "$group.run.json") $run
    $tools = Invoke-RestMethod "$Api/api/runs/$rid/tools"
    Save-FkgJson (Join-Path $Out "$group.tools.json") $tools
    # 原样保存 HTTP JSON 字节，避免 PowerShell 默认 Out-File 变成 UTF-16。
    Invoke-WebRequest -UseBasicParsing -Uri "$Api/api/graphs/$($run.graph_id)/export" `
        -OutFile (Join-Path $Out "$group.graph.json") | Out-Null
}
foreach ($entry in @(@{Label='15'; ID=$E.source15}, @{Label='17'; ID=$E.source17})) {
    $source = Invoke-RestMethod "$Api/api/sources/$($entry.ID)"
    # 保留完整 documents / excluded_documents / 哈希等元数据；分块可从数据库追溯。
    $manifest = $source | Select-Object * -ExcludeProperty chunks
    Save-FkgJson (Join-Path $Out "source-$($entry.Label).json") $manifest
}
$preview = Invoke-RestMethod "$Api/api/previews/$($Results['E4_update'].preview_id)"
Save-FkgJson (Join-Path $Out 'E4.preview.json') $preview
$changes = (Invoke-RestMethod "$Api/api/changes") | Where-Object {
    $_.target_graph_id -eq $Results['E4_update'].graph_id
}
Save-FkgJson (Join-Path $Out 'E4.changes.json') @($changes)
$Out
```

归档清单：

- **最终四份**：`E1.graph.json`、`E2.graph.json`、`E3.graph.json`、`E4_update.graph.json`。
- **中间旧图**：`E4_old.graph.json`（15.0，不能当第五份最终 17.0 结果）。
- `*.run.json`：含模型引用、提交配置快照、来源哈希、分块 / session、制品、usage 等；实际消息详情用于核对真实模型。
- `*.tools.json`：实际工具日志；`experiment.json`：组别、运行映射与 E4 总计。
- `source-15.json`、`source-17.json`、`E4.preview.json`、`E4.changes.json`：来源清单与更新证据。
- `config-at-export.json` 仅记录导出时配置；**各 run 内的 `config` 才是该次提交时的配置快照**。正式运行前记录的代码版本、文件哈希和人工审核表另存附件。

原始文档与下载缓存仍在数据目录，不在这些 JSON 中完整内嵌。为了可复验，应保留原始 `raw` 文件和停止写入后备份的数据目录。实验附件可能含原文、会话与运行细节，请先审查再共享；不要把 `.env`、`.secrets` 或带认证的服务日志放进去。

用**原始校验脚本**对导出的图及对应原文再验一次：

```powershell
# 自定义数据目录时，把 .\data 替换为实际目录。
$DataDir = (Resolve-Path .\data).Path
foreach ($group in $Groups) {
    $sid = if ($group -eq 'E4_old') { $E.source15 } else { $E.source17 }
    $rawRoot = Join-Path $DataDir "sources\$sid\raw"
    & $Python schema\validate_fkg.py (Join-Path $Out "$group.graph.json") --source-root $rawRoot
    if ($LASTEXITCODE -ne 0) { throw "$group 导出校验失败" }
}
```

五份均应 PASS。再人工抽查事实与覆盖，不要把 Schema PASS 写成模型抽取准确率 100%。

### 4.7 比较、统计与人工评价

网页“实验与比较 → 跨运行比较与抽样核查”，分别比较：

- E1 vs E2：同模型两次独立生成的稳定性。
- E1 vs E3：相同 17.0 输入的模型差异。
- E1 vs E4_update：直接生成与版本更新结果的差异。

终端可生成并保存同样的候选比较结果（沿用 4.6 的 `$Results`、`$Out`）：

```powershell
foreach ($right in 'E2', 'E3', 'E4_update') {
    $comparison = Send-FkgJson '/api/compare' @{
        left = $Results['E1'].graph_id; right = $Results[$right].graph_id
    }
    Save-FkgJson (Join-Path $Out "compare-E1-$right.json") $comparison
}
```

比较器基于规范化名称和完整归属上下文给出**待人工核查的匹配候选**，不是语义真值裁判；随机 ID、数组顺序、纯 JSON diff 都不适合直接当质量指标。候选还没有被人工接受时，`unmatched` 也不能直接解释成所有真实差异。

人工评价建议固定抽样计划，记录：抽样单位、节点 / 关系、源文档和行号、是否有依据、遗漏 / 错误类型、匹配对、审阅结论与审阅人；覆盖功能、条件、状态、步骤顺序、依赖方向、输出绑定和删除依据，避免只挑容易匹配的名称。

- 没有经过审核的参考答案与完整标注时，precision / recall 为 `null` 是正确行为，不是系统故障。**E1 不是金标准**。
- 需要计算时，`POST /api/compare` 支持 `reviewed_pairs`、`reviewed_relation_pairs`、`reference_is_reviewed`、`node_adjudication_complete`、`relation_adjudication_complete`。只有确实完成对应参考审核与判定后才可声明这些标志；不要为了显示数字而置 `true`。
- 每个运行的 `usage.tokens`、`usage.usd`、`duration_seconds` 和重试单独报告；E4 汇总 **E4_old + E4_update**，不能只统计更新阶段而声称低成本。
- `usd=null` / token 未知不能填 0，OpenCode 估算不等于平台最终账单；区分试验调用、正式调用和重试成本。
- 图谱均可能为 `partial`；即使所有分块处理结束，也只能说明该处理流程结束，不能直接宣称 GitLab 全功能抽取完毕。

### 4.8 完成判定与可复现交付清单

只有同时满足以下条件，才可报告“本次两版本、两模型、四份最终结果实验流程已完成”：

- [ ] 两版来源均来自固定官方 commit，范围规则一致，文件清单、排除项、内容哈希和原文已留存，无失败文件。
- [ ] 实验明确绑定正确两版正式来源；E1/E2 独立、E3 使用正确 GLM，E4 使用正确 DeepSeek；真实消息模型与工具日志可审计。
- [ ] E1、E2、E3、E4_old、E4_update 五个 run 都为 `succeeded`，E4 已经过人工确认而非停在候选状态。
- [ ] 四份最终图谱都是 17.0；15.0 旧图保留。E4 前后 `graph_id` 不同、`lineage_id` 相同，变化有审计依据。
- [ ] 四份最终图和一份旧图均可导出并通过原始 Schema / 关联 / 原文校验。
- [ ] 运行配置、Agent/Schema/代码版本、统计、未知值、重试、更新审阅与人工抽样方法明确记录。
- [ ] 未把受控样本、PILOT 来源、模型列表、连接检查、Schema 合法或候选匹配数冒充正式功能覆盖 / 准确率结果。

如果某个阶段未完成，保留运行和错误记录，报告实际阻塞点，不修改状态造出四份成功结果。

## 进一步参考

- [模型密钥与 provider 配置](docs/model-api-setup.md)
- [范围与官方版本核验](docs/scope.md)
- [架构](docs/architecture.md) · [需求映射](docs/requirements.md) · [历史验证记录](docs/verification.md)
- Agent 指令：`instructions/gitlab-fkg.md`
- 原始 Schema / 校验器：`schema/fkg.schema.json`、`schema/validate_fkg.py`
- 配置与启动：`scripts/configure_opencode.py`、`scripts/configure_models.py`、`scripts/start.ps1`
- 实验客户端：`scripts/experiments.py`
