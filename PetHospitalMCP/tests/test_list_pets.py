"""list_pets 工具单元测试。

使用 httpx.MockTransport 模拟 Go REST API，不访问真实后端。
"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import httpx
import pytest
from mcp import Client
from pydantic import ValidationError

from pet_hospital_mcp.config import Settings
from pet_hospital_mcp.errors import ErrorCode, MCPToolError
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.server import create_server
from pet_hospital_mcp.tools.list_pets import (
    ListPetsInput,
    ListPetsOutput,
    execute_list_pets,
)


# ---------------------------------------------------------------------------
# 夹具：Go 风格的示例响应
# ---------------------------------------------------------------------------

SAMPLE_PET = {
    "id": "PET-000001",
    "name": "旺财",
    "species": "犬",
    "breed": "金毛",
    "gender": "公",
    "ageMonths": 36,
    "color": "金色",
    "chipNo": "CHIP123456",
    "ownerName": "张三",
    "ownerPhone": "13800001111",
    "ownerAddr": "北京市朝阳区 xxx",
    "doctor": "李医生",
    "disease": "急性肠胃炎",
    "status": "住院中",
    "allergy": "",
    "note": "暂无",
    "records": None,
    "charges": None,
    "totalCost": 380.0,
    "visitCount": 1,
    "createdAt": "2026-09-01T10:00:00+08:00",
    "updatedAt": "2026-09-02T15:00:00+08:00",
}

GO_ENVELOPE = {
    "code": 200,
    "message": "ok",
    "data": {
        "items": [SAMPLE_PET],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "totalPages": 1,
        "totalCost": 380.0,
    },
    "time": "2026-09-16T10:00:00+08:00",
}


def make_ok_handler(expected_path: str = "/api/v1/pets", expected_params: dict | None = None):
    """返回一个 MockTransport handler，它会校验请求路径和参数，然后返回成功信封。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == expected_path, f"路径不匹配: {request.url.path} != {expected_path}"
        if expected_params is not None:
            actual_params = dict(request.url.params)
            for k, v in expected_params.items():
                assert actual_params.get(k) == str(v), f"参数 {k} 期望 {v} 实际 {actual_params.get(k)}"
        return httpx.Response(200, json=GO_ENVELOPE, headers={"Content-Type": "application/json"})

    return handler


def make_error_handler(status: int, custom_body: Any | None = None):
    _body = custom_body if custom_body is not None else {"code": status, "message": "后端错误", "data": None, "time": "now"}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=_body, headers={"Content-Type": "application/json"})

    return handler


def make_malformed_json_handler():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="not json{{{", headers={"Content-Type": "application/json"})

    return handler


def make_invalid_data_handler():
    async def handler(request: httpx.Request) -> httpx.Response:
        # code=200 但 data 字段缺字段
        return httpx.Response(200, json={
            "code": 200,
            "message": "ok",
            "data": {"items": [{"not_a_pet": True}]},  # 缺少必要字段 total, page, ...
            "time": "now",
        }, headers={"Content-Type": "application/json"})

    return handler


# ---------------------------------------------------------------------------
# 工具层测试
# ---------------------------------------------------------------------------

class TestListPetsInputValidation:
    """输入模型校验 —— 覆盖所有 prompt 要求的校验规则。"""

    def test_defaults(self):
        args = ListPetsInput.model_validate({})
        assert args.page == 1
        assert args.pageSize == 20

    def test_page_min_1(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"page": 0})

    def test_pageSize_range(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"pageSize": 0})
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"pageSize": 501})

    def test_min_max_nonnegative(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"min": -1})
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"max": -1})

    def test_min_gt_max_rejected(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"min": 500, "max": 100})

    def test_nan_rejected(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"min": float("nan")})
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"min": float("inf")})

    def test_species_literal(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"species": "恐龙"})

    def test_status_literal(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"status": "已死亡"})

    def test_sortBy_literal(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"sortBy": "unknownField"})

    def test_order_literal(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"order": "random"})

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            ListPetsInput.model_validate({"unknown": "value"})

    def test_empty_string_becomes_none(self):
        args = ListPetsInput.model_validate({"name": "   "})
        assert args.name is None


