
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import APIError
from src.models.account import Account
from src.models.transaction import Transaction
from src.schemas.transaction import TransactionCreate


def create_transaction(
    db: Session,
    account_id: uuid.UUID,
    data: TransactionCreate,
) -> Transaction:
    try:
        # Lock the account row before checking or changing its balance.
        account = db.scalar(
            select(Account)
            .where(Account.id == account_id)
            .with_for_update()
        )

        if account is None:
            raise APIError(
                404, "ACCOUNT_NOT_FOUND", "Account not found."
            )

        # Friendly duplicate check; the unique index remains authoritative.
        existing = db.scalar(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.reference_id == data.reference_id,
            )
        )

        if existing is not None:
            raise APIError(
                409,
                "DUPLICATE_TRANSACTION",
                "This reference ID already exists for the account.",
            )

        amount = data.amount

        if data.type == "debit":
            if account.balance < amount:
                raise APIError(
                    409,
                    "INSUFFICIENT_BALANCE",
                    "The account does not have sufficient funds.",
                )
            account.balance -= amount
        else:
            account.balance += amount

        transaction = Transaction(
            account_id=account_id,
            type=data.type,
            amount=amount,
            reference_id=data.reference_id,
        )
        db.add(transaction)

        # The balance update and transaction insert commit together.
        db.commit()
        db.refresh(transaction)
        return transaction

    except APIError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()

        # Handles duplicate references that race past the friendly check.
        # Other integrity errors should not be misreported as duplicates.
        constraint = getattr(
            getattr(exc.orig, "diag", None),
            "constraint_name",
            None,
        )

        if constraint == "uq_transactions_account_reference":
            raise APIError(
                409,
                "DUPLICATE_TRANSACTION",
                "This reference ID already exists for the account.",
            ) from exc

        raise
    except Exception:
        db.rollback()
        raise


def list_transactions(
    db: Session,
    account_id: uuid.UUID,
    page: int,
    page_size: int,
):
    account = db.get(Account, account_id)

    if account is None:
        raise APIError(404, "ACCOUNT_NOT_FOUND", "Account not found.")

    filters = [Transaction.account_id == account_id]
    offset = (page - 1) * page_size

    items = db.scalars(
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.created_at.desc(), Transaction.id)
        .offset(offset)
        .limit(page_size)
    ).all()

    total = db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(*filters)
    )

    return {
        "items": items,
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }
