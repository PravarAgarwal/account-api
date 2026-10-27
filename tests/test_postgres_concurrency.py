
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.db.session import Base, get_db
from src.main import app
from src.models import Account, Transaction

from decimal import Decimal
from sqlalchemy.exc import IntegrityError

from sqlalchemy import create_engine, func, select, text

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run PostgreSQL concurrency tests",
)


@pytest.fixture
def postgres_client():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )

    # This fixture is intended ONLY for the dedicated test database.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_account(client, initial_credit="100.00"):
    account_response = client.post(
        "/accounts",
        json={"name": "Concurrency Test Account"},
    )
    assert account_response.status_code == 201

    account_id = account_response.json()["id"]

    if initial_credit is not None:
        credit_response = client.post(
            f"/accounts/{account_id}/transactions",
            json={
                "type": "credit",
                "amount": initial_credit,
                "reference_id": "INITIAL-CREDIT",
            },
        )
        assert credit_response.status_code == 201

    return account_id


def submit_transaction(client, account_id, transaction_type, amount, reference):
    return client.post(
        f"/accounts/{account_id}/transactions",
        json={
            "type": transaction_type,
            "amount": amount,
            "reference_id": reference,
        },
    )


def get_account_balance(client, account_id):
    response = client.get(f"/accounts/{account_id}")
    assert response.status_code == 200
    return response.json()["balance"]


def get_transaction_count(account_id):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return connection.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.account_id == account_id)
            )
    finally:
        engine.dispose()


def test_concurrent_debits_cannot_overdraw_account(postgres_client):
    client = postgres_client
    account_id = create_account(client, initial_credit="100.00")

    # Two withdrawals compete for the same 100.00 balance.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                submit_transaction,
                client,
                account_id,
                "debit",
                "80.00",
                f"CONCURRENT-DEBIT-{number}",
            )
            for number in (1, 2)
        ]
        responses = [future.result() for future in futures]

    statuses = sorted(response.status_code for response in responses)

    # One withdrawal succeeds; the other must be rejected.
    assert statuses == [201, 409]

    failed = next(
        response for response in responses
        if response.status_code == 409
    )
    assert failed.json()["error"]["code"] == "INSUFFICIENT_BALANCE"

    assert get_account_balance(client, account_id) == "20.00"

    # One initial credit and exactly one successful debit.
    assert get_transaction_count(account_id) == 2


def test_concurrent_duplicate_references_are_rejected(postgres_client):
    client = postgres_client
    account_id = create_account(client, initial_credit=None)

    # Both requests use the same reference ID for the same account.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                submit_transaction,
                client,
                account_id,
                "credit",
                "25.00",
                "SAME-REFERENCE",
            )
            for _ in range(2)
        ]
        responses = [future.result() for future in futures]

    statuses = sorted(response.status_code for response in responses)

    assert statuses == [201, 409]

    failed = next(
        response for response in responses
        if response.status_code == 409
    )
    assert failed.json()["error"]["code"] == "DUPLICATE_TRANSACTION"

    assert get_account_balance(client, account_id) == "25.00"
    assert get_transaction_count(account_id) == 1

def test_database_rejects_nonpositive_transaction_amount(postgres_client):
    client = postgres_client
    account_id = create_account(client, initial_credit="100.00")

    # Confirm the account has one legitimate transaction.
    assert get_account_balance(client, account_id) == "100.00"
    assert get_transaction_count(account_id) == 1

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    try:
        with engine.begin() as connection:
            connection.execute(
                Transaction.__table__.insert().values(
                    account_id=account_id,
                    type="credit",
                    amount=Decimal("0.00"),
                    reference_id="INVALID-DIRECT-INSERT",
                )
            )
    except IntegrityError:
        pass
    else:
        pytest.fail("Database accepted a transaction with a zero amount.")
    finally:
        engine.dispose()

    # The invalid insert must not affect existing account data.
    assert get_account_balance(client, account_id) == "100.00"
    assert get_transaction_count(account_id) == 1


