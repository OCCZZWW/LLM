# AnythingLLM MCP Server

基于 Python + MCP 2.x SDK 开发的 AnythingLLM MCP Server MVP 版本。
通过 HTTP (streamable-http) 传输协议，暴露工作区问答工具。

## 工具列表

| 工具名 | 描述 |
|---|---|
| `anythingllm_chat` | 向指定工作区提问，返回 AI 回答及来源文档 |
| `anythingllm_list_workspaces` | 列出所有工作区及其 slug |

## 环境要求

- Python 3.10+（已测试 3.13）
- AnythingLLM Desktop 运行在 `http://localhost:3001`
- AnythingLLM API Key

## 配置

配置方式一：修改 `server.py` 顶部常量：

```python
ANYTHINGLLM_BASE_URL = "http://localhost:3001"
ANYTHINGLLM_API_KEY = "你的API_KEY"
MCP_HOST = "127.0.0.1"
MCP_PORT = 8765
```

配置方式二：使用环境变量覆盖：

```powershell
$env:ANYTHINGLLM_API_KEY = "你的API_KEY"
$env:MCP_PORT = "8765"
```

## 安装

```powershell
cd D:\Downloads\python\MCPServer
python -m venv .venv
.\.venv\Scripts\pip install mcp httpx
```

## 启动

```powershell
cd D:\Downloads\python\MCPServer
.\.venv\Scripts\python.exe server.py
```

输出示例：

```
INFO:     Uvicorn running on http://127.0.0.1:8765
```

MCP 端点：`http://127.0.0.1:8765/mcp`

## 停止

在终端中按 `Ctrl+C` 停止服务。

或查找并终止进程：

```powershell
Get-NetTCPConnection -LocalPort 8765 | Select OwningProcess
Stop-Process -Id <PID>
```

## Trae 项目级 MCP 配置

项目根目录下 `.trae/mcp.json` 已自动创建：

```json
{
  "mcpServers": {
    "anythingllm": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

在 Trae 中启用：**设置 → MCP → 打开"启用项目级 MCP"开关**。

## 测试 MCP 端点

```powershell
# 初始化会话（获取 Mcp-Session-Id）
$initResp = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8765/mcp" `
  -Method Post -ContentType "application/json" `
  -Headers @{Accept="application/json, text/event-stream"} `
  -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-07-28","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# 列工具
$sessionId = $initResp.Headers["Mcp-Session-Id"]
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8765/mcp" `
  -Method Post -ContentType "application/json" `
  -Headers @{Accept="application/json, text/event-stream"; "Mcp-Session-Id"=$sessionId} `
  -Body '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

## 文件结构

```
MCPServer/
├── .trae/mcp.json      # 项目级 MCP 配置
├── .venv/              # Python 虚拟环境
├── server.py           # MCP Server 入口
├── requirements.txt    # 依赖
└── README.md           # 本文档
```
