
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.schemas.transfer import TransferCreate, TransferResponse
from src.services.transfer_service import transfer_money

router = APIRouter(prefix="/transfers", tags=["Transfers"])

DBSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=TransferResponse, status_code=201)
def create_transfer_endpoint(data: TransferCreate, db: DBSession):
    return transfer_money(db, data)
