# Gamedrop — Claude Code guidelines

## Testing

Always add tests when implementing a new feature. Tests live in `backend/tests/`.
Run with: `python -m pytest /home/drblank/projects/gamedrop/backend/tests/ -q`

New feature = new test. No exceptions.

## Database migrations

Migrations are sacred — never destructive, always idempotent.
Use `alembic revision --autogenerate` to generate; never write migration files by hand.

## API versioning

App is in alpha. No backward compat needed for API or frontend — break freely.
Only the DB schema (migrations) must remain stable.