def test_failed_transaction_insert_rolls_back_balance(postgres_client):
    client = postgres_client
    account_id = create_account(client, initial_credit="100.00")

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    try:
        # Force PostgreSQL to reject a specific transaction insert.
        # This simulates a database failure after the service updates
        # the account balance but before the transaction can be committed.
        with engine.begin() as connection:
            connection.execute(
                text("""
                    CREATE OR REPLACE FUNCTION test_reject_transaction_insert()
                    RETURNS trigger
                    LANGUAGE plpgsql
                    AS $$
                    BEGIN
                        IF NEW.reference_id = 'FORCE-FAIL' THEN
                            RAISE EXCEPTION 'Forced transaction insert failure';
                        END IF;
                        RETURN NEW;
                    END;
                    $$;
                """)
            )

            connection.execute(
                text("""
                    CREATE TRIGGER test_reject_transaction_insert_trigger
                    BEFORE INSERT ON transactions
                    FOR EACH ROW
                    EXECUTE FUNCTION test_reject_transaction_insert();
                """)
            )

        response = submit_transaction(
            client,
            account_id,
            "debit",
            "40.00",
            "FORCE-FAIL",
        )

        # The database error should be handled by the API.
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "DATABASE_ERROR"

        # Neither the balance nor the transaction history may change.
        assert get_account_balance(client, account_id) == "100.00"
        assert get_transaction_count(account_id) == 1

    finally:
        # Remove the test-only trigger and function.
        with engine.begin() as connection:
            connection.execute(
                text("""
                    DROP TRIGGER IF EXISTS
                    test_reject_transaction_insert_trigger
                    ON transactions;
                """)
            )
            connection.execute(
                text("""
                    DROP FUNCTION IF EXISTS test_reject_transaction_insert();
                """)
            )

        engine.dispose()


def test_database_rejects_invalid_transaction_type(postgres_client):
    client = postgres_client
    account_id = create_account(client, initial_credit=None)

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    try:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    Transaction.__table__.insert().values(
                        account_id=account_id,
                        type="transfer",
                        amount=Decimal("10.00"),
                        reference_id="INVALID-TYPE",
                    )
                )
    finally:
        engine.dispose()

    assert get_account_balance(client, account_id) == "0.00"
    assert get_transaction_count(account_id) == 0


