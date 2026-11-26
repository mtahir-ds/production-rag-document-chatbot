"""Input and output guardrails for prompt injection, jailbreak, off-topic, and leak protection."""

import logging
import re
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.logging_config import redact_secrets
from app.schemas import Citation, RetrievedChunk

logger = logging.getLogger(__name__)

# Prompt-injection and jailbreak patterns (Input Guardrail - M9).
_JAILBREAK_OR_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "prompt injection",
        re.compile(
            r"(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|above|system|safety)\s+(instructions|rules|prompts?)",
            re.IGNORECASE,
        ),
    ),
    (
        "system prompt extraction",
        re.compile(
            r"(reveal|show|print|dump|repeat|leak|expose)\s+(your\s+)?(system\s+prompt|hidden\s+instructions|api\s*key|secret|env(\s+variables?)?)",
            re.IGNORECASE,
        ),
    ),
    (
        "jailbreak attempt",
        re.compile(
            r"\b(jailbreak|dan\s+mode|developer\s+mode|unrestricted\s+mode|bypass\s+(safety|guardrails|restrictions)|act\s+as\s+an?\s+unfiltered)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role-tag spoofing",
        re.compile(r"</?(system|developer|assistant|instruction)>", re.IGNORECASE),
    ),
]

# Obvious off-topic non-document requests (e.g., creative writing, code generation, general trivia).
_OFF_TOPIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(write|generate|create)\s+(me\s+)?(a\s+)?(poem|story|song|joke|rap|haiku)\b", re.IGNORECASE),
    re.compile(r"^\s*(write|generate|build)\s+(me\s+)?(a\s+)?(python|javascript|java|c\+\+|html)\s+(script|code|program|game)\b", re.IGNORECASE),
    re.compile(r"^\s*(tell\s+me\s+a\s+joke|who\s+won\s+the\s+world\s+cup|what\s+is\s+the\s+weather)\b", re.IGNORECASE),
]

# Canary phrases that should never appear in user-facing model answers.
_SYSTEM_LEAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<retrieved_context>", re.IGNORECASE),
    re.compile(r"STRICT\s+GROUNDING\s+RULES", re.IGNORECASE),
    re.compile(r"GEMINI_API_KEY", re.IGNORECASE),
    re.compile(r"QDRANT_API_KEY", re.IGNORECASE),
]


@dataclass(slots=True)
class InputCheckResult:
    """Outcome of input validation and pre-retrieval guardrails."""

    cleaned_question: str
    is_off_topic: bool = False
    off_topic_reason: str | None = None


@dataclass(slots=True)
class OutputCheckResult:
    """Sanitized answer with verified citations pointing strictly to retrieved chunks."""

    answer: str
    answered: bool
    citations: list[Citation]
    guardrail_triggered: bool = False


def validate_question_input(question: str, max_length: int) -> InputCheckResult:
    """Validate question length/emptiness and block prompt-injection or jailbreak attempts."""
    cleaned = question.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question must not be empty or whitespace only.",
        )

    if len(cleaned) > max_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Question exceeds the maximum length of {max_length} characters.",
        )

    for label, pattern in _JAILBREAK_OR_INJECTION_PATTERNS:
        if pattern.search(cleaned):
            logger.warning("Blocked input by security guardrail (%s)", label)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request blocked by security guardrail: detected {label} attempt.",
            )

    for pattern in _OFF_TOPIC_PATTERNS:
        if pattern.search(cleaned):
            logger.info("Detected off-topic non-document request")
            return InputCheckResult(
                cleaned_question=cleaned,
                is_off_topic=True,
                off_topic_reason=(
                    "This assistant only answers questions based on your uploaded documents "
                    "and cannot fulfill general coding, creative writing, or off-topic requests."
                ),
            )

    return InputCheckResult(cleaned_question=cleaned)


def sanitize_and_verify_output(
    *,
    raw_answer: str,
    model_answered: bool,
    cited_chunk_ids: list[str],
    retrieved_chunks: list[RetrievedChunk],
) -> OutputCheckResult:
    """Redact leaked secrets/prompts and verify every citation against retrieved chunks."""
    sanitized_answer = redact_secrets(raw_answer).strip()

    for leak_pattern in _SYSTEM_LEAK_PATTERNS:
        if leak_pattern.search(sanitized_answer):
            logger.warning("Output guardrail blocked potential system prompt or config leak")
            return OutputCheckResult(
                answer="I cannot fulfill that request because it violates output security policies.",
                answered=False,
                citations=[],
                guardrail_triggered=True,
            )

    if not sanitized_answer:
        return OutputCheckResult(
            answer="The uploaded documents do not contain enough information to answer this question.",
            answered=False,
            citations=[],
            guardrail_triggered=False,
        )

    chunk_lookup = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
    verified_citations: list[Citation] = []
    seen_chunk_ids: set[str] = set()

    for cid in cited_chunk_ids:
        clean_id = cid.strip()
        if clean_id in chunk_lookup and clean_id not in seen_chunk_ids:
            chunk = chunk_lookup[clean_id]
            seen_chunk_ids.add(clean_id)
            verified_citations.append(
                Citation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_or_section=chunk.page_or_section,
                )
            )
        elif clean_id and clean_id not in chunk_lookup:
            logger.warning("Stripped unverified/hallucinated citation id '%s'", clean_id)

    # If the model claimed it answered using documents but provided zero valid citations,
    # abstain safely instead of returning uncited claims.
    if model_answered and not verified_citations:
        logger.warning("Model answer lacked verified retrieved citations; enforcing abstention")
        return OutputCheckResult(
            answer="The uploaded documents do not contain enough verifiable evidence to answer this question.",
            answered=False,
            citations=[],
            guardrail_triggered=True,
        )

    final_answered = bool(model_answered and verified_citations)
    final_citations = verified_citations if final_answered else []

    return OutputCheckResult(
        answer=sanitized_answer,
        answered=final_answered,
        citations=final_citations,
        guardrail_triggered=False,
    )