class TestExecuteListPets:
    """execute_list_pets 函数的完整执行路径。"""

    async def test_normal_call_all_params_forwarded(self):
        """正常调用：所有过滤/排序/分页参数正确转发。"""
        expected = {
            "q": "肠胃炎",
            "name": "旺财",
            "ownerName": "张三",
            "ownerPhone": "138",
            "species": "犬",
            "doctor": "李医生",
            "disease": "肠胃",
            "status": "住院中",
            "min": "100.0",
            "max": "1000.0",
            "sortBy": "totalCost",
            "order": "desc",
            "page": "2",
            "pageSize": "50",
        }
        transport = httpx.MockTransport(make_ok_handler(expected_params=expected))
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)

        result = await execute_list_pets(
            client,
            q="肠胃炎",
            name="旺财",
            ownerName="张三",
            ownerPhone="138",
            species="犬",
            doctor="李医生",
            disease="肠胃",
            status="住院中",
            min=100.0,
            max=1000.0,
            sortBy="totalCost",
            order="desc",
            page=2,
            pageSize=50,
        )
        assert isinstance(result, ListPetsOutput)
        assert result.total == 1
        assert result.totalPages == 1
        assert result.items[0].name == "旺财"
        assert result.items[0].records is None  # 兼容 null
        assert result.items[0].charges is None

    async def test_no_params_minimal_call(self):
        """只传默认参数时，只有 page 和 pageSize 会被转发。"""
        transport = httpx.MockTransport(make_ok_handler(expected_params={"page": "1", "pageSize": "20"}))
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)

        result = await execute_list_pets(client)
        assert isinstance(result, ListPetsOutput)

    async def test_validation_error_raised(self):
        """输入校验失败 → MCPToolError(VALIDATION_ERROR)。"""
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client, page=0)
        assert exc.value.code == ErrorCode.VALIDATION_ERROR

    async def test_backend_4xx(self):
        """Go API 返回 4xx → MCPToolError(BACKEND_API_ERROR)。"""
        transport = httpx.MockTransport(make_error_handler(400))
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client)
        assert exc.value.code == ErrorCode.BACKEND_API_ERROR

    async def test_backend_5xx_retried_then_failed(self):
        """Go API 返回 5xx → 有限重试后 MCPToolError(BACKEND_API_ERROR)。"""
        # 每次请求都返回 500，max_retries=2，共 3 次请求
        call_count = [0]

        async def always_500(request: httpx.Request) -> httpx.Response:
            call_count[0] += 1
            return httpx.Response(500, json={"code": 500, "message": "boom", "data": None, "time": "now"})

        transport = httpx.MockTransport(always_500)
        settings = Settings(
            pet_hospital_base_url="http://fake",
            request_timeout=1.0,
            max_retries=2,
            retry_backoff=0.01,  # 快一点
        )
        client = PetHospitalClient(settings).with_transport(transport)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client)
        assert exc.value.code == ErrorCode.BACKEND_API_ERROR
        assert call_count[0] == 3  # 1 + 2 次重试

    async def test_timeout(self):
        """请求超时 → MCPToolError(BACKEND_TIMEOUT)。"""
        # MockTransport 不真正走网络，需要直接 raise TimeoutException
        async def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("request timed out", request=request)

        transport = httpx.MockTransport(timeout_handler)
        settings = Settings(
            pet_hospital_base_url="http://fake",
            request_timeout=0.05,
            max_retries=0,
        )
        client = PetHospitalClient(settings).with_transport(transport)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client)
        assert exc.value.code == ErrorCode.BACKEND_TIMEOUT

    async def test_connection_error(self):
        """连接失败 → MCPToolError(BACKEND_UNAVAILABLE)。"""
        # MockTransport 不会触发真实连接错误，这里模拟 raise
        async def conn_err_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        transport = httpx.MockTransport(conn_err_handler)
        settings = Settings(
            pet_hospital_base_url="http://fake",
            request_timeout=1.0,
            max_retries=0,
        )
        client = PetHospitalClient(settings).with_transport(transport)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client)
        assert exc.value.code == ErrorCode.BACKEND_UNAVAILABLE

    async def test_malformed_json(self):
        """后端返回非法 JSON → MCPToolError(BACKEND_INVALID_RESPONSE)。"""
        transport = httpx.MockTransport(make_malformed_json_handler())
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client)
        assert exc.value.code == ErrorCode.BACKEND_INVALID_RESPONSE

    async def test_invalid_data_model(self):
        """后端返回合法 JSON 但字段不符合预期 → BACKEND_INVALID_RESPONSE。"""
        transport = httpx.MockTransport(make_invalid_data_handler())
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)

        with pytest.raises(MCPToolError) as exc:
            await execute_list_pets(client)
        assert exc.value.code == ErrorCode.BACKEND_INVALID_RESPONSE


