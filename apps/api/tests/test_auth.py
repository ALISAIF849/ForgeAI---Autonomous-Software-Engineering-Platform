from fastapi.testclient import TestClient


def _client(test_env: None) -> TestClient:
    from forgeai_api.main import create_app

    return TestClient(create_app())


def _register(
    client: TestClient,
    *,
    email: str = "ada@example.com",
    username: str = "ada",
    password: str = "correct-horse-battery",
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": password,
            "full_name": "Ada Lovelace",
        },
    )
    assert response.status_code == 201, response.text


def test_register_returns_public_user_without_password_hash(test_env: None) -> None:
    client = _client(test_env)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "username": "ada", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert body["username"] == "ada"
    assert "hashed_password" not in body
    assert "password" not in body


def test_register_duplicate_email_is_rejected(test_env: None) -> None:
    client = _client(test_env)
    _register(client, email="dup@example.com", username="dupuser1")

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "username": "dupuser2",
            "password": "correct-horse-battery",
        },
    )

    assert response.status_code == 409
    assert response.json()["type"] == "email_taken"


def test_register_duplicate_username_is_rejected(test_env: None) -> None:
    client = _client(test_env)
    _register(client, email="first@example.com", username="sameuser")

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "username": "sameuser",
            "password": "correct-horse-battery",
        },
    )

    assert response.status_code == 409
    assert response.json()["type"] == "username_taken"


def test_login_with_correct_password_returns_access_token(test_env: None) -> None:
    client = _client(test_env)
    _register(
        client, email="login-ok@example.com", username="loginok", password="correct-horse-battery"
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login-ok@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_login_with_wrong_password_is_rejected(test_env: None) -> None:
    client = _client(test_env)
    _register(
        client, email="login-bad@example.com", username="loginbad", password="correct-horse-battery"
    )

    response = client.post(
        "/api/v1/auth/login", json={"email": "login-bad@example.com", "password": "totally-wrong"}
    )

    assert response.status_code == 401
    assert response.json()["type"] == "invalid_credentials"


def test_login_with_unknown_email_gives_same_error_as_wrong_password(test_env: None) -> None:
    """Enumeration-resistance check — see InvalidCredentialsError's docstring."""
    client = _client(test_env)

    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody-here@example.com", "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json()["type"] == "invalid_credentials"


def test_me_requires_a_bearer_token(test_env: None) -> None:
    client = _client(test_env)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_rejects_a_garbage_token(test_env: None) -> None:
    client = _client(test_env)
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_returns_the_authenticated_users_profile(test_env: None) -> None:
    client = _client(test_env)
    _register(
        client, email="whoami@example.com", username="whoami", password="correct-horse-battery"
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "whoami@example.com", "password": "correct-horse-battery"},
    )
    token = login_response.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "whoami@example.com"
