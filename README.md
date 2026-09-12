# Quiz Bot

A production-grade Telegram quiz platform inspired by @QuizBot, with a unique
core feature: **upload a PDF and get an AI-generated quiz from its content.**

## 1. Features implemented

- Full main menu (Quiz Bank / Create Quiz / My Quizzes / Profile / Help / Language) with inline keyboards
- i18n: Uzbek (default), Russian, English — JSON locale files, no hardcoded strings in handlers
- PDF → AI quiz generation pipeline: upload → validate → extract (PyMuPDF) → OCR fallback (Tesseract) →
  clean → detect language → chunk → AI generation per chunk → dedupe (rapidfuzz) → Pydantic-validated
  structured output → persisted as a draft quiz → preview
- Manual quiz creation via Aiogram FSM (title → description → category → difficulty → questions loop)
- Topic-based AI quiz generation (no PDF, just a topic prompt)
- Public quiz bank with pagination, search, and creator attribution
- "My Quizzes" strictly scoped to `quiz.creator_id == current_user.id`, split by draft/published/archived
- Quiz taking flow: one question at a time, answer validation, explanation, live scoring, final result screen
- Quiz sharing via deep link (`t.me/<bot>?start=quiz_<uuid>`)
- Public/private visibility + draft/published/archived status model
- Categories (seeded on startup) with per-locale names
- User profile with aggregated statistics and a global points leaderboard
- Reporting system (spam/incorrect/inappropriate/copyright/other) with an open-reports admin queue
- Admin commands: ban/unban, delete quiz, list open reports, search users
- AI provider abstraction (`AIProvider` / `OpenAIProvider`) — swappable via `AI_PROVIDER` env var,
  works with any OpenAI-compatible endpoint (`AI_BASE_URL`)
- Structured-JSON-only AI output validated with Pydantic; automatic repair retry on invalid JSON;
  hard failure (no broken quiz saved) if repair also fails
- Redis-backed rate limiting (general message throttling + a stricter AI-generation bucket)
- Redis-backed FSM storage (aiogram `RedisStorage`), so flow state survives bot restarts
- Background processing via `arq` — PDF extraction + AI generation never blocks the bot's event loop
- Global error-handling middleware — no stack traces ever reach the user
- Structured logging (`structlog`)
- PDF security: MIME/extension/signature/size validation, encrypted-PDF rejection, random
  non-guessable temp filenames, guaranteed cleanup after processing
- Alembic migration for the full schema

## 2. Architecture

```
app/
  bot/            Telegram-facing layer only (handlers, keyboards, FSM states, middlewares, filters)
  core/           config, logging, security, enums — no business logic
  database/       SQLAlchemy models, repositories (query layer), session factory
  services/       business logic: ai/, pdf/, quiz/, users/, statistics/, reports/
  schemas/        Pydantic contracts (AI I/O, quiz creation DTOs)
  i18n/           locale JSON files + translator
  workers/        arq worker definitions
  main.py         bot process entrypoint
alembic/          migrations
tests/            pytest suite
```

Call chain for the flagship feature:

```
PDF handler (bot/handlers/pdf_quiz.py)
  -> validates upload, persists PdfDocument + QuizGeneration rows
  -> enqueues an arq job (does NOT block the bot)
      -> app/workers/arq_worker.py: generate_quiz_from_pdf_task
          -> PdfQuizPipelineService (services/quiz/pdf_pipeline_service.py)
              -> services/pdf/extractor.py   (PyMuPDF + Tesseract OCR fallback)
              -> services/pdf/chunker.py     (clean, detect language, split)
              -> services/ai/quiz_generator.py
                    -> services/ai/prompts.py (maintainable prompt templates)
                    -> AIProvider.complete()  (OpenAIProvider, or any future provider)
                    -> Pydantic validation -> JSON repair retry -> dedupe -> trim to N
              -> QuizService.create_quiz_from_ai -> QuizRepository (Postgres)
          -> sends live status edits + final preview back to the user via the Bot instance
```

Handlers never touch the database or call the AI provider directly — they call a service, which
calls repositories. This keeps Telegram-specific code out of business logic and makes the AI/PDF
pipeline independently testable and reusable (e.g. from a future admin API).

## 3. Permissions model

- **🧠 Quizlar bazasi (Quiz Bank)** — `QuizRepository.list_public()` — filters strictly on
  `visibility = public AND status = published`. Shows quizzes from **all** users.
- **🧩 Mening quizlarim (My Quizzes)** — `QuizRepository.list_by_creator(creator_id=current_user.id)`
  — filters strictly on `creator_id`. A user can never see another user's quizzes here, public or
  private. `QuizService._assert_owner()` re-enforces this on every mutating action (publish, archive,
  delete) by raising `QuizPermissionError` if `quiz.creator_id != requester_id`.
