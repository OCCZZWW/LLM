"""list_pets 工具 —— 对应 Go API: GET /api/v1/pets

输入/输出模型用 Pydantic 定义，REST 客户端作为依赖注入。
"""

from __future__ import annotations

import logging
import math
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..errors import ErrorCode, MCPToolError
from ..logging_config import redact_sensitive
from ..rest_client import PetHospitalClient, VALID_SPECIES, VALID_STATUS, VALID_SORT_BY, VALID_ORDER

logger = logging.getLogger("pet_hospital_mcp.tools.list_pets")


# ---------------------------------------------------------------------------
# 输入模型
# ---------------------------------------------------------------------------

class ListPetsInput(BaseModel):
    """list_pets 工具的入参。

    所有字段都是可选的；不传表示不过滤。
    """

    model_config = ConfigDict(extra="forbid")  # 拒绝未知字段，防止 Go API 私有参数泄漏

    q: str | None = Field(
        default=None,
        description="全文检索关键词，跨 name / species / disease / doctor / 病历全文匹配，空格分词 AND",
    )
    name: str | None = Field(default=None, description="宠物姓名模糊匹配（大小写不敏感）")
    ownerName: str | None = Field(default=None, description="主人姓名模糊匹配")
    ownerPhone: str | None = Field(default=None, description="主人电话模糊匹配")
    species: Literal["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"] | None = Field(
        default=None, description="宠物种类，枚举值"
    )
    doctor: str | None = Field(default=None, description="主治医生姓名模糊匹配")
    disease: str | None = Field(default=None, description="疾病模糊匹配")
    status: Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"] | None = Field(
        default=None, description="就诊状态"
    )
    min: float | None = Field(default=None, ge=0, description="总花费下限（元，非负）")
    max: float | None = Field(default=None, ge=0, description="总花费上限（元，非负）")
    sortBy: Literal[
        "id", "name", "ownerName", "species", "doctor", "disease",
        "status", "totalCost", "visitCount", "createdAt", "updatedAt",
    ] | None = Field(default=None, description="排序字段")
    order: Literal["asc", "desc"] | None = Field(default=None, description="升序 asc / 降序 desc")
    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    pageSize: int = Field(default=20, ge=1, le=500, description="每页条数，1-500")

    @field_validator("q", "name", "ownerName", "ownerPhone", "doctor", "disease")
    @classmethod
    def _no_empty_string(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            return None
        return v

    @model_validator(mode="after")
    def _validate_cost_range(self) -> "ListPetsInput":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) 不能大于 max ({self.max})")
        return self

    @field_validator("min", "max")
    @classmethod
    def _no_nan_inf(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"不能是 NaN 或 Infinity: {v}")
        return v


# ---------------------------------------------------------------------------
# 输出模型
# ---------------------------------------------------------------------------

class Treatment(BaseModel):
    """消费明细（兼容 Go 的 records/charges 可能为 null 或数组）。"""
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    item: str | None = None
    category: str | None = None
    amount: float = 0.0
    doctor: str | None = None
    date: str | None = None
    note: str | None = None


class MedicalRecord(BaseModel):
    """历史病历。"""
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    visitDate: str | None = None
    doctor: str | None = None
    diagnosis: str | None = None
    symptoms: str | None = None
    treatment: str | None = None
    prescription: list[str] = Field(default_factory=list)
    weightKg: float | None = None
    temperature: float | None = None
    followUp: str | None = None
    charge: float = 0.0
    createdAt: str | None = None


class PetRecord(BaseModel):
    """Go API 返回的单只宠物档案。"""
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    species: str
    breed: str | None = None
    gender: str | None = None
    ageMonths: int = 0
    color: str | None = None
    chipNo: str | None = None
    ownerName: str
    ownerPhone: str
    ownerAddr: str | None = None
    doctor: str
    disease: str
    status: str
    allergy: str | None = None
    note: str | None = None
    records: list[MedicalRecord] | None = None
    charges: list[Treatment] | None = None
    totalCost: float = 0.0
    visitCount: int = 0
    createdAt: str | None = None
    updatedAt: str | None = None


class ListPetsOutput(BaseModel):
    """list_pets 工具的成功输出（对应 Go API 的 data 字段）。"""
    model_config = ConfigDict(extra="forbid")

    items: list[PetRecord]
    total: int
    page: int
    pageSize: int
    totalPages: int
    totalCost: float


# ---------------------------------------------------------------------------
# 工具实现 —— 普通函数，由 server.py 的装饰器注册
# ---------------------------------------------------------------------------

async def execute_list_pets(
    client: PetHospitalClient,
    **raw_args: Any,
) -> ListPetsOutput:
    """解析入参 → 调用 REST → 校验输出 → 返回结构化结果。

    任何校验失败或上游异常都抛出 MCPToolError，
    MCP SDK 2.x 会把它转成 is_error=True 的工具结果。
    """
    # 1. Pydantic 校验入参
    try:
        args = ListPetsInput.model_validate(raw_args)
    except Exception as exc:
        raise MCPToolError(
            ErrorCode.VALIDATION_ERROR,
            f"输入参数校验失败: {exc}",
            {"errors": str(exc)},
        ) from exc

    # 2. 日志（脱敏敏感字段）
    safe_params = redact_sensitive(args.model_dump(exclude_none=True))
    logger.info("list_pets tool call", extra={
        "tool_name": "list_pets",
        "params": safe_params,
    })

    # 3. 调用 Go REST API
    try:
        data = await client.list_pets(
            q=args.q,
            name=args.name,
            owner_name=args.ownerName,
            owner_phone=args.ownerPhone,
            species=args.species,
            doctor=args.doctor,
            disease=args.disease,
            status=args.status,
            min_cost=args.min,
            max_cost=args.max,
            sort_by=args.sortBy,
            order=args.order,
            page=args.page,
            page_size=args.pageSize,
        )
    except MCPToolError:
        # 客户端已经包装成统一错误了，直接上抛
        raise

    # 4. 校验输出模型
    try:
        return ListPetsOutput.model_validate(data)
    except Exception as exc:
        raise MCPToolError(
            ErrorCode.BACKEND_INVALID_RESPONSE,
            f"上游返回数据不符合预期: {exc}",
            {"raw": redact_sensitive(data)},
        ) from exc
