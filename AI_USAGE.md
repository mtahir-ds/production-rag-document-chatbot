# AI_USAGE.md — AI Assistance Log

This document records all significant uses of AI assistance during the development of the Production RAG Document Chatbot, in accordance with the project's transparency requirements.

---

## Summary

| Phase | AI Tool | Purpose |
|-------|---------|---------|
| Project planning | Antigravity (Claude) | Requirement extraction, milestone breakdown |
| M1 — Foundation | Antigravity | FastAPI skeleton, Pydantic settings, logging config |
| M2 — Ingestion | Antigravity | Multi-format extractors, token-aware chunker, Qdrant wrapper |
| M3 — RAG + Guardrails | Antigravity | Retrieval service, Gemini generation, guardrails, pytest suite |
| M4 — Corpus + Eval Dataset | Claude AI (separate session) | Generated 5 sample corporate policy documents + 36 golden QA pairs |
| M5 — Frontend + Observability | Antigravity | Metrics API, JWT auth, SPA frontend (HTML/CSS/JS) |
| M6 — Evaluation | Antigravity | RAGAS-style evaluation script, EVAL.md report |
| M7 — Documentation | Antigravity | README.md, DESIGN.md, Dockerfile, docker-compose.yml |

---

## Detailed Log

### M1 — Foundation & Configuration

**What was AI-assisted:**
- FastAPI `create_app()` factory pattern with lifespan context manager
- Pydantic v2 `Settings` class structure and field defaults
- Structured logging with `contextvars`-based request ID propagation
- Initial `schemas.py` Pydantic model layout

**What was human-directed:**
- Decision to use SQLite (not PostgreSQL) for portability
- Rate limit values and JWT lifetime defaults
- Project directory structure

---

### M2 — Document Ingestion Pipeline

**What was AI-assisted:**
- PyMuPDF text extraction with Tesseract OCR fallback logic
- `python-docx` and `python-pptx` extractors
- `tiktoken`-based token-aware chunking with metadata preservation
- SHA-256 duplicate detection pattern
- Qdrant collection schema and upsert batching logic
- SQLite WAL mode and foreign key pragma setup

**What was human-directed:**
- Choice of 500-token chunk size and 80-token overlap (after reviewing RAGAS literature)
- Decision to store raw files in `uploads/` and use SHA-256 as the deduplication key

---

### M3 — RAG, Generation, and Guardrails

**What was AI-assisted:**
- Grounded generation prompt template (strict document-only grounding)
- `[[chunk_id]]` citation extraction regex
- Output guardrail: hallucinated citation stripping logic
- Input guardrail: injection and jailbreak pattern library
- Off-topic classifier heuristics
- Full pytest suite (14 tests) covering health, ingestion, RAG, guardrails, rate limiting

**What was human-directed:**
- Similarity threshold choice (0.35)
- Decision to use `answered=False` as the abstention signal (not an HTTP error code)
- Off-topic category definitions

---

### M4 — Sample Corpus and Golden Dataset

**What was AI-assisted (Claude AI, separate session):**
- Generated 5 realistic corporate policy documents:
  - `hr_policy.pdf` — HR & leave policy
  - `remote_work_policy.docx` — Remote work guidelines
  - `security_policy.txt` — IT security rules
  - `travel_expense_policy.md` — Travel & expense policy
  - `onboarding_guide.pdf` — New hire onboarding guide
- Generated 36-question golden QA dataset (`evals/golden_qa_dataset.json`):
  - 28 answerable questions (including multi-part and paraphrase questions)
  - 8 unanswerable questions (out-of-scope topics)

**Prompt used (provided to Claude):**
> *Generate 5 realistic corporate policy documents for a fictional company "TechNova" covering HR, remote work, IT security, travel expenses, and new hire onboarding. Then generate a golden QA evaluation dataset with 28 answerable and 8 unanswerable questions distributed across all documents, including at least 3 multi-part questions and 3 paraphrase questions.*

**What was human-reviewed:**
- Verified factual consistency across all documents (no contradictions)
- Verified that unanswerable questions truly have no answer in any document
- Spot-checked 10 Q&A pairs against the source text

---

### M5 — Frontend, Observability, and Auth

**What was AI-assisted:**
- `DatabaseManager.get_metrics_summary()` SQL aggregation query
- `AuthService` JWT creation/verification with PyJWT
- `bcrypt` password hashing integration
- Metrics API router and traces endpoint
- Full SPA frontend: dark-mode glassmorphism CSS design system, chat UI with citations panel, chunks drawer, metrics modal, auth modal, drag-and-drop upload

**What was human-directed:**
- UX flow: left sidebar for documents, center for chat, right for chunks
- Decision to use vanilla JS (no framework) for zero build-step deployment

---

### M6 — Evaluation

**What was AI-assisted:**
- RAGAS-style proxy metric implementations (faithfulness, relevancy, precision, recall)
- Evaluation runner with retry logic and per-question scoring
- EVAL.md report writer

**What was human-directed:**
- Decision to use token-overlap proxy metrics instead of LLM-judge to avoid API cost during evaluation

---

### M7 — Documentation and Deployment

**What was AI-assisted:**
- Full `README.md` with Mermaid architecture diagram, API table, environment variable table
- `DESIGN.md` technical decisions document
- `Dockerfile` multi-stage build
- `docker-compose.yml` service definitions

**What was human-directed:**
- Reviewing all generated content for technical accuracy before commit

---

## AI Tools Used

| Tool | Version / Model | Use |
|------|----------------|-----|
| Antigravity (Google DeepMind) | Claude Sonnet (Thinking) | Primary development agent — code generation, testing, documentation |
| Claude AI (Anthropic) | Claude 3.5 Sonnet | Corpus document generation and golden dataset creation (M4 only) |

---

## Code Ownership

All generated code was reviewed, understood, and accepted by the developer before commit. No code was blindly copied without comprehension. The developer is responsible for the correctness, security, and fitness-for-purpose of all code in this repository, regardless of its origin.
