from fastapi.testclient import TestClient


def _client(test_env: None) -> TestClient:
    from forgeai_api.main import create_app

    return TestClient(create_app())


def _register_and_login(client: TestClient, *, email: str, username: str) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "correct-horse-battery"},
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    token: str = response.json()["access_token"]
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_organization_requires_auth(test_env: None) -> None:
    client = _client(test_env)
    response = client.post("/api/v1/organizations", json={"name": "Acme", "slug": "acme"})
    assert response.status_code == 401


def test_creator_becomes_owner_and_can_view_the_org(test_env: None) -> None:
    client = _client(test_env)
    token = _register_and_login(client, email="owner@example.com", username="owner1")

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Inc", "slug": "acme-inc", "description": "Test org"},
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    org_id = create_response.json()["id"]

    get_response = client.get(f"/api/v1/organizations/{org_id}", headers=_auth_headers(token))
    assert get_response.status_code == 200
    assert get_response.json()["slug"] == "acme-inc"


def test_duplicate_slug_is_rejected(test_env: None) -> None:
    client = _client(test_env)
    token = _register_and_login(client, email="owner2@example.com", username="owner2")
    client.post(
        "/api/v1/organizations",
        json={"name": "Acme", "slug": "dup-slug"},
        headers=_auth_headers(token),
    )

    response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Two", "slug": "dup-slug"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409
    assert response.json()["type"] == "slug_taken"


def test_non_member_cannot_view_the_organization(test_env: None) -> None:
    """The core RBAC assertion: require_org_role actually rejects a real,
    authenticated user who simply isn't a member of the target org."""
    client = _client(test_env)
    owner_token = _register_and_login(client, email="owner3@example.com", username="owner3")
    outsider_token = _register_and_login(client, email="outsider@example.com", username="outsider")

    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Private Org", "slug": "private-org"},
        headers=_auth_headers(owner_token),
    )
    org_id = create_response.json()["id"]

    response = client.get(f"/api/v1/organizations/{org_id}", headers=_auth_headers(outsider_token))

    assert response.status_code == 403
    assert response.json()["type"] == "forbidden"


def test_viewing_a_nonexistent_organization_as_a_stranger_is_403_not_404(test_env: None) -> None:
    """require_org_role checks membership before the route ever looks up the
    organization, so a non-member gets the same 403 regardless of whether the org
    ID is real — it never leaks whether a given org ID exists to non-members."""
    client = _client(test_env)
    token = _register_and_login(client, email="stranger@example.com", username="stranger")

    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000", headers=_auth_headers(token)
    )

    assert response.status_code == 403
