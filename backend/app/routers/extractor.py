"""字段映射接口：维护映射规则，覆盖提交校验、启用规则、停用规则等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.contracts import (
    ExtractorActionPayload,
    ExtractorActionResult,
    ExtractorEntry,
    ExtractorEntryPayload,
    ExtractorExport,
    ExtractorRelationPayload,
)
from app.field_registry import registry
from app.schemas import PageResult
from app.services.extractor import ExtractorService

router = APIRouter(prefix="/api/extractor", tags=["字段映射"])

service = ExtractorService()

LIST_FIELDS = ["规则编号", "源字段名称", "目标字段名称", "数据类型转换", "默认填充值", "清洗表达式", "必填标识", "唯一性校验"]
STATUSES = ["草稿", "待校验", "已启用", "已停用"]


@router.get("", response_model=PageResult[ExtractorEntry])
def list_entries(
    keyword: str | None = Query(default=None, description="按规则编号检索"),
    status: str | None = Query(default=None, description="草稿、待校验、已启用、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[ExtractorEntry]:
    """按规则编号与状态过滤字段映射列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export", response_model=ExtractorExport)
def export_entries() -> ExtractorExport:
    """导出字段映射清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return ExtractorExport(total=total, items=items)


@router.get("/references")
def list_references() -> dict[str, Any]:
    """共享字段登记册：字段映射目标字段的稳定编号来源。"""
    return {
        "module": "extractor",
        "total": len(registry.all()),
        "items": [item.model_dump() for item in registry.all()],
    }


@router.get("/{entry_id}", response_model=ExtractorEntry)
def get_entry(entry_id: int) -> ExtractorEntry:
    """读取单条映射规则明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"映射规则 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ExtractorActionResult)
def create_entry(payload: ExtractorEntryPayload) -> ExtractorActionResult:
    """登记一条映射规则；字段不合规时整体拒绝并说明原因，不做静默截断。"""
    entry, rejected = service.create_entry(payload.values.model_dump(exclude_unset=True))
    if rejected:
        return ExtractorActionResult(ok=False, message=f"登记未通过：{'；'.join(rejected)}")
    return ExtractorActionResult(ok=True, message="映射规则已登记", entry=entry)


@router.post("/{entry_id}/relations", response_model=ExtractorActionResult)
def confirm_relation(entry_id: int, payload: ExtractorRelationPayload) -> ExtractorActionResult:
    """人工确认旧文字引用：必须给出共享登记册编号，名称不被当作身份。"""
    entry, message = service.confirm_relation(
        entry_id, payload.values.目标字段编号, payload.values.目标字段名称
    )
    if entry is None:
        return ExtractorActionResult(ok=False, message=message)
    return ExtractorActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ExtractorActionResult)
def run_action(entry_id: int, payload: ExtractorActionPayload) -> ExtractorActionResult:
    """对单条映射规则执行提交校验、启用规则、停用规则；动作与目标状态由服务层裁决。"""
    action = str(payload.values.action or payload.action or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ExtractorActionResult(ok=False, message=message)
    return ExtractorActionResult(ok=True, message=message, entry=entry)
