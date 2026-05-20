# Backlog

## Real backlog (worth picking up)

- **Expand assistant tool coverage as needs surface.** Starter tools cover the common write paths (grocery add / mark purchased, meal/lunch/exercise create, memory create/search). Add update/delete/duplicate variants when an actual user flow demands them, not as a "complete the matrix" exercise — PRD §11.5 explicitly frames the starter set as something to expand during build.
- **Add assistant read support for exercise history.** Today the assistant can write exercise entries but can't answer "how much did I run this week?". This is a real gap if you want conversational reads on exercise. Needs an `exercise.search`-style tool plus extending the command-aware prompt builder to pre-fetch exercise data for exercise-flavored commands.
- **Clarification Policy Phase 2 — self-repair retry on validation failure.** Per PRD §11.5a. When Pydantic rejects a tool call, feed the validation error back to the LLM once ("Your previous call failed validation: <error>. Either correct it or ask the user.") and accept the second response. Capped at one retry to bound latency and cost. Today the gateway is one-shot — invalid calls bounce with a generic "I couldn't act on that" reply, which wastes the LLM's ability to recover from its own shape errors.
- **Clarification Policy Phase 3 — multi-turn clarification threads.** Per PRD §11.5a. `assistant_interactions` gains `thread_id`; a new `confirmation_status = "pending_clarification"` lets the user's next message resume the same context ("which milk?" → "the 2%" → tool fires). Needs a migration and a small router change to thread messages through `process_command`. Real conversational follow-up — today every input is independent.

## Not really backlog (notes / deferred decisions)

- **`pgvector` image vs. plain Postgres.** Compose uses `pgvector/pgvector:pg16` but nothing in code touches vector columns or functions (embeddings deferred per scope §11.8). Leaving the image as-is costs nothing and keeps phase-2 embeddings a clean additive migration. No action unless you want to slim the image.
- **`subject_id` orphan cleanup for memories.** `Memory.subject_type` / `subject_id` is a polymorphic reference (no FK), so memories can be orphaned if a user or family member is deleted. Low real-world impact in a two-adult + few-kids household. Revisit only if orphans actually show up in the UI.
