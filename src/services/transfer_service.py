
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import APIError
from src.models.account import Account
from src.models.transaction import Transaction
from src.schemas.transfer import TransferCreate


def transfer_money(db: Session, data: TransferCreate) -> dict:
    source_id = data.source_account_id
    destination_id = data.destination_account_id
    amount = data.amount

    try:
        # Always lock accounts in a consistent order to reduce deadlocks.
        account_ids = sorted([source_id, destination_id], key=str)

        accounts = db.scalars(
            select(Account)
            .where(Account.id.in_(account_ids))
            .order_by(Account.id)
            .with_for_update()
        ).all()

        accounts_by_id = {account.id: account for account in accounts}
        source = accounts_by_id.get(source_id)
        destination = accounts_by_id.get(destination_id)

        if source is None or destination is None:
            raise APIError(
                404,
                "ACCOUNT_NOT_FOUND",
                "Source or destination account not found.",
            )

        # A transfer reference must not already be used on either account.
        existing = db.scalar(
            select(Transaction.id).where(
                Transaction.account_id.in_([source_id, destination_id]),
                Transaction.reference_id == data.reference_id,
            ).limit(1)
        )
        if existing is not None:
            raise APIError(
                409,
                "DUPLICATE_TRANSACTION",
                "This reference ID already exists for one of the accounts.",
            )

        if source.balance < amount:
            raise APIError(
                409,
                "INSUFFICIENT_BALANCE",
                "The source account does not have sufficient funds.",
            )

        # Update both balances within the same database transaction.
        source.balance -= amount
        destination.balance += amount

        # Record both sides of the transfer.
        debit = Transaction(
            account_id=source_id,
            type="debit",
            amount=amount,
            reference_id=data.reference_id,
        )
        credit = Transaction(
            account_id=destination_id,
            type="credit",
            amount=amount,
            reference_id=data.reference_id,
        )

        db.add_all([debit, credit])

        # Flush both records and balance updates before committing.
        # Any constraint failure will roll back the entire operation.
        db.flush()
        db.commit()

        db.refresh(debit)

        return {
            "transfer_reference": data.reference_id,
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "amount": amount,
            "source_balance": source.balance,
            "destination_balance": destination.balance,
            "created_at": debit.created_at,
        }

    except APIError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(
            getattr(exc.orig, "diag", None),
            "constraint_name",
            None,
        )
        if constraint == "uq_transactions_account_reference":
            raise APIError(
                409,
                "DUPLICATE_TRANSACTION",
                "This reference ID already exists for one of the accounts.",
            ) from exc
        raise
    except Exception:
        db.rollback()
        raise
