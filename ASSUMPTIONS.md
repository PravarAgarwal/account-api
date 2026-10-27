# Assumptions and Design Decisions

## Accounts

- Each account has a unique UUID.
- An account is created with an initial balance of zero.
- Account balances cannot become negative.
- Monetary values are stored using fixed-precision decimal types.

## Transactions

- A transaction is either a credit or a debit.
- Transaction amounts must be greater than zero and have at most two decimal places.
- A transaction reference ID must be unique within an account.
- A credit increases the account balance; a debit decreases it.
- Transactions for accounts that do not exist are rejected.

## Money Transfers

- Source and destination accounts must both exist.
- An account cannot transfer money to itself.
- The source account must have sufficient funds.
- A successful transfer debits the source and credits the destination by the same amount.
- Both sides of a transfer are recorded as transactions.
- The balance changes and transaction records must commit together. If the operation fails, the entire transfer must roll back.
- Transfer reference IDs cannot conflict with existing transaction reference IDs on either participating account.

## API Behaviour

- Invalid request data is rejected with a validation error.
- Requests referencing nonexistent resources receive a not-found error.
- Insufficient funds and duplicate transaction references are rejected.
- Pagination is used for list endpoints that support it.

## Database and Testing

- PostgreSQL is the target database.
- Alembic manages schema migrations.
- Automated tests cover account operations, transaction processing, validation, and transfer atomicity.
- PostgreSQL integration tests use a dedicated test database separate from development or production data.
