"""HTTP-level tests for the workflows API (2.7) — a thin, real surface over
WorkflowExecutor. Two client flavors: the default client uses the production
dependency wiring (UnconfiguredStageRunner), proving the API is honest when
no real capability execution exists yet; `_client_with_fake_runner` overrides
that one dependency with the workflow_engine's own FakeStageRunner test
double so the rest of the surface (multi-stage progression, approvals,
pause/resume/cancel/skip) can be exercised end to end.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi.testclient import TestClient


def _client(test_env: None) -> TestClient:
    from forgeai_api.main import create_app

    return TestClient(create_app())


def _client_with_fake_runner(test_env: None) -> TestClient:
    from forgeai_api.main import create_app
    from forgeai_api.modules.workflows.dependencies import get_stage_runner
    from forgeai_workflow_engine.runner import FakeStageRunner

    app = create_app()
    app.dependency_overrides[get_stage_runner] = lambda: FakeStageRunner()
    return TestClient(app)


def _register_and_login(client: TestClient, *, email: str, username: str) -> tuple[str, str]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "correct-horse-battery"},
    )
    user_id: str = register_response.json()["id"]
    login_response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    token: str = login_response.json()["access_token"]
    return token, user_id


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _definition_body(key: str, *, requires_approval: bool = False) -> dict[str, object]:
    return {
        "key": key,
        "name": key,
        "version": "1.0.0",
        "stages": [
            {"id": "a", "name": "A", "requires_approval": requires_approval},
        ],
    }


def _two_stage_definition_body(key: str) -> dict[str, object]:
    return {
        "key": key,
        "name": key,
        "version": "1.0.0",
        "stages": [
            {"id": "a", "name": "A"},
            {"id": "b", "name": "B", "depends_on": ["a"], "allow_skip": True},
        ],
    }


class TestDefinitions:
    def test_register_requires_auth(self, test_env: None) -> None:
        client = _client(test_env)
        response = client.post("/api/v1/workflow-definitions", json=_definition_body("noauth"))
        assert response.status_code == 401

    def test_register_then_list_and_get_version(self, test_env: None) -> None:
        client = _client(test_env)
        token, _user_id = _register_and_login(client, email="def1@example.com", username="def1user")
        key = f"greet-{uuid.uuid4().hex[:8]}"

        create_response = client.post(
            "/api/v1/workflow-definitions",
            json=_definition_body(key),
            headers=_auth_headers(token),
        )
        assert create_response.status_code == 201
        assert create_response.json()["version"] == "1.0.0"

        list_response = client.get(
            f"/api/v1/workflow-definitions/{key}/versions", headers=_auth_headers(token)
        )
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        detail_response = client.get(
            f"/api/v1/workflow-definitions/{key}/versions/1.0.0", headers=_auth_headers(token)
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["graph_spec"]["key"] == key

    def test_registering_duplicate_version_is_conflict(self, test_env: None) -> None:
        client = _client(test_env)
        token, _user_id = _register_and_login(client, email="def2@example.com", username="def2user")
        key = f"dup-{uuid.uuid4().hex[:8]}"
        body = _definition_body(key)

        first = client.post("/api/v1/workflow-definitions", json=body, headers=_auth_headers(token))
        assert first.status_code == 201

        second = client.post(
            "/api/v1/workflow-definitions", json=body, headers=_auth_headers(token)
        )
        assert second.status_code == 409
        assert second.json()["type"] == "version_already_registered"

    def test_registering_a_cyclic_definition_is_422(self, test_env: None) -> None:
        client = _client(test_env)
        token, _user_id = _register_and_login(client, email="def3@example.com", username="def3user")
        body = {
            "key": "cyclic",
            "name": "cyclic",
            "version": "1.0.0",
            "stages": [
                {"id": "a", "name": "A", "depends_on": ["b"]},
                {"id": "b", "name": "B", "depends_on": ["a"]},
            ],
        }

        response = client.post(
            "/api/v1/workflow-definitions", json=body, headers=_auth_headers(token)
        )

        assert response.status_code == 422


class TestExecutionsWithDefaultRunner:
    def test_create_execution_requires_project_role(self, test_env: None) -> None:
        client = _client(test_env)
        token, _user_id = _register_and_login(
            client, email="exec1@example.com", username="exec1user"
        )
        response = client.post(
            f"/api/v1/projects/{uuid.uuid4()}/workflow-executions",
            json={"workflow_key": "whatever", "version": "1.0.0"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 403

    def test_create_execution_fails_honestly_without_a_configured_runner(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        """With the production dependency wiring (no override), a stage
        genuinely can't run — the API must say so honestly (execution status
        FAILED, error explaining why), not silently pretend success."""
        client = _client(test_env)
        token, user_id = _register_and_login(
            client, email="exec2@example.com", username="exec2user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"honest-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions", json=_definition_body(key), headers=_auth_headers(token)
        )

        response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "failed"
        assert "no capability execution is configured" in body["error"].lower()


class TestExecutionsWithFakeRunner:
    def test_create_execution_completes_a_single_stage_workflow(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="fake1@example.com", username="fake1user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"single-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions", json=_definition_body(key), headers=_auth_headers(token)
        )

        response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "completed"
        assert len(body["stages"]) == 1
        assert body["stages"][0]["status"] == "completed"

    def test_advance_progresses_a_multi_stage_workflow(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="fake2@example.com", username="fake2user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"multi-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_two_stage_definition_body(key),
            headers=_auth_headers(token),
        )

        create_response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        )
        execution_id = create_response.json()["id"]
        assert create_response.json()["status"] == "running"  # "a" done, "b" still pending

        advance_response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/advance",
            headers=_auth_headers(token),
        )
        assert advance_response.status_code == 200
        assert advance_response.json()["status"] == "completed"

    def test_pause_then_resume(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="fake3@example.com", username="fake3user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"pause-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_two_stage_definition_body(key),
            headers=_auth_headers(token),
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()["id"]

        pause_response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/pause",
            headers=_auth_headers(token),
        )
        assert pause_response.json()["status"] == "paused"

        resume_response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/resume",
            headers=_auth_headers(token),
        )
        assert resume_response.json()["status"] == "running"

    def test_cancel(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="fake4@example.com", username="fake4user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"cancel-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_two_stage_definition_body(key),
            headers=_auth_headers(token),
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()["id"]

        response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/cancel",
            headers=_auth_headers(token),
        )
        assert response.json()["status"] == "cancelled"

    def test_skip_stage(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="fake5@example.com", username="fake5user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"skip-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_two_stage_definition_body(key),
            headers=_auth_headers(token),
        )
        detail = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()
        execution_id = detail["id"]
        stage_b_id = next(s["id"] for s in detail["stages"] if s["stage_key"] == "b")

        response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}"
            f"/stages/{stage_b_id}/skip",
            headers=_auth_headers(token),
        )

        assert response.status_code == 200
        # skip_stage() is a one-shot state change, not a full tick — the
        # workflow only notices every stage is now done on the *next*
        # advance() call, same as the Executor's own 2.3 semantics.
        assert response.json()["status"] == "running"
        skipped = next(s for s in response.json()["stages"] if s["stage_key"] == "b")
        assert skipped["status"] == "skipped"

        advance_response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/advance",
            headers=_auth_headers(token),
        )
        assert advance_response.json()["status"] == "completed"

    def test_non_member_cannot_view_execution(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        owner_token, owner_id = _register_and_login(
            client, email="fake6owner@example.com", username="fake6owner"
        )
        outsider_token, _outsider_id = _register_and_login(
            client, email="fake6out@example.com", username="fake6out"
        )
        project_id = _run(seed_project(uuid.UUID(owner_id)))
        key = f"private-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_definition_body(key),
            headers=_auth_headers(owner_token),
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(owner_token),
        ).json()["id"]

        response = client.get(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}",
            headers=_auth_headers(outsider_token),
        )

        assert response.status_code == 403

    def test_execution_from_another_project_is_not_found_via_this_projects_url(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        """The real authorization check this sub-sprint added: a member of
        Project B must not be able to act on Project A's execution just by
        putting Project B's project_id in the URL alongside Project A's
        execution_id."""
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="fake7@example.com", username="fake7user"
        )
        project_a = _run(seed_project(uuid.UUID(user_id)))
        project_b = _run(seed_project(uuid.UUID(user_id)))
        key = f"cross-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions", json=_definition_body(key), headers=_auth_headers(token)
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_a}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()["id"]

        response = client.get(
            f"/api/v1/projects/{project_b}/workflow-executions/{execution_id}",
            headers=_auth_headers(token),
        )

        assert response.status_code == 404


class TestApprovals:
    def test_list_approvals_and_approve_resumes_execution(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="appr1@example.com", username="appr1user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"approve-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_definition_body(key, requires_approval=True),
            headers=_auth_headers(token),
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()["id"]

        list_response = client.get(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/approvals",
            headers=_auth_headers(token),
        )
        assert list_response.status_code == 200
        approvals = list_response.json()
        assert len(approvals) == 1
        assert approvals[0]["decision"] is None
        approval_id = approvals[0]["id"]

        resolve_response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}"
            f"/approvals/{approval_id}/resolve",
            json={"decision": "approve", "comment": "ship it"},
            headers=_auth_headers(token),
        )

        assert resolve_response.status_code == 200
        assert resolve_response.json()["status"] == "completed"

    def test_reject_fails_the_execution(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="appr2@example.com", username="appr2user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"reject-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_definition_body(key, requires_approval=True),
            headers=_auth_headers(token),
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()["id"]
        approval_id = client.get(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/approvals",
            headers=_auth_headers(token),
        ).json()[0]["id"]

        response = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}"
            f"/approvals/{approval_id}/resolve",
            json={"decision": "reject"},
            headers=_auth_headers(token),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_resolving_the_same_approval_twice_is_conflict(
        self, test_env: None, seed_project: Callable[..., Coroutine[Any, Any, uuid.UUID]]
    ) -> None:
        client = _client_with_fake_runner(test_env)
        token, user_id = _register_and_login(
            client, email="appr3@example.com", username="appr3user"
        )
        project_id = _run(seed_project(uuid.UUID(user_id)))
        key = f"double-{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/v1/workflow-definitions",
            json=_definition_body(key, requires_approval=True),
            headers=_auth_headers(token),
        )
        execution_id = client.post(
            f"/api/v1/projects/{project_id}/workflow-executions",
            json={"workflow_key": key, "version": "1.0.0"},
            headers=_auth_headers(token),
        ).json()["id"]
        approval_id = client.get(
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}/approvals",
            headers=_auth_headers(token),
        ).json()[0]["id"]
        resolve_url = (
            f"/api/v1/projects/{project_id}/workflow-executions/{execution_id}"
            f"/approvals/{approval_id}/resolve"
        )
        client.post(resolve_url, json={"decision": "approve"}, headers=_auth_headers(token))

        response = client.post(
            resolve_url, json={"decision": "approve"}, headers=_auth_headers(token)
        )

        assert response.status_code == 409
        assert response.json()["type"] == "approval_already_decided"


def _run(coro: Coroutine[Any, Any, uuid.UUID]) -> uuid.UUID:
    """seed_project's factory is async (it awaits real DB calls); these tests
    are plain sync functions driving a sync TestClient, so a small runner is
    needed at the call site rather than making every test `async def` just
    for this one setup step."""
    import asyncio

    return asyncio.run(coro)
