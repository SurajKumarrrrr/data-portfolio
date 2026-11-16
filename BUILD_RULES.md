# Rules for the daily project builder

Goal: every project should make a German hiring manager for a Data Science / Data Engineering
Werkstudent role think "this person can already contribute". Quality over size.

## Output location
Build the project in `queue/<repo-name>/` (repo-name from roadmap.md). Include
`queue/<repo-name>/.repo.json`:
```json
{"description": "<= 120 chars, what it does + key tech", "topics": ["python", "data-engineering", "..."]}
```
The GitHub Action turns that folder into its own public repo. Do not put anything outside
`queue/<repo-name>/` except ticking the item in roadmap.md.

## Every project must have
- Working, idiomatic Python 3.11+ (and SQL where relevant). Small, readable modules, type hints, docstrings where useful.
- Data that works offline: a small bundled sample and/or a deterministic synthetic-data generator (fixed seed). If a real public dataset exists, add a `scripts/download_data.py` for it, but tests must never need the network.
- Tests with pytest that actually pass (run them before committing). Aim for meaningful coverage of the core logic.
- `requirements.txt` (pinned major versions) or `pyproject.toml`; `Makefile` with `install`, `test`, `run`.
- `.github/workflows/ci.yml` running lint (ruff) + tests on push.
- Dockerfile / docker-compose only when the project is about serving or orchestration.
- `.gitignore`, MIT `LICENSE` (Copyright Suraj Kumar Ajampudi).
- README.md in English with: one-line pitch, CI badge (`https://github.com/SurajKumarrrrr/<repo-name>/actions/workflows/ci.yml/badge.svg`), Problem, Approach (with a small architecture diagram in Mermaid when there is a pipeline), Results (real numbers produced by running the code), How to run, Project structure, What I'd do next, and a short "Interview notes" section: 3–5 bullets SK can use to explain design decisions.

## Don'ts
- No placeholder code, TODO stubs, or fake results. If something can't be run, don't claim results.
- No secrets or API keys. No scraping of sites whose terms forbid it.
- Keep it focused: roughly 300–1500 lines of code, finishable and understandable.
