# 宠物医院 MCP Server 项目报告

> 基于 Go REST API 的 MCP 2026-07-28 无状态适配器开发纪实
> 
> 时间：2026-09-16

---

## 一、项目背景

### 1.1 现有系统

仓库根目录是一个纯 Go 实现的宠物医院管理系统（`Pet Hospital REST`）：

- **零第三方依赖**，只用 Go 标准库
- **单文件嵌入式数据库**：`pet.db`（追加日志 + 内存索引 + 自动压实）
- **REST API**：`http://127.0.0.1:8080`，统一响应信封 `{code, message, data, time}`
- **健康检查**：`GET /health`
- **核心接口**：`GET /api/v1/pets`（支持全文检索、枚举过滤、分页、排序、花费区间）
- **数据模型**：`Pet` 聚合根，内嵌 `records[]`（历史病历）与 `charges[]`（消费明细），`records`/`charges` 字段可能是 `null` 或数组

### 1.2 任务目标

为这个 Go 后端开发一个独立的 **MCP Server**，把它的能力暴露给 LLM Agent。约束条件：

| 约束 | 说明 |
|---|---|
| **MCP 协议版本** | `2026-07-28`（刚发布 2 个月的大版本重构） |
| **Python SDK** | `mcp==2.0.0`（与协议同日发布） |
| **Server 类** | `MCPServer`（禁止使用 `FastMCP`） |
| **传输模式** | Streamable HTTP，**无状态** |
| **仅实现** | 第一阶段只做一个工具 `list_pets`（对应 `GET /api/v1/pets`） |
| **不修改** | 不触碰 Go 后端一行代码 |
| **测试** | `pytest` + `httpx.MockTransport`，禁止访问真实 Go 服务 |
| **部署要求** | 本地 `127.0.0.1`，无 CORS、无鉴权 |

### 1.3 为什么难

- `2026-07-28` 是一次**从根上重构**的 MCP 版本，大量 1.x 教程/博客/AI 训练数据都是旧协议的（`initialize` 握手、`Mcp-Session-Id`、有状态 SSE），几乎等于在"全网错误信息"里找正确路径
- 任务里写死了**"不要凭旧版 FastMCP 经验猜测新 API"**，意味着必须自己啃官方文档，不能套套路
- `MCPServer` vs `FastMCP` 的 API 表面差异不小，测试时 SDK 的行为也有微妙变化

---

## 二、技术方案

### 2.1 整体架构

```
┌──────────────────────────────────────────────────┐
│         MCP Client (Trae / Cursor / curl)         │
└───────────────────┬──────────────────────────────┘
                    │ POST /mcp  (Streamable HTTP 2026-07-28)
                    │ 无 initialize 握手，无 Session-Id
                    ▼
┌──────────────────────────────────────────────────┐
│  pet_hospital_mcp (Python 3.11+, mcp==2.0.0)     │
│                                                    │
│  server.py  ──▶  @mcp.tool() 装饰器               │
│                     │                              │
│                     ▼                              │
│                execute_list_pets()                 │
│                     │                              │
│                     ▼                              │
│              Pydantic Input/Output                 │
│                     │                              │
│                     ▼                              │
│         rest_client.PetHospitalClient              │
│                     │                              │
│              httpx.AsyncClient                     │
│                     │                              │
└─────────────────────┼──────────────────────────────┘
                      │ HTTP GET /api/v1/pets?params...
                      ▼
        ┌──────────────────────────────────┐
        │  Go REST API  (127.0.0.1:8080)   │
        │  pet.db 嵌入式单文件数据库       │
        └──────────────────────────────────┘
```

### 2.2 目录结构

```
pet-hospital-mcp/
├── pyproject.toml                     # 依赖固定 mcp==2.0.0
├── .venv/                              # 虚拟环境（Python 3.13）
├── src/pet_hospital_mcp/
│   ├── __init__.py
│   ├── __main__.py                     # CLI 入口
│   ├── config.py                       # Settings dataclass + get_settings()
│   ├── errors.py                       # MCPToolError + ErrorCode 枚举
│   ├── logging_config.py               # JSON logger + 敏感字段脱敏
│   ├── rest_client.py                  # httpx 封装 + 超时 + 重试 + MockTransport 注入
│   ├── server.py                       # MCPServer 装配 + run() 启动
│   └── tools/
│       ├── __init__.py
│       └── list_pets.py                # 工具实现 + Pydantic Input/Output 模型
└── tests/
    ├── conftest.py                     # src/ 加入 sys.path
    └── test_list_pets.py               # 29 个用例
```

