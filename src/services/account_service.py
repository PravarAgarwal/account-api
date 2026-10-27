
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.exceptions import APIError
from src.models.account import Account
from src.schemas.account import AccountCreate


def create_account(db: Session, data: AccountCreate) -> Account:
    name = data.name.strip()

    if not name:
        raise APIError(422, "INVALID_ACCOUNT_NAME", "Account name is required.")

    account = Account(name=name, balance=0)
    db.add(account)

    try:
        db.commit()
        db.refresh(account)
        return account
    except Exception:
        db.rollback()
        raise


def get_account(db: Session, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id)

    if account is None:
        raise APIError(404, "ACCOUNT_NOT_FOUND", "Account not found.")

    return account


def list_accounts(db: Session, page: int, page_size: int):
    offset = (page - 1) * page_size

    items = db.scalars(
        select(Account)
        .order_by(Account.created_at.desc(), Account.id)
        .offset(offset)
        .limit(page_size)
    ).all()

    total = db.scalar(select(func.count()).select_from(Account))

    return {
        "items": items,
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }
