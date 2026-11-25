# DeepSeek / GLM API 配置（按用户提供信息，2026-11-25）

已在项目 opencode.json 合并两个 Provider，保留原有 Agent 与 MCP。不修改全局配置。

| 映射标签 | providerID | 模型 id / modelID | 协议 | Base URL |
|---|---|---|---|---|
| DeepSeek v4 flash | fkg-deepseek | deepseek-flash | OpenAI-compatible Chat Completions | https://api.deepseek.com |
| GLM 5.3 | fkg-glm | glm-5.3 | OpenAI-compatible Responses | https://open.bigmodel.cn/api/v1 |

以上 URL、协议、模型 ID 为用户确认输入，尚未使用真实密钥联调。工具能力标志是任务所需配置声明，不是已通过服务端能力验证。

## 你只需要补全这两个文件

在 PowerShell 执行：

```powershell
cd D:\fkg-agent\gitlab-fkg-agent
notepad .secrets\deepseek.api-key
notepad .secrets\glm.api-key
```

- deepseek.api-key：只放 DeepSeek 的 API Key 本身。
- glm.api-key：只放智谱的 API Key 本身。
- 不要写 `API_KEY=`，不要加引号、JSON、Bearer 前缀或其他说明。
- 文件当前为空；没有生成假密钥，没有使用其他模型替代。
- OpenCode v2 的 `{file:...}` 会读取并 trim 内容，无需把 Key 放进环境变量或网页。
- .secrets/ 已加入 .gitignore。但文件仍为本机明文，请保护 Windows 账号/文件权限；打包、同步或分享项目时必须排除该目录。

配置引用：

```json
"apiKey": "{file:.secrets/deepseek.api-key}"
```

以及：

```json
"apiKey": "{file:.secrets/glm.api-key}"
```

这些字段位于 `opencode.json` → `providers` → 对应 Provider → `settings`。

## 填写后启动

1. 若你自己的 OpenCode 服务正在运行，在它所在终端 Ctrl+C 停止后重新启动；不需要升级版本。没有运行则直接执行：

```powershell
cd D:\fkg-agent\gitlab-fkg-agent
opencode serve --hostname 127.0.0.1 --port 4096
```

2. 将本次 OpenCode 服务密码填进项目 `.env` 的 `OPENCODE_PASSWORD=`；它与模型 API Key 是两回事。若尚无 .env，只在不存在时从 .env.example 复制；已有文件不要覆盖。
3. 新 PowerShell 窗口运行：

```powershell
cd D:\fkg-agent\gitlab-fkg-agent
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

4. 打开 http://127.0.0.1:8765 → 运行配置 → 读取 OpenCode 可用模型，应核对上表两个 providerID/id。
5. 应用默认数据目录 `data` 中的两模型映射已写入；预算和超时等其他已有设置保留。界面若已有缓存，刷新页面。若使用了自定义 FKG_DATA_DIR，可运行下面命令把映射写到同一个数据目录：

```powershell
.\.venv\Scripts\python.exe scripts\configure_models.py --data-dir '实际的数据目录'
```

默认目录可直接运行 `scripts/configure_models.py`，脚本保留已有密钥内容，不覆盖其他 Provider；若同名 Provider 被修改会拒绝覆盖，要求手工合并。

注意：`scripts/configure_opencode.py` 现已支持保留 providers；仍不要在未检查差异时随意使用 --refresh。换 Python 环境后如需重新生成 Agent/MCP，先检查备份和差异。

## 首次联调

先用小范围真实文档，分别检查连接、实际模型、工具调用、候选校验；确认成功后再执行全量任务或 E1—E4。本次仅配置文件和离线验证，没有发出推理请求、没有消耗模型额度。

预计协议会分别拼接 `/chat/completions` 与 `/responses`。如遇 401/403，优先检查密钥/账号权限；404 检查完整接口 URL/模型 ID；400 检查协议与支持参数。不会在错误后静默切成其他模型或把 Responses 改成 Chat。
