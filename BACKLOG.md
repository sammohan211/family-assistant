# Backlog

## Medium Priority

- Expand assistant tool coverage to match existing module capabilities such as delete, restore, duplicate, and update actions where appropriate.
- Add assistant read support for exercise history and any other module data that currently exists only in the HTML UI.
- Fix app/test configuration bootstrap so imports do not fail before startup when `.env` is absent or incomplete.

## Lower Priority

- Decide whether `pgvector` remains an active dependency during the keyword-only phase or should be removed until semantic retrieval lands. (Embeddings were deferred — see `memory/scope_decisions` §11.8.)
- Clean up `subject_id` orphans for memories pointing at deleted users or family members (non-FK references; not blocking).
