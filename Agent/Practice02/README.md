# Practice02 — Function Calling Agent

基于 Ollama 本地大模型的 function calling 智能 Agent，支持 **12 个工具**，包括通用能力和完整的本地文件操作。

## 架构

```mermaid
flowchart TB
    User["👤 用户"]
    Main["主循环<br>while True"]
    StreamChat["stream_chat()<br>通信层"]
    Ollama["🦙 Ollama<br>qwen3-vl:4b-instruct<br>/v1/chat/completions"]

    subgraph 工具层["🧰 工具层"]
        direction LR
        subgraph 通用工具["通用工具 (2)"]
            GetDate["getDate"]
            LeapYear["isLeapYear"]
        end
        subgraph 文件工具["文件操作 (10)"]
            direction TB
            subgraph 查看["查看类"]
                GetCwd["getCwd"]
                ListDir["listDir"]
                GetFileType["getFileType"]
                ReadFile["readFile"]
            end
            subgraph 创建["创建类"]
                CreateFile["createFile"]
                CreateDir["createDir"]
            end
            subgraph 修改["修改类"]
                WriteFile["writeFile"]
                RenamePath["renamePath"]
            end
            subgraph 删除["删除类"]
                DeleteFile["deleteFile"]
                DeleteDir["deleteDir"]
            end
        end
    end

    subgraph 基础设施["🔧 基础设施"]
        direction LR
        Resolve["_resolve()<br>路径解析"]
        IsText["_is_text_file()<br>文本探测"]
        ToolMap["TOOL_MAP<br>注册表"]
        StdLib["os · shutil ·<br>subprocess · json"]
    end

    User -->|input()| Main
    Main -->|messages.append| StreamChat
    StreamChat -->|POST stream| Ollama
    Ollama -->|SSE 流式响应| StreamChat
    StreamChat -->|返回 text + tool_calls| Main
    Main -->|检测到 tool_calls| ExecuteTools["执行工具循环"]
    ExecuteTools -->|TOOL_MAP 查表| 工具层
    工具层 --> Resolve
    工具层 --> IsText
    工具层 --> StdLib
    ExecuteTools -->|追加 tool 消息| StreamChat
    StreamChat -->|final_text| Main
```

> 同一份图的纯文本版见 [architecture.mmd](./architecture.mmd)。

## 运行

```powershell
cd Practice02
python chat.py
```

**前置条件**：Ollama 在 `localhost:11434` 运行，且已拉取 `qwen3-vl:4b-instruct` 模型。

## 代码结构

| 行号 | 模块 | 说明 |
|------|------|------|
| 1–15 | 配置 | `OLLAMA_URL` + `OLLAMA_MODEL`，直接对接 Ollama OpenAI 兼容端点 |
| 17–206 | `TOOLS` | 12 个工具的 OpenAI function calling schema 定义 |
| 211–255 | 通用工具实现 | `get_date()` + `is_leap_year()` |
| 261–473 | 文件操作实现 | 10 个文件/目录工具，基于 `os` / `shutil` / `subprocess` |
| 476–491 | `TOOL_MAP` | 工具名 → Python 函数的注册表，主循环靠它分发调用 |
| 497–575 | `stream_chat()` | 通信层：POST 到 Ollama，流式解析 SSE，累积文本和 `tool_calls` 增量 |
| 581–623 | 主循环 | 多轮对话 + 工具调用 + 消息历史管理 |

## 工具清单

### 通用工具

| 工具 | 描述 | 实现 |
|------|------|------|
| `getDate` | 获取当前日期和时间 | Windows: `cmd /c date /t` + `time /t`；其他: `datetime` |
| `isLeapYear` | 判断闰年 | `(y%4==0 and y%100!=0) or y%400==0` |

### 文件操作（10 个）

| 分类 | 工具 | 参数 | 能力 |
|------|------|------|------|
| 查看 | `getCwd` | — | 当前工作目录 |
| | `listDir` | `path?`, `recursive?` | 列出目录内容 |
| | `getFileType` | `path` | 扩展名、MIME、是否文本 |
| | `readFile` | `path`, `encoding?` | 读取纯文本（自动 fallback utf-8/gbk/utf-16） |
| 创建 | `createFile` | `path`, `content?` | 创建文件（自动建父目录） |
| | `createDir` | `path` | 递归创建目录（mkdir -p） |
| 修改 | `writeFile` | `path`, `content`, `append?` | 覆盖或追加写入，拒绝二进制 |
| | `renamePath` | `path`, `new_name` | 同目录重命名 |
| 删除 | `deleteFile` | `path` | 删除文件 |
| | `deleteDir` | `path` | 非空目录一并删除，根目录保护 |

## 对话流程

```
用户输入 "创建 docs 目录，写一个 README.md"
        │
        ▼
┌─ 主循环 ──────────────────────────────────┐
│  messages.append(user)                     │
│  stream_chat(messages, tools=TOOLS) ──────┤──→ Ollama
│                                              │
│  Ollama 返回: tool_calls=[createDir,        │
│               createFile] + 空文本          │
│                                              │
│  ── 执行工具 ──────────────────────────     │
│  for tc in tool_calls:                      │
│      fn = TOOL_MAP[tc.name]                 │
│      result = fn(**tc.args)                 │
│      messages.append(tool, result)          │
│                                              │
│  stream_chat(messages, tools=None) ────────┤──→ Ollama (第二轮，无 tools)
│                                              │
│  Ollama 返回自然语言总结                     │
└──────────────────────────────────────────────┘
```

## 与 Practice01 的差异

| 项 | Practice01 | Practice02 |
|---|---|---|
| LLM 后端 | AnythingLLM wrapper | **Ollama 原生 API** |
| 端点 | `/v1/workspace/{slug}/stream-chat` | `/v1/chat/completions` (OpenAI 格式) |
| Function Calling | ❌ 不转发 tools 参数 | ✅ 完整支持 |
| 工具数 | 0 | **12** |
| 配置方式 | config.ini | 硬编码常量（无外部依赖） |
| 历史格式 | AnythingLLM history 列表 | OpenAI messages 列表 |
