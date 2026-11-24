"""Advisory plan review by the local Ollama model (see llm_chat)."""

from llm_chat import review_plan


def review_plan_locally(plan_facts: dict) -> dict:
    return review_plan(plan_facts)
