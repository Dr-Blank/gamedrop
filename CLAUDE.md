# Gamedrop — Claude Code guidelines

## Testing

Always add tests when implementing a new feature. Tests live in `backend/tests/`.
Run with: `python -m pytest /home/drblank/projects/gamedrop/backend/tests/ -q`

New feature = new test. No exceptions.

## Database migrations

Migrations are sacred — never destructive, always idempotent.
Use `alembic revision --autogenerate` to generate; never write migration files by hand.

## Comments & docstrings

Never put a specific site name, user detail, or anything from a chat session in
code or comments. Code stays generic.

Comment only what the code can't say itself. No narration, no restating the
line below. Prefer clearer code over a comment.

Docstrings: one short line. Add one more line only when a non-obvious
architectural choice needs a reminder of *why*.

## Commits

One commit per feature or fix — whatever makes a self-contained, reviewable
change. Split work up as you go rather than landing one large diff at the end.

Small means coherent, not trivial: don't split a feature into one-line commits
that do nothing on their own, and don't pad the history. If a feature genuinely
needs a big diff, one commit is fine.

Conventional Commits, one line, no body, no trailers.

## API versioning

App is in alpha. No backward compat needed for API or frontend — break freely.
Only the DB schema (migrations) must remain stable.