- Deep links (`?start=quiz_<id>`) can open a specific quiz directly; `QuizService.can_view()` allows
  it only if the quiz is public+published, or the viewer is the owner — private quizzes are not
  guessable/browsable but an owner sharing their own private link is not the scenario this blocks.

## 4. Requirements

- Python 3.12+
- PostgreSQL 15+
- Redis 7+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An OpenAI-compatible API key (OpenAI, Azure OpenAI, or any compatible gateway)
- Docker + Docker Compose (for containerized deployment)
- Tesseract OCR binary (only needed if `OCR_ENABLED=true`)

## 5. Environment variables

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token from BotFather |
| `ADMIN_IDS` | Comma-separated Telegram user IDs with admin access |
| `DATABASE_URL` | Async SQLAlchemy URL (`postgresql+asyncpg://...`) used by the bot/worker |
| `DATABASE_URL_SYNC` | Sync URL (`postgresql+psycopg2://...`) used by Alembic |
| `REDIS_URL` | Redis DB for arq queue + rate limiting |
| `REDIS_FSM_URL` | Redis DB for aiogram FSM storage (can be same instance, different DB index) |
| `AI_PROVIDER` | Currently `openai`; add new providers in `app/services/ai/factory.py` |
| `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` | AI backend configuration |
| `PDF_MAX_SIZE_MB` | Upload size limit |
| `OCR_ENABLED` | Enable Tesseract OCR fallback for scanned PDFs |
| `RATE_LIMIT_MESSAGES_PER_MINUTE`, `RATE_LIMIT_AI_PER_HOUR` | Throttling limits |

## 6. Telegram BotFather setup

1. Message [@BotFather](https://t.me/BotFather), run `/newbot`, follow the prompts.
2. Copy the token into `BOT_TOKEN` in `.env`.
3. Optional: `/setcommands` to register `/start` and `/admin` (admin-only, still safe to list).

## 7. AI API configuration

Works with OpenAI directly, or any OpenAI-compatible gateway (Azure OpenAI via a compatible proxy,
OpenRouter, local vLLM/Ollama servers exposing an OpenAI-compatible `/v1/chat/completions`, etc.) —
just set `AI_BASE_URL` and `AI_API_KEY` accordingly, no code changes required. To add a genuinely
different SDK/protocol, implement `AIProvider` (see `app/services/ai/base.py`) and register it in
`app/services/ai/factory.py`.

## 8. Database & Redis setup (local, no Docker)

```bash
# PostgreSQL
createdb quizbot

# Redis
redis-server
```

## 9. Install & run locally

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env   # then edit values

alembic upgrade head

python -m app.main            # bot process
arq app.workers.arq_worker.WorkerSettings   # worker process (separate terminal)
```

## 10. Running with Docker

```bash
docker compose up -d --build
```

This starts Postgres, Redis, runs migrations once (`migrate` service), then starts the `bot` and
`worker` containers. Logs:

```bash
docker compose logs -f bot worker
```

Stop:

```bash
docker compose down
```

## 11. Database migrations

```bash
# Apply all migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Generate a new migration after changing models
alembic revision --autogenerate -m "describe change"
```

## 12. Testing

```bash
pip install -r requirements.txt
pytest -q
```

The suite covers PDF validation, safe temp-file generation, text chunking, AI-response Pydantic
validation, duplicate-question detection, quiz visibility/permission rules, and score calculation.
These run without a live database. Repository-level integration tests should be run against a real
Postgres instance (`docker compose up -d postgres` first) since the schema uses native PostgreSQL
UUID columns.

## 13. Deployment notes

- Run `alembic upgrade head` as a release step before starting new bot/worker containers.
- Scale `worker` horizontally (multiple `arq` containers) if PDF/AI generation volume grows — arq
  jobs are safely picked up by whichever worker is free.
- Set `ENVIRONMENT=production` for JSON-structured logs.
- PDF temp files are deleted immediately after each pipeline run (success or failure); no PDF
  content is retained beyond that unless you extend `PdfDocument` storage intentionally.

## 14. Future improvements (architecture already allows these)

- Multiplayer/live quiz mode, group competitions
- Payments/subscriptions for premium quiz packs
- AI tutor / follow-up explanations per question
- Spaced repetition scheduling
- Web dashboard reusing the existing service layer via a thin FastAPI wrapper
- Certificates for completed quizzes
- Quiz recommendation engine based on `UserStatistics`
#   Q u i z - B o t  
 