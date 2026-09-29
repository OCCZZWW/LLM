"""MCP Server 装配 —— 使用 MCPServer + Streamable HTTP。

MCP 2026-07-28 无状态模式：
- 不需要 initialize 握手
- 不需要 Mcp-Session-Id
- 每个请求自包含 protocol version
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from mcp.server import MCPServer

from .config import Settings, get_settings
from .logging_config import setup_logging, redact_sensitive
from .rest_client import PetHospitalClient
from .tools.list_pets import (
    ListPetsInput,
    ListPetsOutput,
    execute_list_pets,
)

setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("pet_hospital_mcp.server")


# ---------------------------------------------------------------------------
# 工厂函数 —— 方便测试注入 client
# ---------------------------------------------------------------------------

def create_server(
    settings: Settings | None = None,
    client: PetHospitalClient | None = None,
) -> MCPServer:
    """构造 MCPServer，注册所有工具。

    通过闭包注入 client，测试时可传入 MockTransport 的 client。
    """
    settings = settings or get_settings()
    rest_client = client or PetHospitalClient(settings)

    mcp = MCPServer(
        name="Pet Hospital",
        version="0.1.0",
        description=(
            "宠物医院 MCP 服务。"
            "通过 list_pets 工具查询本地宠物医院管理系统的档案数据。"
        ),
    )

    # -----------------------------------------------------------------------
    # 工具：list_pets
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def list_pets(
        q: str | None = None,
        name: str | None = None,
        ownerName: str | None = None,
        ownerPhone: str | None = None,
        species: str | None = None,
        doctor: str | None = None,
        disease: str | None = None,
        status: str | None = None,
        min: float | None = None,
        max: float | None = None,
        sortBy: str | None = None,
        order: str | None = None,
        page: int = 1,
        pageSize: int = 20,
    ) -> ListPetsOutput:
        """查询宠物医院档案列表（GET /api/v1/pets）。

        适用场景：
        - 浏览/搜索全部宠物档案（可过滤、排序、分页）
        - 按主人姓名/电话查找宠物
        - 按医生查看接诊宠物
        - 按疾病、就诊状态筛选
        - 查看消费金额区间、消费排行榜

        参数:
            q: 全文检索关键词（跨字段 AND 匹配，空格分词）
            name: 宠物姓名模糊匹配
            ownerName: 主人姓名模糊匹配
            ownerPhone: 主人电话模糊匹配
            species: 种类枚举: 犬/猫/兔/鸟/仓鼠/爬宠/其他
            doctor: 医生姓名模糊匹配
            disease: 疾病模糊匹配
            status: 状态枚举: 待就诊/就诊中/住院中/已康复/慢性病随访
            min: 总花费下限（非负）
            max: 总花费上限（非负，需 >= min）
            sortBy: 排序字段: id/name/ownerName/species/doctor/disease/status/totalCost/visitCount/createdAt/updatedAt
            order: 升序 asc / 降序 desc
            page: 页码（>=1，默认 1）
            pageSize: 每页条数（1-500，默认 20）

        返回:
            结构化分页结果，包含 items（宠物档案列表）、total、page、pageSize、totalPages、totalCost。
            每只档案含 records/charges 子数组（可能为空或 null）。
        """
        return await execute_list_pets(
            rest_client,
            q=q,
            name=name,
            ownerName=ownerName,
            ownerPhone=ownerPhone,
            species=species,
            doctor=doctor,
            disease=disease,
            status=status,
            min=min,
            max=max,
            sortBy=sortBy,
            order=order,
            page=page,
            pageSize=pageSize,
        )

    return mcp


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------

def _check_backend_health(settings: Settings) -> None:
    """同步健康检查，避免 asyncio 事件循环冲突。"""
    try:
        resp = httpx.get(
            f"{settings.pet_hospital_base_url.rstrip('/')}/health",
            timeout=settings.request_timeout,
        )
        if resp.status_code == 200:
            logger.info("backend health check passed")
        else:
            logger.warning(f"backend health check failed: HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning(f"backend health check failed: {exc}")


def run(settings: Settings | None = None) -> None:
    """同步入口，由 __main__ 或 CLI 调用。

    mcp.run() 内部会自己启动 anyio 事件循环，不需要 asyncio.run() 包装。
    """
    settings = settings or get_settings()

    # 先跑一次健康检查，确认上游可达（同步，避免嵌套事件循环）
    _check_backend_health(settings)

    mcp = create_server(settings)

    logger.info("starting Pet Hospital MCP server", extra={
        "mcp_host": settings.mcp_host,
        "mcp_port": settings.mcp_port,
        "mcp_path": settings.mcp_path,
        "backend": settings.pet_hospital_base_url,
        "protocol_version": "2026-07-28",
    })

    mcp.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path=settings.mcp_path,
        json_response=False,
        stateless_http=True,
    )
