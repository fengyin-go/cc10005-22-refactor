"""结果校验业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.field_registry import registry
from app.services.field_links import (
    ReferenceMismatch,
    UnknownFieldReference,
    build_linked_relation,
    build_relation,
    require_reference,
)
from app.store import store

MODULE = "validator"
REQUIRED_FIELDS = ["规则编号", "校验对象", "校验类型"]
STATUS_ORDER = ["草稿", "待校验", "已启用", "已停用"]
ACTION_RULES = {"提交校验": "待校验", "启用规则": "已启用", "停用规则": "已停用"}
NEGATIVE_ACTIONS = ["停用规则"]
ACTIONS = tuple(ACTION_RULES)


class ValidatorService:
    """读取归一化统一交给 ValidatorEntry 契约，服务层只做业务规则与筛选。"""

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [dict(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("规则编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return dict(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """严格写入：先整体校验，有一项不合规就整条拒绝，不落半条记录。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing

        field_id = values.get("校验对象编号")
        target_name = values.get("校验对象")
        try:
            relation = build_linked_relation(field_id, target_name, name_field="校验对象编号")
        except (UnknownFieldReference, ReferenceMismatch) as error:
            return None, [str(error)]

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["校验对象编号"] = relation.字段编号
        for field in ("校验表达式", "期望值范围", "采样比例", "异常阈值", "阻断级别"):
            if field in values:
                entry[field] = values[field]
        entry["校验对象关系"] = relation.model_dump(mode="json")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return dict(entry), []

    def confirm_relation(
        self, entry_id: int, field_id: str | None, name: str | None
    ) -> tuple[dict[str, Any] | None, str]:
        """人工确认旧文字引用：必须给出登记册编号，确认后名称统一为登记名称。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"校验规则 {entry_id} 不存在或已归档"
        try:
            clean_id = require_reference(field_id, name, name_field="校验对象编号")
        except (UnknownFieldReference, ReferenceMismatch) as error:
            return None, str(error)
        canonical = registry.name_of(clean_id)
        entry["校验对象编号"] = clean_id
        entry["校验对象"] = canonical
        entry["校验对象关系"] = build_relation(clean_id, canonical).model_dump(mode="json")
        return dict(entry), f"校验规则已关联到字段 {clean_id}"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"校验规则 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于结果校验可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return dict(entry), f"校验规则已{action}"


__all__ = [
    "ACTIONS",
    "ValidatorService",
    "MODULE",
    "ReferenceMismatch",
    "UnknownFieldReference",
]
