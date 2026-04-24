# IATB STRICT CHECKLIST CONTRACT — PROJECT RULE

This file defines strict agent behavior for the IATB repository.
It is beginner-friendly, explicit, and execution-focused.

---

## 0) Scope and Trigger (Mandatory)

This strict contract is active ONLY when BOTH conditions are true:
- The request is strictly relevant to repository `G:\IATB-02Apr26\IATB`.
- The user explicitly includes the literal trigger `/Agnt` in the same request.

Applies to project-scoped tasks such as:
- Creating, modifying, reviewing, validating, testing, running, debugging, or documenting project files/components.
- Requests referencing repository files, modules, scripts, tests, CI, DB setup, infra, or git changes.

Does NOT apply when:
- The request is general knowledge or not tied to this repository.
- `/Agnt` is not explicitly included.

Default behavior rule:
- If `/Agnt` is missing, treat the request with normal routine behavior.
- If `/Agnt` is present and scope is ambiguous, ask one clarification question.

---

## 1) Repo Routing

| Current Working Directory | Remote Repository |
|---------------------------|-------------------|
| `G:\AG\AG11Dec25` | `git@github.com:npmvlKP/AG11Dec25.git` |
| `G:\IATB-02Apr26\IATB` | `git@github.com:npmvlKP/IATB-02Apr26.git` |

---

## 2) Objective (What strict mode does)

For `/Agnt` + project-scoped tasks, the agent must produce:
- Complete implementation evidence
- Deterministic test evidence
- Validation gate evidence
- Win11 PowerShell execution runbook
- Git sync status report
- Zero-assumption reporting

---

## 3) Execution Flow

```
IMPLEMENT → GATES(G1–G10) → DEBUG/FIX(max 3) → RE-VERIFY → COMMIT-READY
```

---

## 4) Strict Rules

| Rule | Description |
|-------|-------------|
| Evidence-only | No assumptions. No placeholders/TODOs. |
| Fail-closed | Safety-first approach. |
| Decimal-only finance | No float in financial paths. |
| UTC-aware datetime | No naive `datetime.now()`. |
| Structured logging | No `print()` in src/. |
| Function size | ≤50 LOC per function. |
| Debug cycles | Max 3 debug cycles allowed. |

---

## 5) Quality Gates (All must pass, every phase)

| Gate | Command | Expected Result |
|------|---------|-----------------|
| **G1** Lint | `poetry run ruff check src/ tests/` | 0 violations |
| **G2** Format | `poetry run ruff format --check src/ tests/` | 0 reformats |
| **G3** Types | `poetry run mypy src/ --strict` | 0 errors |
| **G4** Security | `poetry run bandit -r src/ -q` | 0 high/medium |
| **G5** Secrets | `gitleaks detect --source . --no-banner` | 0 leaks |
| **G6** Tests | `poetry run pytest --cov=src/iatb --cov-fail-under=90 -x` | All pass ≥90% |
| **G7** No float | Python Script to ascertain the non-availability of 'float' in this said project codebase | 0 float in financial calculations (API boundary conversions with comments allowed) |
| **G8** No naive dt | Python Script to ascertain the non-availability of 'naive datetime' in this said project codebase | 0 naive datetime |
| **G9** No print | Python Script to ascertain the non-availability of 'print()' statements in this said project codebase| 0 print() statements |
| **G10** Func size | Function LOC check | ≤50 LOC each |

---

## 6) Mandatory Checklist (`/Agnt` + project-scoped tasks)

Before final delivery, ALL must be satisfied:

| # | Checklist Item | Requirement |
|---|----------------|-------------|
| 1 | Changed Files | File name + storage location + one-line purpose (not full content by default) |
| 2 | Tests | Test file name + storage location + one-line coverage intent |
| 3 | Test Coverage | Happy path, edge cases, error paths, type handling, precision handling, timezone handling |
| 4 | External APIs | Mocked in tests |
| 5 | Comprehensive and sequential Win11 Python scripts execution commands |
| 6 | Validation Steps | Python scripts includes validation steps and git sync to completion |
| 7 | Git Sync Report |Local git source control should not show "still pending", make sure all of them proposelry taken care duly following the git add, commit & push commands | Branch name, commit hash, and push status |
| 8 | Output Contract | Follows Section 9 exactly |
| 9 | Validation Gates | All G1–G10 addressed |
| 10 | No Assumptions | Unknowns explicitly listed as blockers |

For tasks without `/Agnt` or out-of-scope general issues:
- Use normal concise behavior.
- Do not force strict Section 9 format.
- Do not trigger AUTO-FAIL contract.

---

## 7) On Failure Policy

If ANY strict checklist item or gate cannot be satisfied:

**Output ONLY:**
```
Verdict: AUTO-FAIL → failed gate → evidence → required fix → next input
```

**Hard-stop rules:**
- No partial success language.
- No "completed" or "done" claims.
- No normal strict Section 9 delivery when AUTO-FAIL is active.

