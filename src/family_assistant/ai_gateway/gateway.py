"""AI Gateway entry point (PRD Section 16.7).

The single internal entry consumed by the assistant router. Will orchestrate
prompt loading, Ollama LLM calls, retrieval (pgvector + keyword), tool
schema validation and dispatch, the confirmation policy (Section 11.6),
and AssistantInteraction logging (Section 11.10).
"""


def process_command(user_id: int, input_text: str):
    """Parse and dispatch a user command. See PRD Section 11."""
    raise NotImplementedError