def test_database_rejects_negative_account_balance(postgres_client):
    client = postgres_client
    account_id = create_account(client, initial_credit="100.00")

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    try:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        UPDATE accounts
                        SET balance = -1.00
                        WHERE id = :account_id
                    """),
                    {"account_id": account_id},
                )
    finally:
        engine.dispose()

    assert get_account_balance(client, account_id) == "100.00"
    assert get_transaction_count(account_id) == 1


def test_accounts_have_independent_balances(postgres_client):
    client = postgres_client
    account_a = create_account(client, initial_credit="100.00")
    account_b = create_account(client, initial_credit="50.00")

    response = submit_transaction(
        client,
        account_a,
        "debit",
        "30.00",
        "ACCOUNT-A-DEBIT",
    )
    assert response.status_code == 201

    assert get_account_balance(client, account_a) == "70.00"
    assert get_account_balance(client, account_b) == "50.00"

    assert get_transaction_count(account_a) == 2
    assert get_transaction_count(account_b) == 1


def test_same_reference_is_allowed_for_different_accounts(postgres_client):
    client = postgres_client
    account_a = create_account(client, initial_credit=None)
    account_b = create_account(client, initial_credit=None)

    first = submit_transaction(
        client, account_a, "credit", "25.00", "SHARED-REFERENCE"
    )
    second = submit_transaction(
        client, account_b, "credit", "40.00", "SHARED-REFERENCE"
    )

    assert first.status_code == 201
    assert second.status_code == 201

    assert get_account_balance(client, account_a) == "25.00"
    assert get_account_balance(client, account_b) == "40.00"

    assert get_transaction_count(account_a) == 1
    assert get_transaction_count(account_b) == 1


def test_transaction_endpoints_return_404_for_missing_account(postgres_client):
    client = postgres_client
    missing_account_id = "00000000-0000-0000-0000-000000000001"

    create_response = client.post(
        f"/accounts/{missing_account_id}/transactions",
        json={
            "type": "credit",
            "amount": "10.00",
            "reference_id": "MISSING-ACCOUNT",
        },
    )
    list_response = client.get(
        f"/accounts/{missing_account_id}/transactions"
    )

    assert create_response.status_code == 404
    assert create_response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"

    assert list_response.status_code == 404
    assert list_response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"



def test_failed_transfer_rolls_back_both_accounts(postgres_client):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    try:
        # Create the accounts.
        source_response = postgres_client.post(
            "/accounts", json={"name": "Transfer Source"}
        )
        destination_response = postgres_client.post(
            "/accounts", json={"name": "Transfer Destination"}
        )

        assert source_response.status_code == 201
        assert destination_response.status_code == 201

        source_id = source_response.json()["id"]
        destination_id = destination_response.json()["id"]

        # Give each account an initial balance.
        source_credit = postgres_client.post(
            f"/accounts/{source_id}/transactions",
            json={
                "type": "credit",
                "amount": "100.00",
                "reference_id": "SOURCE-INITIAL",
            },
        )
        destination_credit = postgres_client.post(
            f"/accounts/{destination_id}/transactions",
            json={
                "type": "credit",
                "amount": "50.00",
                "reference_id": "DESTINATION-INITIAL",
            },
        )

        assert source_credit.status_code == 201
        assert destination_credit.status_code == 201

        # Force PostgreSQL to reject one of the transfer's transaction inserts.
        with engine.begin() as connection:
            connection.execute(
                text("""
                    CREATE OR REPLACE FUNCTION test_reject_transfer_insert()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        IF NEW.reference_id = 'TRANSFER-FORCE-FAIL' THEN
                            RAISE EXCEPTION 'Forced transfer insert failure';
                        END IF;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
            )
            connection.execute(
                text("""
                    CREATE TRIGGER trg_reject_transfer_insert
                    BEFORE INSERT ON transactions
                    FOR EACH ROW
                    EXECUTE FUNCTION test_reject_transfer_insert();
                """)
            )

        # Attempt a transfer that must fail at the database layer.
        response = postgres_client.post(
            "/transfers",
            json={
                "source_account_id": source_id,
                "destination_account_id": destination_id,
                "amount": "30.00",
                "reference_id": "TRANSFER-FORCE-FAIL",
            },
        )

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "DATABASE_ERROR"

        # Both original balances must remain unchanged.
        source_after = postgres_client.get(
            f"/accounts/{source_id}"
        ).json()
        destination_after = postgres_client.get(
            f"/accounts/{destination_id}"
        ).json()

        assert source_after["balance"] == "100.00"
        assert destination_after["balance"] == "50.00"

        # Neither side of the failed transfer may be recorded.
        source_transactions = postgres_client.get(
            f"/accounts/{source_id}/transactions"
        ).json()
        destination_transactions = postgres_client.get(
            f"/accounts/{destination_id}/transactions"
        ).json()

        assert source_transactions["total"] == 1
        assert destination_transactions["total"] == 1

    finally:
        # Remove the test trigger so it cannot affect other tests.
        with engine.begin() as connection:
            connection.execute(
                text("""
                    DROP TRIGGER IF EXISTS trg_reject_transfer_insert
                    ON transactions;
                """)
            )
            connection.execute(
                text("""
                    DROP FUNCTION IF EXISTS test_reject_transfer_insert();
                """)
            )
        engine.dispose()
