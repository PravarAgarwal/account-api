
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TransferCreate(BaseModel):
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
    )
    reference_id: str = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.source_account_id == self.destination_account_id:
            raise ValueError(
                "Source and destination accounts must be different."
            )

        self.reference_id = self.reference_id.strip()
        if not self.reference_id:
            raise ValueError("Reference ID cannot be blank.")

        return self


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transfer_reference: str
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount: Decimal
    source_balance: Decimal
    destination_balance: Decimal
    created_at: datetime
