
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.schemas.account import AccountCreate, AccountPage, AccountResponse
from src.services.account_service import (
    create_account,
    get_account,
    list_accounts,
)

router = APIRouter(prefix="/accounts", tags=["Accounts"])

DBSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=AccountResponse, status_code=201)
def create_account_endpoint(data: AccountCreate, db: DBSession):
    return create_account(db, data)


@router.get("", response_model=AccountPage)
def list_accounts_endpoint(
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return list_accounts(db, page, page_size)


@router.get("/{account_id}", response_model=AccountResponse)
def get_account_endpoint(account_id: uuid.UUID, db: DBSession):
    return get_account(db, account_id)
