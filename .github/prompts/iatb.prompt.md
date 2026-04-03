Activate IATB strict mode.

**Repo routing (auto-detect from cwd):**
- `G:\AG\AG11Dec25` → `git@github.com:npmvlKP/AG11Dec25.git`
- `G:\IATB02Apr26\iatb` → `git@github.com:npmvlKP/IATB-02Apr26.git`
- No match → normal mode; skip contract.

**Execution:** IMPLEMENT → GATES(G1–G10) → DEBUG/FIX(≤3) → RE-VERIFY

**Gates (run sequentially, stop on first fail):**
G1 `poetry run ruff check src/ tests/` → 0
G2 `poetry run ruff format --check src/ tests/` → 0
G3 `poetry run mypy src/ --strict` → 0
G4 `poetry run bandit -r src/ -q` → 0
G5 `gitleaks detect --source . --no-banner` → 0
G6 `poetry run pytest --cov=src/iatb --cov-fail-under=90 -x` → pass ≥90%
G7 grep float in financial paths → 0
G8 grep naive datetime.now() → 0
G9 grep print( in src/ → 0
G10 all functions ≤50 LOC

**On any gate fail → output only:**
`Verdict: AUTO-FAIL` + failed gate + evidence + fix + next input needed.

**Response (token-efficient):**
Verdict | Repo | Changes | Gate Status | Evidence | Next

**Rules:** Evidence-only. No assumptions. No placeholders. Fail-closed. Decimal finance. UTC datetime. Structured logging. ≤50 LOC/fn. Max 3 debug cycles.

**Git:** Conventional commits post-gates. No auto-push — confirm first.

Now execute the user's task below: