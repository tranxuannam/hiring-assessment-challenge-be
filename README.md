# Hiring Assessment

## Backend

The FastAPI backend uses SQLAlchemy with a persistent database configured by
`DATABASE_URL`. Local development defaults to SQLite; set `DATABASE_URL` to a
PostgreSQL connection string for production. The application creates the
current schema on startup through `Base.metadata.create_all`.

From `D:\projects\hiring-assessment\hiring-assessment-example` in Windows
PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
python -m pytest
python -m uvicorn app.main:app --reload
```

The health endpoint is available at `GET /health`.

### Importing the synthetic data pack

The supplied pack is synthetic. Import the first ten answer records, their
questions, candidates, audio files, and queued scoring jobs with:

```powershell
python -m app.commands.import_data_pack "C:\Users\Nam Tran\Downloads\business-systems-pack"
```

Use `--limit 35` to import every answer JSON file. The importer is idempotent:
existing candidate/question/answer records are skipped, audio is copied to
`uploads\imported`, and no scores are fabricated.

Run the scoring worker after importing:

```powershell
python -m app.commands.run_scoring_worker --once
```

Use the command without `--once` to keep polling for new jobs. It requires
`LLM_API_KEY`. Text answers are scored by the configured real LLM; audio-only
answers remain `needs_human` until transcribed.

If a job fails, inspect its `last_error` value in `scoring_jobs`. Common
causes are an invalid or expired `LLM_API_KEY`, an unavailable model, rate
limits, network access, or an incorrect `LLM_BASE_URL`. Never print the API
key while diagnosing this.

Create a test assignment and receive a raw personal token:

```powershell
python -m app.commands.create_assignment C2041 --role "Backend Engineer"
```

Only the token hash is stored. The raw token is printed once.

Candidate assessment links are bearer-style random tokens; only their SHA-256
hashes are stored. Candidate responses expose question and progress state but
never scores. The HR demo uses the clearly labelled `X-Mock-HR-Email` header
after `POST /hr/mock-sign-in`; this is mock authentication for the take-home,
not production authentication.

### LLM scoring

Scoring uses the configured OpenAI-compatible API. Set `LLM_API_KEY` and
optionally `LLM_BASE_URL` and `LLM_MODEL` in `.env`; do not commit credentials.
The scoring service persists each job and score, accepts only JSON with an
integer score from 1 through 4 and a reason, and treats candidate answers as
untrusted data. Provider failures retry with backoff until
`SCORING_MAX_ATTEMPTS`; malformed model output is marked `needs_human`.
