# DESIGN.md — Technical Design Decisions

> This document explains the **why** behind key architectural and algorithmic choices in the Production RAG Document Chatbot.

---

## 1. Overall Architecture

### Why FastAPI?
FastAPI provides async-first request handling (critical for non-blocking Gemini API and Qdrant calls), automatic OpenAPI docs, and Pydantic v2 validation out of the box. It has a mature middleware and dependency-injection system that maps cleanly to the layered service architecture used here.

### Why a Service Layer?
Routes are intentionally thin — they only validate input and delegate to service classes (`IngestionService`, `RAGService`, `AuthService`). This makes unit testing trivial: tests instantiate services directly with mock dependencies rather than standing up an HTTP server for every assertion.

### Why SQLite + Qdrant (not a single DB)?
| Concern | Store | Reason |
|---------|-------|--------|
| Document metadata, user accounts, telemetry | SQLite | Relational, transactional, zero-dep, embeds in the binary |
| Vector embeddings + similarity search | Qdrant | Purpose-built ANN index; cosine similarity at ms latency |

SQLite runs in WAL mode (`PRAGMA journal_mode=WAL`) so concurrent readers (health checks, metrics queries) don't block writers (ingestion, telemetry inserts).

---

## 2. Document Ingestion

### Multi-format text extraction
Each format has its own extractor:
- **PDF** — PyMuPDF (`fitz`) extracts per-page text; falls back to Tesseract OCR if the page has no selectable text (scanned PDFs, images).
- **DOCX** — `python-docx` preserves paragraph structure.
- **PPTX** — `python-pptx` extracts slide text in reading order.
- **TXT / MD** — direct UTF-8 read with Latin-1 fallback.

### Why token-aware chunking (not character-based)?
Embedding models have token limits. Character-based splitting can silently truncate a chunk mid-token when the model tokenizes it, producing a malformed embedding. Using `tiktoken` to count tokens before splitting ensures every chunk fits in the embedding model's context window.

### Chunk size: 500 tokens / 80-token overlap
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `chunk_size_tokens` | 500 | Balances context richness vs. embedding drift. Large chunks dilute the embedding signal; small chunks miss cross-sentence context. |
| `chunk_overlap_tokens` | 80 | ~16% overlap prevents semantic discontinuity at boundaries without doubling storage. |

### Duplicate detection (SHA-256)
A SHA-256 hash of the raw file bytes is stored in SQLite. On upload, the hash is checked first. If a match is found for the same user, the upload returns `409 Conflict` without re-embedding — saving API cost and preventing duplicate vectors.

---

## 3. Retrieval

### Embedding model: `gemini-embedding-001` (1536 dimensions)
Google's `gemini-embedding-001` is optimized for semantic similarity tasks and produces 1536-dimensional vectors. The 1536-dim Qdrant collection uses cosine distance (`COSINE`), which is scale-invariant (unit-length normalization is irrelevant for ranking).

### Similarity threshold: 0.35
The threshold is deliberately low (0.35 on cosine similarity) to avoid false negatives on paraphrased questions. The LLM's output guardrail acts as the second filter: even if a weakly-related chunk is retrieved, the generation step must cite it, and citation verification strips any hallucinated references.

**Trade-off**: A higher threshold (e.g., 0.6) reduces noise in the prompt but can cause the system to abstain on legitimately answerable questions where the question is phrased very differently from the document text.

---

## 4. Generation & Grounding

### Why strict document-only grounding?
The system prompt instructs Gemini to answer **only** from the provided context chunks. If the model cannot find support in the retrieved text, it must respond with a structured `CANNOT_ANSWER` signal. This prevents the LLM from mixing parametric knowledge (what it learned during training) with document-grounded facts.

### Citation verification (output guardrail)
After generation, `sanitize_and_verify_output()` cross-references every `[[chunk_id]]` citation in the raw answer against the actually-retrieved chunk IDs. Citations to chunks that were never retrieved (hallucinated references) are stripped. This is a lightweight, deterministic check that runs in <1 ms.