**AUTO-FAIL Format:**
1. Verdict: AUTO-FAIL
2. Failed Checklist Item(s): numbered list
3. Evidence Missing: exact data/file/test/gate missing
4. Required Next Input: exact user input needed to proceed

---

## 8) Response Format

| Column | Description |
|--------|-------------|
| Verdict | PASS / AUTO-FAIL |
| Repo Detected | Repository path |
| Change Summary | Brief description of changes |
| Gate Status | G1–G10 status (✓/✗) |
| Evidence | Links, outputs, proof |
| Blockers/Next | Blocking issues or next steps |

---

## 9) Output Contract (Exact section order for strict mode)

If a task-specific Section 9 contract is provided in prompt context, use it exactly.
If not provided, use this strict default contract exactly in this order:

### 9.1 Checklist Compliance Matrix (10/10 required)
| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Changed Files | PASS/FAIL | ... |
| 2 | Tests | PASS/FAIL | ... |
| 3 | Test Coverage | PASS/FAIL | ... |
| 4 | External APIs Mocked | PASS/FAIL | ... |
| 5 | PowerShell Block | PASS/FAIL | ... |
| 6 | Validation Steps | PASS/FAIL | ... |
| 7 | Git Sync Report | PASS/FAIL | ... |
| 8 | Output Contract | PASS/FAIL | ... |
| 9 | Validation Gates | PASS/FAIL | ... |
| 10 | No Assumptions | PASS/FAIL | ... |

### 9.2 Changed Files
| File Name | Storage Location | Purpose |
|-----------|------------------|---------|
| ... | ... | ... |

*(Explicitly write "No file changes" if none)*

### 9.3 Tests
| Test File Name | Storage Location | Coverage Intent |
|----------------|------------------|-----------------|
| ... | ... | ... |

*(Explicitly write "No test file changes" if none)*

### 9.4 Validation Gates (Status)
| Gate | Command | Status | Notes |
|------|---------|--------|-------|
| G1 | `poetry run ruff check src/ tests/` | ✓/✗ | ... |
| G2 | `poetry run ruff format --check src/ tests/` | ✓/✗ | ... |
| G3 | `poetry run mypy src/ --strict` | ✓/✗ | ... |
| G4 | `poetry run bandit -r src/ -q` | ✓/✗ | ... |
| G5 | `gitleaks detect --source . --no-banner` | ✓/✗ | ... |
| G6 | `poetry run pytest --cov=src/iatb --cov-fail-under=90 -x` | ✓/✗ | ... |
| G7 | Float check in financial paths | ✓/✗ | ... |
| G8 | Naive datetime check | ✓/✗ | ... |
| G9 | Print statement check | ✓/✗ | ... |
| G10 | Function size check | ✓/✗ | ... |

### 9.5 Win11 Python Scripts (Sequential)

# Step 1: Verify/Install dependencies
poetry install

# Step 2: Run Quality Gates (G1-G5)
poetry run ruff check src/ tests/
poetry run ruff format --check src/ tests/
poetry run mypy src/ --strict
poetry run bandit -r src/ -q
gitleaks detect --source . --no-banner

# Step 3: Run Tests (G6)
poetry run pytest --cov=src/iatb --cov-fail-under=90 -x

# Step 4: Additional Checks (G7-G10)
# G7: No float in financial paths
# G8: No naive datetime
# G9: No print statements
# G10: Function size ≤50 LOC

# Step 5: Git Sync
git init
$branch = git rev-parse --abbrev-ref HEAD
$context = Prepare the prompted context
git status
git add -A or git add .
git commit -m "Update: $context - $(Get-Date -Format 'yyyy-MM-dd')"
git pull --rebase --autostash origin $branch
git push origin $branch
git push origin main
git remote -v
git status
git log --oneline -5
```

### 9.6 Git Sync Report
| Field | Value |
|-------|-------|
| Current Branch | ... |
| Latest Commit Hash | ... |
| Push Status | Success/Failure + remote/branch target |

### 9.7 Assumptions and Unknowns
*(Explicitly write "None" if no assumptions)*

---

## 10) Beginner Mode (How to execute safely)

For strict tasks, explain:
- **What** is being changed
- **Where** files are located
- **How** to run installation and tests
- **How** to verify pass/fail quickly

Use plain language and step-by-step sequencing.

---

## 11) Git Rules (post all-gates-pass, user-confirmed)

| Rule | Description |
|------|-------------|
| Commit Style | Conventional commits (`type(scope): description`) |
| Push Policy | Never auto-push without confirmation |
| Branch Naming | Descriptive, kebab-case |

---

## 12) `/Agnt` Command Usage (Simple)

Use `/Agnt` by appending it in the same message as the task.

**Examples:**
- `Create scripts/init-db.sql with this SQL ... /Agnt`
- `Fix failing tests in tests/unit/test_api.py /Agnt`
- `Implement new feature in src/iatb/core/engine.py /Agnt`

**Behavior:**
- With `/Agnt` + project scope: strict protocol is enforced.
- Without `/Agnt`: normal routine behavior is used.

---

## 13) Reusable Strict Template Prompt (Copy/Paste)

```
TEMPLATE START
You are in STRICT CHECKLIST MODE.
Apply this strict mode ONLY if:
1) task is strictly relevant to repository G:\IATB-02Apr26\IATB, and
2) the request includes /Agnt.
If either condition is false, use normal routine behavior.

