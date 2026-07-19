from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from fastapi import HTTPException

from backend.app.routers import guides as guides_router
from backend.app.routers import persons as persons_router
from backend.app.services import delete_preflight


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, values: dict[str, object]):
        self._body = urlencode(values).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


def snapshot(
    entity_type: str = "person",
    entity_id: int = 1,
    *,
    counts: tuple[tuple[str, int], ...] = (("rewards", 2),),
    blocking_reason: str | None = None,
) -> delete_preflight.DeletePreflightSnapshot:
    message = "Удалить кавалера? Наград: 2."
    if blocking_reason:
        message = f"Удаление недоступно: {blocking_reason}."
    return delete_preflight.DeletePreflightSnapshot(
        entity_type=entity_type,
        entity_id=entity_id,
        counts=counts,
        blocking_reason=blocking_reason,
        message=message,
    )


class DeletePreflightGrantTests(unittest.TestCase):
    def setUp(self) -> None:
        delete_preflight.reset_delete_preflight_registry()
        self.settings = SimpleNamespace()

    def test_fresh_grant_is_bound_to_entity_type_id_and_plan(self) -> None:
        current = snapshot()
        with patch.object(delete_preflight, "_snapshot", return_value=current):
            response = delete_preflight.issue_delete_preflight(self.settings, "person", 1)
            delete_preflight.authorize_delete_execution(
                self.settings,
                "person",
                1,
                str(response["operation_id"]),
            )

        self.assertTrue(response["allowed"])
        self.assertFalse(response["blocked"])
        self.assertEqual(response["entity_type"], "person")
        self.assertEqual(response["entity_id"], 1)
        self.assertEqual(response["counts"], {"rewards": 2})
        self.assertEqual(len(str(response["operation_id"])), 32)
        self.assertEqual(response["plan_fingerprint"], current.fingerprint)

        with self.assertRaisesRegex(delete_preflight.DeletePreflightValidationError, "не соответствует"):
            delete_preflight.authorize_delete_execution(
                self.settings,
                "reward",
                1,
                str(response["operation_id"]),
            )
        with self.assertRaisesRegex(delete_preflight.DeletePreflightValidationError, "не соответствует"):
            delete_preflight.authorize_delete_execution(
                self.settings,
                "person",
                2,
                str(response["operation_id"]),
            )

    def test_blocked_changed_and_expired_grants_are_rejected(self) -> None:
        with patch.object(
            delete_preflight,
            "_snapshot",
            return_value=snapshot(blocking_reason="есть внешняя ссылка"),
        ):
            blocked = delete_preflight.issue_delete_preflight(self.settings, "person", 1)
        self.assertFalse(blocked["allowed"])
        self.assertTrue(blocked["blocked"])
        with self.assertRaisesRegex(delete_preflight.DeletePreflightValidationError, "заблокировано"):
            delete_preflight.authorize_delete_execution(
                self.settings,
                "person",
                1,
                str(blocked["operation_id"]),
            )

        delete_preflight.reset_delete_preflight_registry()
        with patch.object(
            delete_preflight,
            "_snapshot",
            side_effect=(snapshot(), snapshot(counts=(("rewards", 3),))),
        ):
            changed = delete_preflight.issue_delete_preflight(self.settings, "person", 1)
            with self.assertRaisesRegex(delete_preflight.DeletePreflightValidationError, "Данные изменились"):
                delete_preflight.authorize_delete_execution(
                    self.settings,
                    "person",
                    1,
                    str(changed["operation_id"]),
                )

        delete_preflight.reset_delete_preflight_registry()
        with patch.object(delete_preflight, "_snapshot", return_value=snapshot()), patch.object(
            delete_preflight.time,
            "monotonic",
            side_effect=(100.0, 100.0 + delete_preflight.DELETE_PREFLIGHT_TTL_SECONDS + 1),
        ):
            expired = delete_preflight.issue_delete_preflight(self.settings, "person", 1)
            with self.assertRaisesRegex(delete_preflight.DeletePreflightValidationError, "устарела"):
                delete_preflight.authorize_delete_execution(
                    self.settings,
                    "person",
                    1,
                    str(expired["operation_id"]),
                )

    def test_post_route_rejects_missing_grant_before_repository_delete(self) -> None:
        settings = SimpleNamespace()
        request = FakeRequest(
            {
                "confirm": "true",
                "delete_person_confirm": "true",
                "delete_operation_id": "missing",
            }
        )
        delete_call = Mock()
        with patch.object(persons_router, "get_settings", return_value=settings), patch.object(
            persons_router,
            "delete_person_with_result",
            delete_call,
        ):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(persons_router.person_delete(request, 1))

        self.assertEqual(caught.exception.status_code, 409)
        delete_call.assert_not_called()