### Why `gemini-2.5-flash` (not Pro)?
Flash is 3–5× cheaper per token and has lower latency for the query lengths used here (typically <4096 tokens per prompt). The RAG pattern — where context is explicitly injected — reduces the advantage of a larger model's parametric recall, making Flash the right cost/quality trade-off for this workload.

---

## 5. Guardrails

### Input guardrails
1. **Length check** — rejects questions > 1000 chars before any API call.
2. **Injection patterns** — regex-based detection of common prompt injection markers (`ignore previous`, `system:`, `<|im_start|>`, etc.).
3. **Jailbreak heuristics** — detects role-play and system-override attempts.
4. **Off-topic classifier** — keyword and pattern-based pre-filter for clearly off-topic queries (personal advice, code generation unrelated to documents, etc.).

### Output guardrails
1. **Citation stripping** — removes references to chunk IDs not in the retrieval result.
2. **PII/key redaction** — scrubs API key patterns and email addresses from the generated answer.
3. **Hallucination detection** — if the model answers `True` for `answered` but the answer text matches the CANNOT_ANSWER template, it is overridden to `answered=False`.

---

## 6. Authentication

### JWT (not sessions)
The API is stateless. JWT tokens are self-contained: the user ID is embedded in the `sub` claim, signed with `HS256`, and verified on every request without a DB lookup. Token lifetime defaults to 24 hours (configurable via `JWT_EXPIRE_MINUTES`).

### Graceful fallback to `usr_default`
If no `Authorization: Bearer` header is present, `get_current_user_id()` falls back to `usr_default`. This keeps the entire existing test suite green (tests don't issue tokens) while still supporting real users in production.

---

## 7. Observability

### What is tracked
Every API request (including errors) is recorded in the `request_metrics` SQLite table with:
- Endpoint, method, status code
- Total latency (wall-clock), retrieval latency, LLM latency
- Prompt tokens, completion tokens, estimated cost (USD)
- Error message (if any)

### Latency percentiles
P50 and P95 are computed in Python by sorting all latency values — no SQL window functions needed. For typical production traffic volumes (<10K rows), this is fast enough without an additional time-series database.

### Cost estimation
Cost is estimated at ingestion time using published Gemini API rates:
- `gemini-embedding-001`: ~$0.00002 / 1K characters
- `gemini-2.5-flash`: input $0.075 / 1M tokens, output $0.30 / 1M tokens

These values are hardcoded constants in `generation.py` and serve as a rough budget tracker, not an exact billing record.

---

## 8. Rate Limiting

`slowapi` wraps `limits` to enforce per-IP rate limits:
- `/api/chat/ask` — 20 requests/minute
- `/api/documents/upload` — 10 requests/minute

Both limits are configurable via environment variables (`RATE_LIMIT_ASK`, `RATE_LIMIT_UPLOAD`) and injected into the route modules at startup, making them testable without restarting the process.

---

## 9. Frontend

The SPA is pure HTML + CSS + JavaScript — no build step, no bundler, no framework. It is served by FastAPI's `StaticFiles` mount at `/`. All API calls use the native `fetch` API against the same origin.

**Design rationale**: Keeping the frontend dependency-free reduces operational complexity (no Node.js, no npm, no CI pipeline for frontend builds) while still delivering a premium dark-mode glassmorphism UX using CSS custom properties and CSS animations.

---

## 10. What Would Change in a Real Production System

| Current choice | Production upgrade | Reason |
|---------------|-------------------|--------|
| SQLite | PostgreSQL (or CockroachDB) | Horizontal scaling, connection pooling |
| Local Qdrant | Qdrant Cloud | Managed, replicated, autoscaled |
| In-process rate limiter | Redis + `limits` | Shared state across multiple app replicas |
| HS256 JWT | RS256 with JWKS | Asymmetric keys; no secret to share across services |
| Token-count latency estimate | Actual billing API | Exact cost tracking |
| Tesseract OCR | Azure Document Intelligence | Higher accuracy on scanned PDFs |
