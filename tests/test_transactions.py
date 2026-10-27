
def create_account(client):
    response = client.post(
        "/accounts",
        json={"name": "Transaction Test Account"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_transaction(client, account_id, transaction_type, amount, reference):
    return client.post(
        f"/accounts/{account_id}/transactions",
        json={
            "type": transaction_type,
            "amount": str(amount),
            "reference_id": reference,
        },
    )


def get_balance(client, account_id):
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200
    return response.json()["balance"]


def test_credit_increases_balance(client):
    account_id = create_account(client)

    response = create_transaction(
        client, account_id, "credit", "1000.00", "CREDIT-001"
    )

    assert response.status_code == 201
    assert get_balance(client, account_id) == "1000.00"


def test_debit_decreases_balance(client):
    account_id = create_account(client)

    create_transaction(
        client, account_id, "credit", "1000.00", "CREDIT-001"
    )

    response = create_transaction(
        client, account_id, "debit", "250.00", "DEBIT-001"
    )

    assert response.status_code == 201
    assert get_balance(client, account_id) == "750.00"


def test_insufficient_balance_does_not_change_balance(client):
    account_id = create_account(client)

    response = create_transaction(
        client, account_id, "debit", "100.00", "DEBIT-001"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert get_balance(client, account_id) == "0.00"

    transactions = client.get(
        f"/accounts/{account_id}/transactions"
    ).json()

    assert transactions["total"] == 0


def test_duplicate_reference_is_rejected(client):
    account_id = create_account(client)

    first = create_transaction(
        client, account_id, "credit", "1000.00", "REF-001"
    )
    assert first.status_code == 201

    duplicate = create_transaction(
        client, account_id, "credit", "1000.00", "REF-001"
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_TRANSACTION"
    assert get_balance(client, account_id) == "1000.00"

    transactions = client.get(
        f"/accounts/{account_id}/transactions"
    ).json()

    assert transactions["total"] == 1


def test_invalid_transaction_inputs_are_rejected(client):
    account_id = create_account(client)

    invalid_payloads = [
        {
            "type": "transfer",
            "amount": "10.00",
            "reference_id": "INVALID-001",
        },
        {
            "type": "credit",
            "amount": "0",
            "reference_id": "INVALID-002",
        },
        {
            "type": "debit",
            "amount": "-50.00",
            "reference_id": "INVALID-003",
        },
    ]

    for payload in invalid_payloads:
        response = client.post(
            f"/accounts/{account_id}/transactions",
            json=payload,
        )
        assert response.status_code == 422

    assert get_balance(client, account_id) == "0.00"


def test_transaction_pagination(client):
    account_id = create_account(client)

    for number in range(3):
        response = create_transaction(
            client,
            account_id,
            "credit",
            "10.00",
            f"PAGE-{number}",
        )
        assert response.status_code == 201

    first_page = client.get(
        f"/accounts/{account_id}/transactions?page=1&page_size=2"
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2

    second_page = client.get(
        f"/accounts/{account_id}/transactions?page=2&page_size=2"
    )

    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
