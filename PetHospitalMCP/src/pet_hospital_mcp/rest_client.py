"""REST 客户端：封装对 Go 宠物医院 API 的异步 HTTP 调用。

只暴露一个 list_pets 方法，严格适配 GET /api/v1/pets 的查询参数。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

import httpx

from .config import Settings
from .errors import ErrorCode, MCPToolError

logger = logging.getLogger("pet_hospital_mcp.rest")


# Go API 允许的枚举值 —— 与 model.go / api.go 对齐
VALID_SPECIES = {"犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"}
VALID_STATUS = {"待就诊", "就诊中", "住院中", "已康复", "慢性病随访"}
VALID_SORT_BY = {
    "id", "name", "ownerName", "species", "doctor",
    "disease", "status", "totalCost", "visitCount",
    "createdAt", "updatedAt",
}
VALID_ORDER = {"asc", "desc"}


class PetHospitalError(Exception):
    """REST 客户端底层错误的中间态，用于区分 MCP 工具错误。"""


class PetHospitalClient:
    """对 Go 宠物医院 REST API 的薄封装。"""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.pet_hospital_base_url.rstrip("/")
        self.timeout = settings.request_timeout
        self.max_retries = settings.max_retries
        self.retry_backoff = settings.retry_backoff
        # 测试时可通过 httpx.MockTransport 注入 transport
        self._http_client: httpx.AsyncClient | None = None
        self._transport: httpx.BaseTransport | None = None

    def with_transport(self, transport: httpx.BaseTransport) -> "PetHospitalClient":
        """注入一个 MockTransport，供测试使用。"""
        self._transport = transport
        return self

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发起一次 GET 请求，带有限重试。"""
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            client = self._make_client()
            try:
                async with client:
                    resp = await client.get(url, params=params or {}, timeout=self.timeout)
                    if resp.status_code >= 500:
                        # 5xx 触发重试
                        last_exc = MCPToolError(
                            ErrorCode.BACKEND_API_ERROR,
                            f"上游返回 {resp.status_code}",
                            {"status_code": resp.status_code, "body": resp.text[:500]},
                        )
                    else:
                        # 非 5xx 不重试：业务错误立刻向上抛
                        return self._unwrap(resp)
            except httpx.TimeoutException as exc:
                last_exc = MCPToolError(
                    ErrorCode.BACKEND_TIMEOUT,
                    f"请求超时: {exc}",
                    {"url": url, "timeout": self.timeout},
                )
            except httpx.ConnectError as exc:
                last_exc = MCPToolError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"上游不可达: {exc}",
                    {"url": url},
                )
            except httpx.RequestError as exc:
                last_exc = MCPToolError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"网络错误: {exc}",
                    {"url": url},
                )

            # 重试前等一下
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff * (2 ** attempt))

        assert last_exc is not None
        raise last_exc

    def _make_client(self) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport)
        return httpx.AsyncClient()

    def _unwrap(self, resp: httpx.Response) -> dict[str, Any]:
        """解析 Go 统一响应信封：{code, message, data, time}。"""
        try:
            envelope = resp.json()
        except ValueError as exc:
            raise MCPToolError(
                ErrorCode.BACKEND_INVALID_RESPONSE,
                f"上游返回的不是合法 JSON: {exc}",
                {"body": resp.text[:500]},
            ) from exc

        code = envelope.get("code")
        if code is None:
            # 没信封 —— 直接把整个 JSON 当 data（防御性）
            return envelope

        if resp.status_code >= 400 or (isinstance(code, int) and code >= 400):
            raise MCPToolError(
                ErrorCode.BACKEND_API_ERROR,
                envelope.get("message") or f"上游返回 {resp.status_code}",
                {"status_code": resp.status_code, "code": code, "body": envelope},
            )

        return envelope.get("data") or {}

    # ------------------------------------------------------------------
    # 工具暴露的业务方法
    # ------------------------------------------------------------------

    async def list_pets(
        self,
        *,
        q: str | None = None,
        name: str | None = None,
        owner_name: str | None = None,
        owner_phone: str | None = None,
        species: str | None = None,
        doctor: str | None = None,
        disease: str | None = None,
        status: str | None = None,
        min_cost: float | None = None,
        max_cost: float | None = None,
        sort_by: str | None = None,
        order: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """GET /api/v1/pets —— 严格转发到 Go REST API。"""
        params = self._build_params(
            q=q,
            name=name,
            ownerName=owner_name,
            ownerPhone=owner_phone,
            species=species,
            doctor=doctor,
            disease=disease,
            status=status,
            min=min_cost,
            max=max_cost,
            sortBy=sort_by,
            order=order,
            page=page,
            pageSize=page_size,
        )
        return await self._get("/api/v1/pets", params)

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        try:
            return await self._get("/health")
        except MCPToolError:
            return {"status": "unhealthy"}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _build_params(**kwargs: Any) -> dict[str, Any]:
        """过滤掉 None 值，只保留 Go API 接受的查询参数。"""
        return {
            k: v for k, v in kwargs.items()
            if v is not None and v != ""
        }
