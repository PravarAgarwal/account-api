
def test_create_account(client):
    response = client.post(
        "/accounts",
        json={"name": "Test Account"},
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Test Account"
    assert data["balance"] == "0.00"
    assert "id" in data
    assert "created_at" in data


def test_get_account(client):
    created = client.post(
        "/accounts",
        json={"name": "Savings"},
    ).json()

    response = client.get(f"/accounts/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["name"] == "Savings"


def test_get_nonexistent_account(client):
    response = client.get(
        "/accounts/00000000-0000-0000-0000-000000000001"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_create_account_with_blank_name(client):
    response = client.post(
        "/accounts",
        json={"name": "   "},
    )

    assert response.status_code == 422


def test_list_accounts_pagination(client):
    for name in ["Account A", "Account B", "Account C"]:
        response = client.post("/accounts", json={"name": name})
        assert response.status_code == 201

    response = client.get("/accounts?page=1&page_size=2")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2

def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_account_uuid_returns_validation_error(client):
    response = client.get("/accounts/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_pagination_is_rejected(client):
    response = client.get("/accounts?page=0&page_size=20")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_page_size_above_limit_is_rejected(client):
    response = client.get("/accounts?page=1&page_size=101")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