### 2.3 关键设计决策

| 决策 | 理由 |
|---|---|
| **Pydantic 输入校验** — `ConfigDict(extra="forbid")` | 防止 Go 私有字段泄漏进 MCP，拒绝未知参数 |
| **枚举字段硬编码字面量**（`Literal["犬","猫",...]`） | 任务要求严格对齐 Go API 的允许值 |
| **重试用 `asyncio.sleep` + 指数退避** | 5xx 触发重试，4xx 直接抛，mock 测试里不需要真实 sleep |
| **错误格式统一** `{error: {code, message, details}}` | 6 种 ErrorCode 覆盖 VALIDATION / BACKEND_* / INTERNAL |
| **日志脱敏** — `redact_sensitive()` 递归处理 dict/list | `ownerPhone`/`ownerAddr`/`chipNo` 自动替换为 `[REDACTED]` |
| **`rest_client.with_transport()` 注入 MockTransport** | 测试零网络依赖，完全隔离 |
| **`mcp.run()` 不嵌套 `asyncio.run()`** | SDK 内部自己用 `anyio.run()`，外层包会触发 "Already running asyncio" |

---

## 三、遇到的问题与难点

### 问题 1：MCP 2026-07-28 协议与 SDK 文档稀缺

**现象**：
- 全网绝大多数 MCP 教程和示例代码写的是旧协议（2025-03-26 或更早）
- 2026-07-28 的最大变化是**去掉了 initialize 握手和 Mcp-Session-Id**，改为每个请求自包含 protocol version 和 capabilities
- SDK 2.0.0 与协议同日发布，文档少、AI 训练数据基本没有覆盖

**根因**：协议做了"从根上重构"，旧知识反而是噪声。

**解决方法**：
- 直接读官方 `py.sdk.modelcontextprotocol.io` 的文档（只有 `MCPServer`、没有 `FastMCP`）
- 看 SDK 源码的 CLI 示例：`mcp.run(transport="streamable-http")` 一行就能起，**没有** `session_id`、**没有** `initialize`
- 实测发现 SDK 2.x 要求 `params._meta` 必须携带：
  ```json
  "_meta": {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {}
  }
  ```
  否则返回 `{"code": -32602, "message": "params._meta must be an object carrying the required ..."}`

---

### 问题 2：Python 和 Go 都没装

**现象**：
- 一开始机器上**没有 Go 也没有 Python 命令**（PATH 里找不到）
- 最后发现 Anaconda 安装在 `D:\Downloads\Anaconda3`，Go 需要新装

**解决方法**：
- Go：`winget install --id GoLang.Go` → 装到 `C:\Program Files\Go`
- Python：用 Anaconda 自带的 `python.exe`，但全局 PATH 里没挂，所有调用都得写完整路径 `D:\Downloads\Anaconda3\python.exe`
- pip 全局安装时遇到沙箱权限拒绝（EPERM），改为**项目内虚拟环境**：`python -m venv .venv` + 用 `.venv\Scripts\pip.exe`

---

### 问题 3：Settings dataclass 没有默认值导致测试全炸

**现象**：
- `Settings` 最初写的是 `@dataclass(frozen=True)` 且所有字段没有默认值
- 测试里写 `Settings(pet_hospital_base_url="http://fake")` 会报错：
  ```
  TypeError: Settings.__init__() missing 7 required positional arguments: 'mcp_host', 'mcp_port', ...
  ```
- 一次性炸掉 12 个测试（夹具共享同一个 Settings 写法）

**根因**：写 dataclass 时忘了给默认值，只写了 `get_settings()` 里读取环境变量的版本。

**解决方法**：把所有字段补上默认值（与 `get_settings()` 里的环境变量回退值一致），测试里可以覆盖任何字段，生产环境用 `get_settings()`。

---

### 问题 4：Python 闭包变量遮蔽 — `UnboundLocalError`

