"""
AnythingLLM MCP Server - MVP
工具：通过 AnythingLLM 工作区提取信息并进行 AI 回答
传输协议：HTTP (streamable-http)
协议版本：MCP 2026-07-28 (via mcp 2.x SDK)
"""
import os
import httpx
from mcp.server.mcpserver import MCPServer

# ===== 配置 =====
ANYTHINGLLM_BASE_URL = os.environ.get("ANYTHINGLLM_BASE_URL", "http://localhost:3001")
ANYTHINGLLM_API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "JDHNTAP-MM44XG8-J2CWF2K-QESF6TP")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))

mcp = MCPServer("AnythingLLM")


@mcp.tool()
async def anythingllm_chat(workspace_slug: str, message: str) -> str:
    """通过 AnythingLLM 工作区提取信息并回答问题。

    Args:
        workspace_slug: 工作区的 slug 标识
        message: 要向工作区提问的问题
    """
    url = f"{ANYTHINGLLM_BASE_URL}/api/v1/workspace/{workspace_slug}/chat"
    headers = {
        "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"message": message, "mode": "query"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    answer = data.get("textResponse", "(无回复)")
    sources = data.get("sources", [])
    if sources:
        lines = ["\n\n--- 来源 ---"]
        for i, s in enumerate(sources, 1):
            lines.append(f"{i}. [{s.get('title', '')}] {s.get('url', '')}")
        answer += "\n".join(lines)

    return answer


@mcp.tool()
async def anythingllm_list_workspaces() -> str:
    """列出所有 AnythingLLM 工作区及其 slug。"""
    url = f"{ANYTHINGLLM_BASE_URL}/api/v1/workspaces"
    headers = {"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    workspaces = data.get("workspaces", [])
    if not workspaces:
        return "(没有工作区)"
    lines = ["工作区列表:"]
    for w in workspaces:
        lines.append(f"- {w.get('name')} | slug: {w.get('slug')}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=MCP_HOST, port=MCP_PORT)
