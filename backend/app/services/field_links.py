"""字段引用关系：写入严格、读取宽容，两者共用同一份登记册。

* 写入：编号必须在共享登记册；名称若一并提供必须与该编号登记的名称一致。
  名称相同不代表同一个对象，因此永远不按名称反查编号。
* 读取：旧记录只有文字时解释为“待确认”；旧数据即使带着失效编号也降级为待确认，
  接口输出不会出现悬空引用。
"""
from __future__ import annotations

from app.contracts import FieldRelation, ReferenceStatus
from app.field_registry import registry


class UnknownFieldReference(ValueError):
    """写入的字段编号没有在共享登记册登记。"""

    def __init__(self, field_id: str) -> None:
        self.field_id = field_id
        super().__init__(f"字段编号「{field_id}」未在共享字段登记册登记")


class ReferenceMismatch(ValueError):
    """编号与名称指向的不是同一个字段。"""


def resolve_reference(field_id: str | None, name: str | None, *, name_field: str) -> str | None:
    """校验编号与名称是否一致，返回可写入的编号（可能为空）。

    没有编号时返回 None，由调用方决定“仅文字待确认”是否可接受的业务口径。
    """
    clean_id = (field_id or "").strip()
    clean_name = (name or "").strip()
    if not clean_id:
        return None
    canonical = registry.name_of(clean_id)
    if canonical is None:
        raise UnknownFieldReference(clean_id)
    if clean_name and clean_name != canonical:
        raise ReferenceMismatch(
            f"{name_field}「{clean_name}」与编号 {clean_id} 登记的名称「{canonical}」不一致，"
            "请先确认引用关系"
        )
    return clean_id


def require_reference(field_id: str | None, name: str | None, *, name_field: str) -> str:
    """新写入必须用稳定编号建立身份；只有文字时整体拒绝。"""
    clean_id = resolve_reference(field_id, name, name_field=name_field)
    if not clean_id:
        raise ReferenceMismatch(
            f"{name_field}必须提供共享字段登记册中的字段编号；"
            "纯文字引用只能作为待确认关系保留，不能作为新写入的身份"
        )
    return clean_id


def build_relation(field_id: str | None, reference_text: str | None) -> FieldRelation:
    """登记新记录时构造关系；有编号必须可解析，只有文字则保留为待确认。"""
    clean_id = resolve_reference(field_id, reference_text, name_field="引用名称")
    clean_text = reference_text
    if clean_id:
        return FieldRelation(
            状态=ReferenceStatus.LINKED,
            字段编号=clean_id,
            引用文本=clean_text,
            说明=f"按稳定字段编号 {clean_id} 关联，名称不参与身份判定",
        )
    if clean_text:
        return FieldRelation(
            状态=ReferenceStatus.PENDING,
            字段编号=None,
            引用文本=clean_text,
            说明=f"文字引用「{clean_text}」待人工确认对应字段，不按同名自动合并",
        )
    return FieldRelation(
        状态=ReferenceStatus.PENDING,
        字段编号=None,
        引用文本=None,
        说明="缺少可确认的字段引用，待人工确认对应字段",
    )


def build_linked_relation(
    field_id: str | None, reference_text: str | None, *, name_field: str
) -> FieldRelation:
    """新写入专用：一次性校验编号与名称并返回“已关联”关系，不合规就抛错整体拒绝。"""
    clean_id = require_reference(field_id, reference_text, name_field=name_field)
    return build_relation(clean_id, reference_text)


def normalize_relation(
    *,
    field_id: str | None,
    reference_text: str | None,
    stored: object | None = None,
) -> FieldRelation:
    """读取旧记录时归一化关系，确保输出里不会出现悬空编号。"""
    relation: FieldRelation | None = None
    if isinstance(stored, FieldRelation):
        relation = stored
    elif isinstance(stored, dict):
        try:
            relation = FieldRelation.model_validate(stored)
        except ValueError:
            relation = None

    if relation is not None:
        if relation.字段编号 and not registry.exists(relation.字段编号):
            return FieldRelation(
                状态=ReferenceStatus.PENDING,
                字段编号=None,
                引用文本=relation.引用文本 or reference_text,
                说明=f"原编号 {relation.字段编号} 已不在共享字段登记册，待人工重新确认",
            )
        return relation

    clean_id = (field_id or "").strip()
    if clean_id and registry.exists(clean_id):
        return FieldRelation(
            状态=ReferenceStatus.LINKED,
            字段编号=clean_id,
            引用文本=reference_text,
            说明=f"按稳定字段编号 {clean_id} 关联，名称不参与身份判定",
        )
    if clean_id or reference_text:
        return FieldRelation(
            状态=ReferenceStatus.PENDING,
            字段编号=None,
            引用文本=reference_text,
            说明=(
                f"旧样例文字引用「{reference_text}」未自动关联，待人工确认对应字段"
                if reference_text
                else "旧记录引用的编号已不在登记册，待人工重新确认"
            ),
        )
    return FieldRelation(
        状态=ReferenceStatus.PENDING,
        字段编号=None,
        引用文本=None,
        说明="缺少可确认的字段引用，待人工确认对应字段",
    )
