
def create_account(client, name):
    response = client.post("/accounts", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def credit_account(client, account_id, amount, reference):
    return client.post(
        f"/accounts/{account_id}/transactions",
        json={
            "type": "credit",
            "amount": str(amount),
            "reference_id": reference,
        },
    )


def transfer(client, source_id, destination_id, amount, reference):
    return client.post(
        "/transfers",
        json={
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "amount": str(amount),
            "reference_id": reference,
        },
    )


def balance(client, account_id):
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200
    return response.json()["balance"]


def test_successful_transfer(client):
    source = create_account(client, "Source")
    destination = create_account(client, "Destination")

    assert credit_account(client, source, "100.00", "INITIAL").status_code == 201
    assert credit_account(client, destination, "50.00", "INITIAL").status_code == 201

    response = transfer(client, source, destination, "30.00", "TRANSFER-001")

    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == "30.00"
    assert data["source_balance"] == "70.00"
    assert data["destination_balance"] == "80.00"

    assert balance(client, source) == "70.00"
    assert balance(client, destination) == "80.00"

    source_transactions = client.get(
        f"/accounts/{source}/transactions"
    ).json()
    destination_transactions = client.get(
        f"/accounts/{destination}/transactions"
    ).json()

    assert source_transactions["total"] == 2
    assert destination_transactions["total"] == 2


def test_transfer_rejected_for_insufficient_balance(client):
    source = create_account(client, "Source")
    destination = create_account(client, "Destination")

    credit_account(client, source, "20.00", "INITIAL")

    response = transfer(client, source, destination, "30.00", "TRANSFER-002")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert balance(client, source) == "20.00"
    assert balance(client, destination) == "0.00"

    assert client.get(
        f"/accounts/{source}/transactions"
    ).json()["total"] == 1
    assert client.get(
        f"/accounts/{destination}/transactions"
    ).json()["total"] == 0


def test_transfer_rejected_when_account_is_missing(client):
    source = create_account(client, "Source")
    missing_id = "00000000-0000-0000-0000-000000000001"

    credit_account(client, source, "100.00", "INITIAL")

    response = transfer(client, source, missing_id, "10.00", "TRANSFER-003")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
    assert balance(client, source) == "100.00"


def test_transfer_rejects_same_account(client):
    account_id = create_account(client, "Single Account")

    response = transfer(
        client, account_id, account_id, "10.00", "TRANSFER-004"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert balance(client, account_id) == "0.00"


def test_transfer_rejects_duplicate_reference(client):
    source = create_account(client, "Source")
    destination = create_account(client, "Destination")

    credit_account(client, source, "100.00", "INITIAL")

    first = transfer(client, source, destination, "10.00", "TRANSFER-005")
    second = transfer(client, source, destination, "10.00", "TRANSFER-005")

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_TRANSACTION"

    assert balance(client, source) == "90.00"
    assert balance(client, destination) == "10.00"


def test_transfer_rejects_invalid_amount(client):
    source = create_account(client, "Source")
    destination = create_account(client, "Destination")

    for amount in ("0", "-5.00", "1.001"):
        response = transfer(
            client, source, destination, amount, f"INVALID-{amount}"
        )
        assert response.status_code == 422

    assert balance(client, source) == "0.00"
    assert balance(client, destination) == "0.00"