**现象**：
- `make_error_handler(status, body=None)` 里写：
  ```python
  async def handler(request):
      if body is None:
          body = {...}  # 闭包变量被重新赋值 → 变成局部变量
      return httpx.Response(status, json=body)
  ```
- 调用 `make_error_handler(400)` 时，`body=None` 进入内部函数，但因为 `if body is None: body = ...` 这行，Python 把 `body` 识别为 handler 的**局部变量** → 在赋值前就访问 → `UnboundLocalError`

**根因**：Python 闭包里对外部变量的重新赋值会让它变成局部变量，handler 里 `if body is None` 触发了遮蔽。

**解决方法**：把默认值计算移到闭包外面，用不同变量名：
```python
def make_error_handler(status, custom_body=None):
    _body = custom_body if custom_body is not None else {"code": status, ...}
    async def handler(request):
        return httpx.Response(status, json=_body)
    return handler
```

---

### 问题 5：asyncio 嵌套事件循环 — `Already running asyncio in this thread`

**现象**：
- 最初的设计是 `run_async()` 先跑一次健康检查（`await rest_client.health()`），再调 `mcp.run()`
- 外层入口写 `asyncio.run(run_async(settings))`
- 启动时报：`RuntimeError: Already running asyncio in this thread`

**根因**：`MCPServer.run()` 内部调用 `anyio.run()`，而外层 `asyncio.run()` 已经在同一线程启动了 asyncio 事件循环，anyio 检测到后直接报错。

**解决方法**：
- 把健康检查改成**同步 httpx.get()**（不走 async）
- `run()` 函数直接同步调用 `mcp.run()`，**不再**包 `asyncio.run()`
- 完整重构后的 `run()` 函数只做三件事：同步健康检查 → 创建 server → `mcp.run(transport="streamable-http", ...)`

---

### 问题 6：MockTransport 不真正超时

**现象**：
- 写了 `async def slow_handler(): await asyncio.sleep(0.5)` + `request_timeout=0.05`
- 测试期望 `BACKEND_TIMEOUT`，但始终没有触发

**根因**：`httpx.MockTransport` 不经过真正的网络栈，`AsyncClient(timeout=...)` 的超时机制在 MockTransport 下**不会生效** —— 因为没有 `asyncio.wait_for` 包裹真实 socket 操作。

**解决方法**：让 handler 直接 `raise httpx.TimeoutException("request timed out", request=request)`，在 client 的重试逻辑里已经统一捕获 `httpx.TimeoutException` 并转为 `MCPToolError(BACKEND_TIMEOUT)`。

---

### 问题 7：SDK 2.x 里 `inputSchema` 改名了

**现象**：
- 测试里写 `tool.inputSchema`，得到 `AttributeError: 'Tool' object has no attribute 'inputSchema'. Did you mean: 'input_schema'?`

**根因**：SDK 从 `1.x` 升级到 `2.x` 时，Pydantic 模型的 snake_case 自动命名生效，`inputSchema` → `input_schema`。这是**跨版本 API 改名**的典型陷阱。

**解决方法**：改成 `tool.input_schema`。

---

### 问题 8：`stateless_http=True` 但 SDK 仍要求 `params._meta`

**现象**：
- 以为无状态模式会"什么都不传"，实际 SDK 2.x 在 2026-07-28 协议下仍然**强制校验**每个请求的 `params._meta` 携带 protocol version 和 client capabilities
- 直接发 `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}` → `400` + JSON-RPC `-32602` 错误

**解决方法**：在测试和手动验证里都带上正确的 `_meta`：
```python
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}
```
SDK 的 `Client(mcp_server)` 在内存模式下会自动注入，所以 MCP 层测试里不需要手动写；但用 httpx 直接发 HTTP 请求时必须手动带上。

---

## 四、解决方案汇总

| 问题 | 类型 | 根因 | 修复 |
|---|---|---|---|
| 2026-07-28 协议文档稀缺 | 知识缺口 | 协议大重构 + SDK 同步发布 | 读官方 docs + 实测 `params._meta` 必须字段 |
| 环境没装 Go / Python | 环境 | 新机器 PATH 没配 | `winget` + 项目内 venv |
| Settings 无默认值 | 代码失误 | dataclass 字段漏 `=` | 全部补默认值 |
| 闭包变量遮蔽 | Python 陷阱 | 闭包内重新赋值 → 局部变量 | 闭包外计算默认值，换变量名 |
| asyncio 嵌套循环 | 架构问题 | `mcp.run()` 内部 anyio | 同步健康检查 + 直接调 `mcp.run()` |
| MockTransport 不真正超时 | httpx 行为 | Mock 不走网络栈 | 手动 `raise TimeoutException` |
| `inputSchema` → `input_schema` | SDK 改名 | snake_case 自动生效 | 改字段名 |
| `params._meta` 强制校验 | 协议细节 | 2026-07-28 规范要求 | 手动注入或用 SDK Client |

