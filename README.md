# Account Transaction API

A REST API built with FastAPI, SQLAlchemy, and PostgreSQL for managing accounts, processing credits and debits, viewing transaction history, and transferring money between accounts.

## Features

- Create and retrieve accounts.
- List accounts with pagination.
- Credit and debit accounts.
- Retrieve account transaction history.
- Prevent transactions that would result in a negative account balance.
- Prevent duplicate transaction reference IDs on the same account.
- Transfer money between two accounts atomically.
- Validate request data and return structured API errors.
- Apply database schema changes using Alembic.

## Technology Stack

- Python 3.11
- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- Pydantic
- Pytest

## Prerequisites

- Python 3.11
- Docker Desktop
- Git

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd account-api
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root and configure `DATABASE_URL` for your PostgreSQL instance.

Example for the local Docker database:

```env
DATABASE_URL=postgresql+psycopg://account_user:local_dev_password@localhost:5432/account_db
```

Use appropriate credentials for your environment. Do not commit `.env` or real credentials to version control.

### 5. Start PostgreSQL

```powershell
docker compose up -d
```

Wait until the database is healthy before continuing.

### 6. Apply database migrations

```powershell
alembic upgrade head
```

### 7. Start the API

```powershell
uvicorn src.main:app --reload
```

The API should be available at `http://127.0.0.1:8000`.

## API Documentation

FastAPI provides interactive API documentation:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Main Endpoints

| Method | Endpoint                              | Purpose                         |
| ------ | ------------------------------------- | ------------------------------- |
| GET    | `/health`                             | Check API health                |
| GET    | `/health/db`                          | Check database connectivity     |
| POST   | `/accounts`                           | Create an account               |
| GET    | `/accounts`                           | List accounts                   |
| GET    | `/accounts/{account_id}`              | Retrieve an account             |
| POST   | `/accounts/{account_id}/transactions` | Record a credit or debit        |
| GET    | `/accounts/{account_id}/transactions` | List account transactions       |
| POST   | `/transfers`                          | Transfer funds between accounts |

Refer to `/docs` for request schemas, response schemas, status codes, and pagination parameters.

## Money Transfer Behaviour

A transfer requires a source account, a destination account, a positive amount, and a reference ID.

The API:

1. Verifies that both accounts exist.
2. Locks the relevant account rows during the operation.
3. Checks that the source has sufficient funds.
4. Debits the source and credits the destination.
5. Records both sides of the transfer.
6. Commits the changes together.

If the operation fails before commit, the database transaction is rolled back so a partial transfer is not persisted.

## Running Tests

Run the complete test suite:

```powershell
python -m pytest -v
```

The test suite includes API validation, account and transaction behaviour, and transfer scenarios. PostgreSQL-specific integration tests require a separate test database configured through `TEST_DATABASE_URL`.

**Warning:** The PostgreSQL integration tests recreate database tables. Configure `TEST_DATABASE_URL` to point only to a dedicated test database, never a production or personal database.

## Assumptions and Design Decisions

- Account balances use decimal monetary values rather than floating-point arithmetic.
- Account balances cannot be negative.
- Transaction amounts must be positive and use at most two decimal places.
- Transaction reference IDs must be unique per account.
- A transfer cannot use the same account as both source and destination.
- A transfer creates a debit record for the source and a credit record for the destination.
- Database migrations are managed using Alembic.
- API errors use structured responses with an error code and message.

## Project Structure

- `src/api/routes/` — API endpoints
- `src/core/` — shared application exceptions and core logic
- `src/db/` — database configuration and session management
- `src/models/` — SQLAlchemy models
- `src/schemas/` — Pydantic request and response schemas
- `src/services/` — account, transaction, and transfer business logic
- `tests/` — automated tests
- `migrations/` — database migrations