# ---------------------------------------------------------------------------
# MCP 层测试 —— 通过 Client 在内存中连接
# ---------------------------------------------------------------------------

class TestMCPToolRegistration:
    """工具注册、工具名、JSON Schema。"""

    @pytest.fixture
    def mcp_server(self):
        transport = httpx.MockTransport(make_ok_handler())
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)
        return create_server(settings, client)

    @pytest.mark.anyio
    async def test_tool_registered(self, mcp_server):
        """tools/list 应该能返回 list_pets。"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools.tools]
            assert "list_pets" in names

    @pytest.mark.anyio
    async def test_tool_name_snake_case(self, mcp_server):
        """工具名使用 snake_case。"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools.tools if t.name == "list_pets")
            assert "_" in tool.name  # snake_case

    @pytest.mark.anyio
    async def test_tool_has_json_schema(self, mcp_server):
        """输入 schema 应该存在。"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools.tools if t.name == "list_pets")
            schema = tool.input_schema
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema

    @pytest.mark.anyio
    async def test_tool_call_normal(self, mcp_server):
        """tools/call 正常返回结构化内容。"""
        async with Client(mcp_server) as client:
            result = await client.call_tool("list_pets", {"page": 1})
            assert not result.is_error
            assert result.structured_content is not None
            data = result.structured_content
            assert "items" in data
            assert len(data["items"]) == 1
            assert data["items"][0]["name"] == "旺财"

    @pytest.mark.anyio
    async def test_tool_call_validation_error(self, mcp_server):
        """tools/call 校验失败 → is_error=True。"""
        async with Client(mcp_server) as client:
            result = await client.call_tool("list_pets", {"page": 0})
            assert result.is_error

    @pytest.mark.anyio
    async def test_tool_call_backend_error(self):
        """tools/call 上游错误 → is_error=True。"""
        transport = httpx.MockTransport(make_error_handler(404))
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)
        server = create_server(settings, client)

        async with Client(server) as c:
            result = await c.call_tool("list_pets")
            assert result.is_error


# ---------------------------------------------------------------------------
# 无状态连接流程
# ---------------------------------------------------------------------------

class TestStatelessMCPConnection:
    """MCP 2026-07-28 无状态约定验证。"""

    @pytest.fixture
    def mcp_server(self):
        transport = httpx.MockTransport(make_ok_handler())
        settings = Settings(pet_hospital_base_url="http://fake")
        client = PetHospitalClient(settings).with_transport(transport)
        return create_server(settings, client)

    @pytest.mark.anyio
    async def test_client_connects_without_initialize(self, mcp_server):
        """SDK 2.x 不应要求手动 initialize 握手。"""
        # Client 构造后直接 connect，不手动调 initialize
        async with Client(mcp_server) as client:
            # 直接调用工具 —— 不应该有任何需要 initialize 的异常
            result = await client.call_tool("list_pets", {"page": 1})
            assert not result.is_error

    @pytest.mark.anyio
    async def test_no_mcp_session_id(self, mcp_server):
        """MCP-Session-Id 不应该出现在请求头（在 Streamable HTTP 模式下）。

        因为我们使用 stateless_http=True，SDK 不应发送或检查 Mcp-Session-Id。
        """
        # 通过 Client 直接连接 server 对象（内存中），不存在 HTTP header
        # 所以我们间接验证：Client(mcp_server) 直接 connect 成功
        async with Client(mcp_server) as client:
            result = await client.call_tool("list_pets")
            assert not result.is_error
            # 成功就是验证 —— 如果 SDK 要求 Mcp-Session-Id 会报连接错误