---

## 五、最终成果

### 5.1 测试结果

```
29 passed in 0.89s
```

覆盖：输入校验 12 个用例 + 工具执行路径 10 个用例 + MCP 注册/协议验证 7 个用例。

### 5.2 服务状态

| 组件 | 状态 | 地址 |
|---|---|---|
| Go REST API | ✅ 运行中 | `http://127.0.0.1:8080` |
| MCP Server | ✅ 运行中 | `http://127.0.0.1:8000/mcp` |
| 协议版本 | 2026-07-28 | — |
| 工具数 | 1（`list_pets`） | — |

### 5.3 MCP Client 配置

```json
{
  "mcpServers": {
    "pet-hospital": {
      "type": "streamablehttp",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### 5.4 MCP HTTP 请求模板

```bash
# 列出工具
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/list" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list",
       "params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
                         "io.modelcontextprotocol/clientCapabilities":{}}}}'

# 调用 list_pets（过滤犬类 + 花费降序）
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2026-07-28" \
  -H "Mcp-Method: tools/call" \
  -H "Mcp-Name: list_pets" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"list_pets",
                "arguments":{"species":"犬","sortBy":"totalCost","order":"desc","pageSize":3},
                "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
                         "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

---

## 六、经验总结

1. **协议大版本升级期间，全网旧知识都是噪声** — 必须读官方文档 + 实测行为，不能凭印象
2. **`MCPServer` vs `FastMCP`**：前者是 SDK 2.x 的底层类，后者是独立项目；本次用 `MCPServer` 因为任务明确禁止 `FastMCP`
3. **`mcp.run()` 自己管事件循环，别包外层** — 这是 anyio 架构决定的，SDK 文档里提到了但很容易忽略
4. **闭包内重新赋值外部变量会遮蔽** — Python 经典坑，测试里不小心就踩
5. **MockTransport 不等于真实网络** — 想测超时/连接错误，手动 `raise` 比 `sleep` 更可控
6. **Pydantic 字段名自动 snake_case** — SDK 从 1.x 升到 2.x 后，`inputSchema` 变成了 `input_schema`，这是跨版本升级的典型改名陷阱
7. **`2026-07-28` 无状态 ≠ 完全无 meta** — 协议从"每个请求自包含 version"的方向走，但 `params._meta` 这个自包含字段反而变成了**必填**

---

## 七、后续工作（阶段二，尚未启动）

任务明确说"本次只保留一个 MCP 工具"，以下是后续可能的扩展方向（尚未实现）：

| 可能的新工具 | 对应 Go API |
|---|---|
| `create_pet` | `POST /api/v1/pets` |
| `get_pet` | `GET /api/v1/pets/{id}` |
| `update_pet` | `PUT /api/v1/pets/{id}` |
| `delete_pet` | `DELETE /api/v1/pets/{id}` |
| `search_pets` | `GET /api/v1/pets/search` |
| `list_records` | `GET /api/v1/pets/{id}/records` |
| `add_record` | `POST /api/v1/pets/{id}/records` |
| `add_charge` | `POST /api/v1/pets/{id}/charges` |
| `pet_summary` | `GET /api/v1/pets/{id}/summary` |
| `hospital_stats` | `GET /api/v1/stats` |
| `export_pets` | `GET /api/v1/export` |
| `seed_demo_data` | `POST /api/v1/admin/seed` |

每个新工具按目录约定，只需在 `src/pet_hospital_mcp/tools/` 增加一个模块、在 `server.py` 注册装饰器、在 `rest_client.py` 增加一个方法 —— 其他基础设施（错误、日志、脱敏、重试）全部复用。

---

*报告完毕。29 个测试通过，Go + MCP 双服务在线，`list_pets` 工具端到端可用。*
