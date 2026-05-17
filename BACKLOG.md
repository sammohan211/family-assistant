# Backlog

## Real backlog (worth picking up)

- **Expand assistant tool coverage as needs surface.** Starter tools cover the common write paths (grocery add / mark purchased, meal/lunch/exercise create, memory create/search). Add update/delete/duplicate variants when an actual user flow demands them, not as a "complete the matrix" exercise — PRD §11.5 explicitly frames the starter set as something to expand during build.
- **Add assistant read support for exercise history.** Today the assistant can write exercise entries but can't answer "how much did I run this week?". This is a real gap if you want conversational reads on exercise. Needs an `exercise.search`-style tool plus extending the command-aware prompt builder to pre-fetch exercise data for exercise-flavored commands.

## Not really backlog (notes / deferred decisions)

- **`pgvector` image vs. plain Postgres.** Compose uses `pgvector/pgvector:pg16` but nothing in code touches vector columns or functions (embeddings deferred per scope §11.8). Leaving the image as-is costs nothing and keeps phase-2 embeddings a clean additive migration. No action unless you want to slim the image.
- **`subject_id` orphan cleanup for memories.** `Memory.subject_type` / `subject_id` is a polymorphic reference (no FK), so memories can be orphaned if a user or family member is deleted. Low real-world impact in a two-adult + few-kids household. Revisit only if orphans actually show up in the UI.
