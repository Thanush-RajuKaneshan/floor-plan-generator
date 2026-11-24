"""Grounded chatbot and plan review on a local Ollama model. No training needed.

Answers are grounded in (1) passages retrieved from the local DCPR-2034 text by
keyword scoring (BM25) and (2) the facts of the user's latest generated plan.
If Ollama is not running, the chatbot falls back to the rule-based glossary.
"""

import json
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from functools import lru_cache

from chatbot_rules import answer_question

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
CHUNKS_PATH = os.path.join(os.path.dirname(__file__), "dcpr_parser", "enhanced_dcpr_chunks.json")

_STOPWORDS = set(
    "a an and are as at be by can do does for from how i in is it my of on or "
    "the this to what when where which who why will with you your me about".split()
)

SYSTEM_PROMPT = (
    "You are the assistant inside a floor-plan concept generator for Mumbai plots. "
    "Answer the user's question using ONLY the DCPR-2034 passages and the plan facts "
    "provided. Cite DCPR passages as [p.<page>]. If the passages do not contain the "
    "answer, say so plainly instead of guessing. Never claim a plan is approved or "
    "code-compliant; generated plans are early concepts that a licensed architect must "
    "review. Be concise: at most about 150 words unless the user asks for detail."
)

REVIEW_PROMPT = (
    "You are a cautious reviewer of an early schematic apartment floor-plan concept. "
    "Review only the structured facts supplied. Identify at most three specific, "
    "actionable design questions or improvements, using the design_issues and "
    "geometry_checks. Do not invent dimensions or claim regulatory compliance. "
    "Keep the answer under 120 words."
)


def _tokens(text: str):
    return [t for t in re.findall(r"[a-z0-9.]+", text.lower()) if t not in _STOPWORDS]


@lru_cache(maxsize=1)
def _index():
    with open(CHUNKS_PATH, encoding="utf-8") as handle:
        chunks = json.load(handle)["chunks"]
    docs = [Counter(_tokens(chunk["text"])) for chunk in chunks]
    doc_freq = Counter(term for doc in docs for term in doc)
    avg_len = sum(sum(doc.values()) for doc in docs) / max(1, len(docs))
    return chunks, docs, doc_freq, avg_len


def retrieve(question: str, k: int = 6):
    """Top-k DCPR passages by BM25 score."""
    chunks, docs, doc_freq, avg_len = _index()
    terms = set(_tokens(question))
    if not terms:
        return []
    n = len(docs)
    scored = []
    for chunk, doc in zip(chunks, docs):
        length = sum(doc.values())
        score = 0.0
        for term in terms & doc.keys():
            idf = math.log(1 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            tf = doc[term]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg_len))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: -item[0])
    return [
        {"page": chunk["metadata"].get("page_number"), "text": chunk["text"][:1200]}
        for _, chunk in scored[:k]
    ]


def _ollama_chat(messages, timeout: float = 120.0) -> str:
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }).encode()
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            answer = json.load(response)["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Ollama returned {exc.code}. Is the model pulled? Run: ollama pull {OLLAMA_MODEL}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"The local AI model is not reachable at {OLLAMA_URL}. Start it with: ollama serve"
        ) from exc
    if not answer:
        raise RuntimeError("The local AI model returned an empty answer.")
    return answer


def chat(message: str, history=None, plan_facts=None) -> dict:
    """Answer a question; falls back to the rule-based glossary if Ollama is down."""
    passages = retrieve(message)
    context = "DCPR-2034 passages:\n" + (
        "\n\n".join(f"[p.{p['page']}] {p['text']}" for p in passages) or "(none found)"
    )
    if plan_facts:
        context += "\n\nUser's latest generated plan (facts):\n" + json.dumps(plan_facts)
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
    for turn in (history or [])[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})
    try:
        answer = _ollama_chat(messages)
    except RuntimeError:
        return {"answer": answer_question(message), "sources": [], "backend": "rules"}
    return {
        "answer": answer,
        "sources": sorted({p["page"] for p in passages if p["page"] is not None}),
        "backend": OLLAMA_MODEL,
    }


def review_plan(plan_facts: dict) -> dict:
    """Advisory design review of a generated plan; raises RuntimeError if Ollama is down."""
    text = _ollama_chat([
        {"role": "system", "content": REVIEW_PROMPT},
        {"role": "user", "content": json.dumps(plan_facts)},
    ])
    return {"reviewer": "local_language_model", "advisory_only": True,
            "text": text, "model": OLLAMA_MODEL}