class OrdinaryReadContractTests(unittest.TestCase):
    def test_entity_routers_do_not_build_destructive_previews_on_reads(self) -> None:
        router_names = ("legacy.py", "persons.py", "rewards.py", "marks.py", "guides.py", "search.py", "dashboard.py")
        for name in router_names:
            source = (ROOT / "backend" / "app" / "routers" / name).read_text(encoding="utf-8")
            self.assertNotIn("delete_preview", source, name)
            self.assertNotIn("issue_delete_preflight", source, name)
            self.assertNotIn("uuid4", source, name)

    def test_guides_context_contains_delete_affordances_but_no_eager_collections(self) -> None:
        settings = SimpleNamespace(db_exists=True, rewards_db_path=Path("unused.sqlite"))
        ranks = [{"id": 7, "name": "Тестовое звание", "image_path": None}]
        tree = [{"id": 8, "level": 0, "name": "Тестовый узел", "guide_key": "0-8", "children": []}]
        with patch.object(guides_router, "list_rank_guide", return_value=ranks), patch.object(
            guides_router,
            "guide_tree",
            return_value=tree,
        ):
            context = guides_router._context(settings, SimpleNamespace())

        self.assertEqual(context["ranks"], ranks)
        self.assertIn("tree", context)
        self.assertFalse(any("delete" in key for key in context))

    def test_templates_use_one_lazy_contract_without_eager_preview_collections(self) -> None:
        template_names = ("legacy.html", "person_detail.html", "reward_detail.html", "mark_detail.html", "guides.html")
        templates = "\n".join(
            (ROOT / "backend" / "app" / "templates" / name).read_text(encoding="utf-8")
            for name in template_names
        )
        for entity_type in ("person", "reward", "mark", "rank", "guide_level_"):
            self.assertIn(f"/delete-preflight/{entity_type}", templates)
        self.assertIn('data-delete-entity-type=', templates)
        self.assertIn('data-delete-entity-id=', templates)
        self.assertIn('type="submit">Удалить</button>', templates)
        for eager_name in (
            "delete_confirmations",
            "delete_blocked",
            "delete_operation_ids",
        ):
            self.assertNotIn(eager_name, templates)

    def test_all_entity_posts_require_shared_authorization(self) -> None:
        expected = {
            "persons.py": '"person"',
            "rewards.py": '"reward"',
            "marks.py": '"mark"',
            "guides.py": '"rank"',
        }
        for name, entity_literal in expected.items():
            source = (ROOT / "backend" / "app" / "routers" / name).read_text(encoding="utf-8")
            self.assertIn("authorize_delete_execution(", source, name)
            self.assertIn(entity_literal, source, name)
        guides = (ROOT / "backend" / "app" / "routers" / "guides.py").read_text(encoding="utf-8")
        self.assertIn('f"guide_level_{level}"', guides)

    def test_frontend_has_finite_shared_lifecycle_and_stale_protection(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "confirm_submit.js").read_text(encoding="utf-8")
        for expected in (
            "DELETE_PREFLIGHT_TIMEOUT_MS = 15000",
            "new AbortController()",
            "abortActiveDeleteRequest()",
            "activeDeleteRequest.sequence !== sequence",
            "validateDeletePreview(form",
            "preview.entity_type",
            "preview.entity_id",
            'dialog.setAttribute("aria-busy", loading ? "true" : "false")',
            "form.requestSubmit(submitter || undefined)",
        ):
            self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
