"""字段契约：字段映射与结果校验共用的登记输入、业务记录与接口输出模型。

这里刻意不再使用 `dict[str, Any]` 承载业务字段：

* 登记输入（`ExtractorValues` / `ValidatorValues`）只允许白名单字段，
  内部编号、状态、待处理与异常标记不在白名单内，提交后整体校验、整体拒绝。
* 业务记录与接口输出（`ExtractorEntry` / `ValidatorEntry`）是有边界的模型，
  中文字段名保持不变，同时额外给出每个字段的三种存在状态。
* 字段映射的“目标字段”和结果校验的“校验对象”都通过共享登记册里的稳定编号
  （`目标字段编号` / `校验对象编号`）关联，名称只作为展示文字，绝不参与自动合并。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldPresence(str, Enum):
    """一个字段在登记输入中的三种存在情况。"""

    VALUE = "有值"
    EXPLICIT_NULL = "显式空值"
    ABSENT = "未提供"


class ReferenceStatus(str, Enum):
    """字段引用关系。旧样例文字引用固定为“待确认”。"""

    LINKED = "已关联"
    PENDING = "待确认"


class FieldRelation(BaseModel):
    """目标字段 / 校验对象与共享字段登记册之间的关系。"""

    model_config = ConfigDict(extra="forbid")

    状态: ReferenceStatus
    字段编号: str | None = None
    引用文本: str | None = None
    说明: str


EXTRACTOR_FIELDS: tuple[str, ...] = (
    "规则编号",
    "源字段名称",
    "目标字段名称",
    "数据类型转换",
    "默认填充值",
    "清洗表达式",
    "必填标识",
    "唯一性校验",
    "目标字段编号",
)

VALIDATOR_FIELDS: tuple[str, ...] = (
    "规则编号",
    "校验对象",
    "校验类型",
    "校验表达式",
    "期望值范围",
    "采样比例",
    "异常阈值",
    "阻断级别",
    "校验对象编号",
)


def _field_states(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, FieldPresence]:
    """按原始键是否存在、值是否显式为 null 计算三态。"""
    states: dict[str, FieldPresence] = {}
    for field in fields:
        if field not in data:
            states[field] = FieldPresence.ABSENT
        elif data[field] is None:
            states[field] = FieldPresence.EXPLICIT_NULL
        else:
            states[field] = FieldPresence.VALUE
    return states


def _normalize_relation_payload(
    payload: dict[str, Any],
    *,
    id_field: str,
    name_field: str,
    relation_field: str,
) -> None:
    """把记录里的引用关系归一化成“已关联 / 待确认”，避免任何悬空编号流到输出。

    这里延迟导入服务层的归一化函数：services 在模块级依赖 contracts，延迟到调用时
    再导入可以避免循环导入，同时让模型在脱离服务层直接构造时也守同一套口径。
    """
    from app.services.field_links import normalize_relation

    relation = normalize_relation(
        field_id=payload.get(id_field),
        reference_text=payload.get(name_field),
        stored=payload.get(relation_field),
    )
    payload[relation_field] = relation
    if relation.字段编号:
        payload[id_field] = relation.字段编号
    elif id_field in payload:
        # 原本有值但已失效：显式置空，字段状态据此呈现“显式空值”而不是“未提供”。
        payload[id_field] = None


class ExtractorFieldStates(BaseModel):
    """字段映射业务字段的存在状态，逐字段强类型声明。"""

    model_config = ConfigDict(extra="forbid")

    规则编号: FieldPresence
    源字段名称: FieldPresence
    目标字段名称: FieldPresence
    数据类型转换: FieldPresence
    默认填充值: FieldPresence
    清洗表达式: FieldPresence
    必填标识: FieldPresence
    唯一性校验: FieldPresence
    目标字段编号: FieldPresence


class ValidatorFieldStates(BaseModel):
    """结果校验业务字段的存在状态，逐字段强类型声明。"""

    model_config = ConfigDict(extra="forbid")

    规则编号: FieldPresence
    校验对象: FieldPresence
    校验类型: FieldPresence
    校验表达式: FieldPresence
    期望值范围: FieldPresence
    采样比例: FieldPresence
    异常阈值: FieldPresence
    阻断级别: FieldPresence
    校验对象编号: FieldPresence


class ExtractorValues(BaseModel):
    """字段映射登记输入：只有这些字段可写，内部字段一律不在契约内。"""

    model_config = ConfigDict(extra="forbid")

    规则编号: str | None = None
    源字段名称: str | None = None
    目标字段名称: str | None = None
    数据类型转换: str | None = None
    默认填充值: str | None = None
    清洗表达式: str | None = None
    必填标识: str | None = None
    唯一性校验: str | None = None
    目标字段编号: str | None = None


class ValidatorValues(BaseModel):
    """结果校验登记输入：只有这些字段可写，内部字段一律不在契约内。"""

    model_config = ConfigDict(extra="forbid")

    规则编号: str | None = None
    校验对象: str | None = None
    校验类型: str | None = None
    校验表达式: str | None = None
    期望值范围: str | None = None
    采样比例: str | None = None
    异常阈值: str | None = None
    阻断级别: str | None = None
    校验对象编号: str | None = None


class ExtractorRelationValues(BaseModel):
    """人工确认字段映射的目标字段引用。"""

    model_config = ConfigDict(extra="forbid")

    目标字段编号: str | None = None
    目标字段名称: str | None = None


class ValidatorRelationValues(BaseModel):
    """人工确认结果校验的校验对象引用。"""

    model_config = ConfigDict(extra="forbid")

    校验对象编号: str | None = None
    校验对象: str | None = None


class ExtractorRelationPayload(BaseModel):
    """确认字段映射目标字段引用：必须给出登记册中的稳定编号。"""

    model_config = ConfigDict(extra="forbid")

    values: ExtractorRelationValues = Field(default_factory=ExtractorRelationValues)


class ValidatorRelationPayload(BaseModel):
    """确认结果校验校验对象引用：必须给出登记册中的稳定编号。"""

    model_config = ConfigDict(extra="forbid")

    values: ValidatorRelationValues = Field(default_factory=ValidatorRelationValues)


class ExtractorActionValues(BaseModel):
    """字段映射动作输入：只允许动作名，不允许夹带状态或异常标记。"""

    model_config = ConfigDict(extra="forbid")

    action: str | None = None


class ValidatorActionValues(BaseModel):
    """结果校验动作输入：只允许动作名，不允许夹带状态或异常标记。"""

    model_config = ConfigDict(extra="forbid")

    action: str | None = None


class ExtractorEntryPayload(BaseModel):
    """登记请求：保留旧接口的 values 包装，values 内部字段受 ExtractorValues 约束。"""

    model_config = ConfigDict(extra="forbid")

    values: ExtractorValues = Field(default_factory=ExtractorValues)
    remark: str | None = None


class ValidatorEntryPayload(BaseModel):
    """登记请求：保留旧接口的 values 包装，values 内部字段受 ValidatorValues 约束。"""

    model_config = ConfigDict(extra="forbid")

    values: ValidatorValues = Field(default_factory=ValidatorValues)
    remark: str | None = None


class ExtractorActionPayload(BaseModel):
    """动作请求：保留旧接口的 values 包装，values 内部只允许 action。

    顶层 `action` 仅用于兼容旧客户端直接平铺动作名的调用方式。
    """

    model_config = ConfigDict(extra="forbid")

    values: ExtractorActionValues = Field(default_factory=ExtractorActionValues)
    action: str | None = None


class ValidatorActionPayload(BaseModel):
    """动作请求：保留旧接口的 values 包装，values 内部只允许 action。

    顶层 `action` 仅用于兼容旧客户端直接平铺动作名的调用方式。
    """

    model_config = ConfigDict(extra="forbid")

    values: ValidatorActionValues = Field(default_factory=ValidatorActionValues)
    action: str | None = None


class ExtractorEntry(BaseModel):
    """字段映射业务记录 / 接口输出。"""

    model_config = ConfigDict(extra="forbid")

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    规则编号: str | None = None
    源字段名称: str | None = None
    目标字段名称: str | None = None
    数据类型转换: str | None = None
    默认填充值: str | None = None
    清洗表达式: str | None = None
    必填标识: str | None = None
    唯一性校验: str | None = None
    目标字段编号: str | None = None
    目标字段关系: FieldRelation
    字段状态: ExtractorFieldStates

    @model_validator(mode="before")
    @classmethod
    def _fill_compatible_fields(cls, data: Any) -> Any:
        """兼容读取旧记录：缺关系字段时由旧文字解释成“待确认”，绝不按名称自动关联。"""
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not payload.get("目标字段关系"):
            ref_id = payload.get("目标字段编号")
            text = payload.get("目标字段名称")
            if ref_id:
                payload["目标字段关系"] = {
                    "状态": ReferenceStatus.LINKED.value,
                    "字段编号": ref_id,
                    "引用文本": text,
                    "说明": "按稳定字段编号关联，名称不参与身份判定",
                }
            else:
                payload["目标字段关系"] = {
                    "状态": ReferenceStatus.PENDING.value,
                    "字段编号": None,
                    "引用文本": text,
                    "说明": (
                        f"旧样例文字引用「{text}」未自动关联，待人工确认对应字段"
                        if text
                        else "缺少可确认的文字引用，待人工确认对应字段"
                    ),
                }
        _normalize_relation_payload(
            payload,
            id_field="目标字段编号",
            name_field="目标字段名称",
            relation_field="目标字段关系",
        )
        if payload.get("字段状态") is None:
            payload["字段状态"] = _field_states(payload, EXTRACTOR_FIELDS)
        return payload


class ValidatorEntry(BaseModel):
    """结果校验业务记录 / 接口输出。"""

    model_config = ConfigDict(extra="forbid")

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    规则编号: str | None = None
    校验对象: str | None = None
    校验类型: str | None = None
    校验表达式: str | None = None
    期望值范围: str | None = None
    采样比例: str | None = None
    异常阈值: str | None = None
    阻断级别: str | None = None
    校验对象编号: str | None = None
    校验对象关系: FieldRelation
    字段状态: ValidatorFieldStates

    @model_validator(mode="before")
    @classmethod
    def _fill_compatible_fields(cls, data: Any) -> Any:
        """兼容读取旧记录：旧文字引用保留为待确认关系，不做同名合并。"""
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not payload.get("校验对象关系"):
            ref_id = payload.get("校验对象编号")
            text = payload.get("校验对象")
            if ref_id:
                payload["校验对象关系"] = {
                    "状态": ReferenceStatus.LINKED.value,
                    "字段编号": ref_id,
                    "引用文本": text,
                    "说明": "按稳定字段编号关联，名称不参与身份判定",
                }
            else:
                payload["校验对象关系"] = {
                    "状态": ReferenceStatus.PENDING.value,
                    "字段编号": None,
                    "引用文本": text,
                    "说明": (
                        f"旧样例文字引用「{text}」未自动关联，待人工确认对应字段"
                        if text
                        else "缺少可确认的文字引用，待人工确认对应字段"
                    ),
                }
        _normalize_relation_payload(
            payload,
            id_field="校验对象编号",
            name_field="校验对象",
            relation_field="校验对象关系",
        )
        if payload.get("字段状态") is None:
            payload["字段状态"] = _field_states(payload, VALIDATOR_FIELDS)
        return payload


class ExtractorActionResult(BaseModel):
    ok: bool
    message: str
    entry: ExtractorEntry | None = None


class ValidatorActionResult(BaseModel):
    ok: bool
    message: str
    entry: ValidatorEntry | None = None


class ExtractorExport(BaseModel):
    module: Literal["extractor"] = "extractor"
    total: int
    items: list[ExtractorEntry]


class ValidatorExport(BaseModel):
    module: Literal["validator"] = "validator"
    total: int
    items: list[ValidatorEntry]


class FieldReferenceEntry(BaseModel):
    """共享字段登记册中的稳定标识。字段映射与结果校验都引用这里的编号。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    字段编号: str
    字段名称: str
    作用域: str
    说明: str
