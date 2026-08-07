from fastapi.testclient import TestClient


def test_liveness_returns_ok_without_touching_the_database(test_env: None) -> None:
    from forgeai_api.main import create_app

    client = TestClient(create_app())
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ok_when_database_is_reachable(test_env: None) -> None:
    from forgeai_api.main import create_app

    client = TestClient(create_app())
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unmatched_route_returns_rfc7807_shape_not_starlettes_default(test_env: None) -> None:
    from forgeai_api.main import create_app

    client = TestClient(create_app())
    response = client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "not_found"
    assert body["status"] == 404
    assert body["instance"] == "/this-route-does-not-exist"
