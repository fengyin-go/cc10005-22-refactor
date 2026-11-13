"""共享字段登记册：字段映射的“目标字段”与结果校验的“校验对象”在这里取得稳定编号。

关键约束：
* 身份只由 `字段编号` 决定，两个同名对象不会被自动合并；
* 旧样例文字引用只作为待确认关系展示，必须人工确认后才绑定编号；
* 业务记录一旦引用编号，编号就必须存在于登记册，避免悬空引用。
"""
from __future__ import annotations

from app.contracts import FieldReferenceEntry

FIELD_REFERENCES: tuple[FieldReferenceEntry, ...] = (
    FieldReferenceEntry(
        字段编号="FLD-TITLE",
        字段名称="标题",
        作用域="网页抽取",
        说明="列表或详情页的标题文本",
    ),
    FieldReferenceEntry(
        字段编号="FLD-PRICE",
        字段名称="价格",
        作用域="网页抽取",
        说明="商品或服务的价格数值",
    ),
    FieldReferenceEntry(
        字段编号="FLD-PUBLISH-DATE",
        字段名称="发布日期",
        作用域="网页抽取",
        说明="内容发布时间",
    ),
    FieldReferenceEntry(
        字段编号="FLD-AUTHOR",
        字段名称="作者",
        作用域="网页抽取",
        说明="内容作者或发布账号",
    ),
    FieldReferenceEntry(
        字段编号="FLD-DETAIL-URL",
        字段名称="详情地址",
        作用域="网页抽取",
        说明="详情页绝对地址",
    ),
    FieldReferenceEntry(
        字段编号="FLD-RECORD-COUNT",
        字段名称="记录条数",
        作用域="结果校验",
        说明="单批次采集结果应有的记录数量",
    ),
    FieldReferenceEntry(
        字段编号="FLD-NULL-RATIO",
        字段名称="空值比例",
        作用域="结果校验",
        说明="采集结果中空值字段占比",
    ),
)


class ReferenceRegistry:
    """登记册的只读访问入口；新增字段必须同时登记编号，不做按名称推断。"""

    def __init__(self, entries: tuple[FieldReferenceEntry, ...]) -> None:
        self._by_id = {item.字段编号: item for item in entries}

    def get(self, field_id: str) -> FieldReferenceEntry | None:
        return self._by_id.get(field_id)

    def exists(self, field_id: str | None) -> bool:
        return bool(field_id) and field_id in self._by_id

    def name_of(self, field_id: str) -> str | None:
        entry = self._by_id.get(field_id)
        return entry.字段名称 if entry else None

    def all(self) -> list[FieldReferenceEntry]:
        return list(self._by_id.values())


registry = ReferenceRegistry(FIELD_REFERENCES)
