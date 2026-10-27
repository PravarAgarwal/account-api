
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.schemas.transaction import (
    TransactionCreate,
    TransactionPage,
    TransactionResponse,
)
from src.services.transaction_service import (
    create_transaction,
    list_transactions,
)

router = APIRouter(
    prefix="/accounts/{account_id}/transactions",
    tags=["Transactions"],
)

DBSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=TransactionResponse, status_code=201)
def create_transaction_endpoint(
    account_id: uuid.UUID,
    data: TransactionCreate,
    db: DBSession,
):
    return create_transaction(db, account_id, data)


@router.get("", response_model=TransactionPage)
def list_transactions_endpoint(
    account_id: uuid.UUID,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return list_transactions(db, account_id, page, page_size)
