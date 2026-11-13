"""结果校验接口：维护校验规则，覆盖提交校验、启用规则、停用规则等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.contracts import (
    ValidatorActionPayload,
    ValidatorActionResult,
    ValidatorEntry,
    ValidatorEntryPayload,
    ValidatorExport,
    ValidatorRelationPayload,
)
from app.field_registry import registry
from app.schemas import PageResult
from app.services.validator import ValidatorService

router = APIRouter(prefix="/api/validator", tags=["结果校验"])

service = ValidatorService()

LIST_FIELDS = ["规则编号", "校验对象", "校验类型", "校验表达式", "期望值范围", "采样比例", "异常阈值", "阻断级别"]
STATUSES = ["草稿", "待校验", "已启用", "已停用"]


@router.get("", response_model=PageResult[ValidatorEntry])
def list_entries(
    keyword: str | None = Query(default=None, description="按规则编号检索"),
    status: str | None = Query(default=None, description="草稿、待校验、已启用、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[ValidatorEntry]:
    """按规则编号与状态过滤结果校验列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export", response_model=ValidatorExport)
def export_entries() -> ValidatorExport:
    """导出结果校验清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return ValidatorExport(total=total, items=items)


@router.get("/references")
def list_references() -> dict[str, Any]:
    """共享字段登记册：结果校验对象编号的稳定来源。"""
    return {
        "module": "validator",
        "total": len(registry.all()),
        "items": [item.model_dump() for item in registry.all()],
    }


@router.get("/{entry_id}", response_model=ValidatorEntry)
def get_entry(entry_id: int) -> ValidatorEntry:
    """读取单条校验规则明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"校验规则 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ValidatorActionResult)
def create_entry(payload: ValidatorEntryPayload) -> ValidatorActionResult:
    """登记一条校验规则；字段不合规时整体拒绝并说明原因，不做静默截断。"""
    entry, rejected = service.create_entry(payload.values.model_dump(exclude_unset=True))
    if rejected:
        return ValidatorActionResult(ok=False, message=f"登记未通过：{'；'.join(rejected)}")
    return ValidatorActionResult(ok=True, message="校验规则已登记", entry=entry)


@router.post("/{entry_id}/relations", response_model=ValidatorActionResult)
def confirm_relation(entry_id: int, payload: ValidatorRelationPayload) -> ValidatorActionResult:
    """人工确认旧文字引用：必须给出共享登记册编号，名称不被当作身份。"""
    entry, message = service.confirm_relation(
        entry_id, payload.values.校验对象编号, payload.values.校验对象
    )
    if entry is None:
        return ValidatorActionResult(ok=False, message=message)
    return ValidatorActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ValidatorActionResult)
def run_action(entry_id: int, payload: ValidatorActionPayload) -> ValidatorActionResult:
    """对单条校验规则执行提交校验、启用规则、停用规则；动作与目标状态由服务层裁决。"""
    action = str(payload.values.action or payload.action or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ValidatorActionResult(ok=False, message=message)
    return ValidatorActionResult(ok=True, message=message, entry=entry)