Task:
{describe task} /Agnt

Mandatory checklist (all required, no exceptions):
1) Changed Files section shows file name + storage location + purpose
2) Tests section shows test file name + storage location + coverage intent
3) Tests cover happy path, edge cases, errors, types, precision, timezone
4) External APIs mocked in tests
5) Win11 Comprehensive Python scripts complete and sequential
6) Python scripts includes validation + git sync to completion
7) Git sync reports branch name, commit hash, push status
8) Output follows Section 9 contract exactly
9) All validation gates (G1-G10) addressed
10) No assumptions made

Output contract (exact order):
1. Checklist Compliance Matrix (10 rows: PASS/FAIL + evidence)
2. Changed Files (File Name + Storage Location + Purpose)
3. Tests (File Name + Storage Location + Coverage Intent)
4. Validation Gates (G1-G10 Status)
5. Win11 Comprehensive Python scripts complete and sequential
6. Git Sync Report
7. Assumptions and Unknowns

Auto-fail rule:
If any checklist row is FAIL or missing, do not produce normal strict output.
Return only:
1. Verdict: AUTO-FAIL
2. Failed Checklist Item(s)
3. Evidence Missing
4. Required Next Input
TEMPLATE END
```

---

## 14) Global Rule Variant (Same Policy Across All Repos)

Use the block below as Warp Global Rule description.

```
GLOBAL RULE START
Mode: STRICT CHECKLIST + AUTO-FAIL (EXPLICIT /Agnt TRIGGER, PROJECT-SCOPED ONLY)

Scope trigger (ALL required):
- Request is repository/project-specific.
- Request explicitly contains /Agnt.

Fallback:
- If /Agnt is absent, use normal routine behavior.
- If request is general knowledge/non-project, use normal routine behavior.

Strict mandatory checklist:
1) Changed Files section shows file name + storage location + purpose
2) Tests section shows test file name + storage location + coverage intent
3) Tests cover happy path, edge cases, errors, types, precision, timezone
4) External APIs mocked in tests
5) Win11 Comprehensive Python scripts complete and sequential
6) PowerShell block includes validation + git sync to completion
7) Git sync reports branch name, commit hash, push status
8) Output follows exact section order contract
9) All validation gates (G1-G10) addressed
10) No assumptions made

Quality Gates (G1-G10):
G1: poetry run ruff check src/ tests/ → 0 violations
G2: poetry run ruff format --check src/ tests/ → 0 reformats
G3: poetry run mypy src/ --strict → 0 errors
G4: poetry run bandit -r src/ -q → 0 high/medium
G5: gitleaks detect --source . --no-banner → 0 leaks
G6: poetry run pytest --cov=src/iatb --cov-fail-under=90 -x → all pass ≥90%
G7: No float in financial paths
G8: No naive datetime.now()
G9: No print() in src/
G10: Function size ≤50 LOC

Default strict output contract (exact order):
1. Checklist Compliance Matrix (10 rows: PASS/FAIL + evidence)
2. Changed Files (File Name + Storage Location + Purpose)
3. Tests (File Name + Storage Location + Coverage Intent)
4. Validation Gates (G1-G10 Status)
5. Win11 Comprehensive Python scripts complete and sequential
6. Git Sync Report
7. Assumptions and Unknowns

Hard-stop AUTO-FAIL:
If any checklist item is FAIL or missing, do not produce normal strict output.
Return only:
1. Verdict: AUTO-FAIL
2. Failed Checklist Item(s)
3. Evidence Missing
4. Required Next Input

No partial completion claims are allowed when AUTO-FAIL is triggered.
GLOBAL RULE END
```

---

## 15) Quick Reference Card

| Trigger | Behavior |
|---------|----------|
| `/Agnt` + project scope | Strict mode with full checklist |
| No `/Agnt` | Normal routine behavior |
| General knowledge | Normal routine behavior |

| Gate | Quick Command |
|------|---------------|
| G1-G2 | `poetry run ruff check src/ tests/ && poetry run ruff format --check src/ tests/` |
| G3 | `poetry run mypy src/ --strict` |
| G4-G5 | `poetry run bandit -r src/ -q && gitleaks detect --source . --no-banner` |
| G6 | `poetry run pytest --cov=src/iatb --cov-fail-under=90 -x` |

---

**End of IATB Strict Contract**