"""字段契约回归测试：三态、严格写入、稳定标识关联与兼容读取。

运行：cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.contracts import (  # noqa: E402
    ExtractorEntryPayload,
    ExtractorValues,
    FieldPresence,
    ValidatorEntry,
    ValidatorValues,
)
from app.field_registry import registry  # noqa: E402
from app.main import app  # noqa: E402
from app.services.field_links import (  # noqa: E402
    ReferenceMismatch,
    UnknownFieldReference,
    build_relation,
    normalize_relation,
)
from app.store import store  # noqa: E402


async def _call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(raw)).encode()),
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 10001),
        "server": ("127.0.0.1", settings.port),
    }
    messages: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    await app(scope, receive, send)
    status = next(item["status"] for item in messages if item["type"] == "http.response.start")
    payload = b"".join(
        item.get("body", b"") for item in messages if item["type"] == "http.response.body"
    )
    return status, json.loads(payload) if payload else {}


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    return asyncio.run(_call(method, path, body))


class StoreIsolation(unittest.TestCase):
    """每个用例一份数据副本，互不影响。"""

    def setUp(self) -> None:
        self._snapshot = {
            name: [dict(row) for row in rows] for name, rows in store._tables.items()
        }

    def tearDown(self) -> None:
        store._tables = {
            name: [dict(row) for row in rows] for name, rows in self._snapshot.items()
        }


class PresenceTests(unittest.TestCase):
    def test_three_states_are_distinct(self) -> None:
        states = ExtractorValues.model_fields
        self.assertIn("目标字段编号", states)
        self.assertNotIn("status", states)

        absent = ExtractorEntryPayload.model_validate({"values": {"规则编号": "R-1"}})
        explicit = ExtractorEntryPayload.model_validate(
            {"values": {"规则编号": "R-1", "目标字段名称": None}}
        )
        value = ExtractorEntryPayload.model_validate(
            {"values": {"规则编号": "R-1", "目标字段名称": "标题"}}
        )
        self.assertNotIn("目标字段名称", absent.values.model_fields_set)
        self.assertIn("目标字段名称", explicit.values.model_fields_set)
        self.assertIsNone(explicit.values.目标字段名称)
        self.assertEqual(value.values.目标字段名称, "标题")

    def test_internal_fields_cannot_be_registered(self) -> None:
        for key in ("status", "pending", "abnormal", "id"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                ExtractorValues.model_validate({"规则编号": "R-1", key: "x"})

    def test_action_cannot_smuggle_internal_fields(self) -> None:
        with self.assertRaises(ValueError):
            ValidatorValues.model_validate({"规则编号": "R-1", "status": "已启用"})


class RelationTests(unittest.TestCase):
    def test_same_name_objects_are_not_merged(self) -> None:
        first = build_relation("FLD-TITLE", "标题")
        second = build_relation("FLD-DETAIL-URL", "详情地址")
        self.assertEqual(first.字段编号, "FLD-TITLE")
        self.assertEqual(second.字段编号, "FLD-DETAIL-URL")
        self.assertNotEqual(first.字段编号, second.字段编号)

    def test_unknown_identifier_is_rejected(self) -> None:
        with self.assertRaises(UnknownFieldReference):
            build_relation("FLD-NOT-EXIST", "标题")

    def test_name_conflict_with_identifier_is_rejected(self) -> None:
        with self.assertRaises(ReferenceMismatch):
            build_relation("FLD-TITLE", "价格")

    def test_legacy_text_is_pending_and_never_auto_linked(self) -> None:
        relation = normalize_relation(field_id=None, reference_text="标题", stored=None)
        self.assertEqual(relation.状态.value, "待确认")
        self.assertIsNone(relation.字段编号)
        self.assertEqual(relation.引用文本, "标题")

    def test_dangling_stored_relation_degrades_to_pending(self) -> None:
        relation = normalize_relation(
            field_id="FLD-TITLE",
            reference_text="标题",
            stored={"状态": "已关联", "字段编号": "FLD-GONE", "引用文本": "标题", "说明": ""},
        )
        self.assertEqual(relation.状态.value, "待确认")
        self.assertIsNone(relation.字段编号)

    def test_model_itself_blocks_dangling_reference(self) -> None:
        """即使绕过服务层直接构造，输出也不会带悬空编号。"""
        entry = ValidatorEntry.model_validate(
            {"id": 1, "校验对象": "记录条数", "校验对象编号": "FLD-GONE"}
        )
        self.assertIsNone(entry.校验对象编号)
        self.assertEqual(entry.校验对象关系.状态.value, "待确认")
        self.assertEqual(entry.字段状态.校验对象编号, FieldPresence.EXPLICIT_NULL)

    def test_same_identifier_resolves_in_both_modules(self) -> None:
        """两个模块引用同一编号时应解析到同一个登记项，且互不依赖名称。"""
        _, extractor_created = call(
            "POST",
            "/api/extractor",
            {
                "values": {
                    "规则编号": "EXTR-9100",
                    "源字段名称": "标题文本",
                    "目标字段名称": "标题",
                    "目标字段编号": "FLD-TITLE",
                }
            },
        )
        _, validator_created = call(
            "POST",
            "/api/validator",
            {
                "values": {
                    "规则编号": "VALI-9100",
                    "校验对象": "标题",
                    "校验类型": "非空",
                    "校验对象编号": "FLD-TITLE",
                }
            },
        )
        self.assertEqual(
            extractor_created["entry"]["目标字段关系"]["字段编号"],
            validator_created["entry"]["校验对象关系"]["字段编号"],
        )
        self.assertEqual(registry.name_of("FLD-TITLE"), "标题")


class ApiTests(StoreIsolation):
    def test_legacy_rows_are_readable_and_pending(self) -> None:
        status, payload = call("GET", "/api/extractor/1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["目标字段关系"]["状态"], "待确认")
        self.assertIsNone(payload["目标字段编号"])
        self.assertEqual(payload["字段状态"]["目标字段编号"], FieldPresence.ABSENT.value)

    def test_create_with_stable_identifier(self) -> None:
        status, payload = call(
            "POST",
            "/api/extractor",
            {
                "values": {
                    "规则编号": "EXTR-9001",
                    "源字段名称": "标题文本",
                    "目标字段名称": "标题",
                    "目标字段编号": "FLD-TITLE",
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["entry"]["目标字段关系"]["状态"], "已关联")
        self.assertEqual(payload["entry"]["目标字段编号"], "FLD-TITLE")
        self.assertEqual(payload["entry"]["status"], "草稿")

    def test_create_with_text_only_is_rejected_whole(self) -> None:
        before = len(store.rows("extractor"))
        status, payload = call(
            "POST",
            "/api/extractor",
            {"values": {"规则编号": "EXTR-9002", "源字段名称": "标题", "目标字段名称": "标题"}},
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(len(store.rows("extractor")), before)

    def test_create_with_dangling_identifier_is_rejected_whole(self) -> None:
        before = len(store.rows("validator"))
        status, payload = call(
            "POST",
            "/api/validator",
            {
                "values": {
                    "规则编号": "VALI-9002",
                    "校验对象": "记录条数",
                    "校验类型": "非空",
                    "校验对象编号": "FLD-NOT-EXIST",
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(len(store.rows("validator")), before)

    def test_user_cannot_override_internal_markers(self) -> None:
        status, _ = call(
            "POST",
            "/api/extractor",
            {
                "values": {
                    "规则编号": "EXTR-9003",
                    "源字段名称": "标题",
                    "目标字段名称": "标题",
                    "目标字段编号": "FLD-TITLE",
                    "status": "已启用",
                    "abnormal": True,
                }
            },
        )
        self.assertEqual(status, 422)

    def test_confirmation_requires_identifier(self) -> None:
        status, payload = call(
            "POST", "/api/extractor/1/relations", {"values": {"目标字段名称": "价格"}}
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(call("GET", "/api/extractor/1")[1]["目标字段关系"]["状态"], "待确认")

        status, payload = call(
            "POST", "/api/extractor/1/relations", {"values": {"目标字段编号": "FLD-PRICE"}}
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["entry"]["目标字段关系"]["状态"], "已关联")
        self.assertEqual(payload["entry"]["目标字段名称"], "价格")

    def test_action_cannot_write_status(self) -> None:
        status, payload = call(
            "POST", "/api/extractor/1/actions", {"values": {"action": "启用规则"}}
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["entry"]["status"], "已启用")

        status, _ = call(
            "POST",
            "/api/extractor/1/actions",
            {"values": {"action": "启用规则", "status": "草稿"}},
        )
        self.assertEqual(status, 422)

    def test_exports_keep_legacy_shape(self) -> None:
        status, payload = call("GET", "/api/validator/export")
        self.assertEqual(status, 200)
        self.assertEqual(payload["module"], "validator")
        self.assertEqual(payload["total"], len(payload["items"]))
        self.assertIn("校验对象关系", payload["items"][0])

    def test_registry_is_shared_by_both_modules(self) -> None:
        status, extractor_refs = call("GET", "/api/extractor/references")
        self.assertEqual(status, 200)
        status, validator_refs = call("GET", "/api/validator/references")
        self.assertEqual(status, 200)
        self.assertEqual(extractor_refs["items"], validator_refs["items"])
        ids = [item["字段编号"] for item in extractor_refs["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("FLD-RECORD-COUNT", ids)
        self.assertTrue(all(registry.exists(field_id) for field_id in ids))


if __name__ == "__main__":
    unittest.main()
