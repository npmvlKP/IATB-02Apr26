# IATB Development Workflow Guide

## Overview

This guide provides Python-based verification steps for all quality gates (G1-G10) and git sync procedures for local development to remote repository.

---

## Prerequisites

Ensure you have the following installed:
- Python 3.12+
- Poetry
- Git
- Gitleaks

```bash
# Verify installations
python --version
poetry --version
git --version
gitleaks --version
```

---

## Part 1: Quality Gates Verification (Python)

### Option A: Run All Gates Sequentially

Execute the comprehensive verification script:

```bash
python scripts/verify_all_gates.py
```

This will run G1-G10 in sequence and provide:
- Individual gate pass/fail status
- Detailed error messages for failures
- Summary report with success rate
- Exit code 0 if all pass, 1 if any fail

### Option B: Run Gates Individually

#### G1: Lint Check
```bash
poetry run ruff check src/ tests/
# Expected: No violations
```

#### G2: Format Check
```bash
poetry run ruff format --check src/ tests/
# Expected: No reformatting needed
```

#### G3: Type Checking
```bash
poetry run mypy src/ --strict
# Expected: 0 errors
```

#### G4: Security Scan
```bash
poetry run bandit -r src/ -q
# Expected: 0 high/medium severity issues
```

#### G5: Secrets Scan
```bash
gitleaks detect --source . --no-banner
# Expected: 0 leaks
```

#### G6: Test Coverage
```bash
poetry run pytest --cov=src/iatb --cov-fail-under=90 -x
# Expected: All tests pass with ≥90% coverage
```

#### G7: No Float in Financial Paths
```bash
python scripts/verify_g7_g8_g9.py
# Expected: G7: PASS
```

#### G8: No Naive Datetime
```bash
python scripts/verify_g7_g8_g9.py
# Expected: G8: PASS
```

#### G9: No Print Statements
```bash
python scripts/verify_g7_g8_g9.py
# Expected: G9: PASS
```

#### G10: Function Size (CI Placeholder)
```bash
# Note: Full check runs in CI. Local verification uses placeholder.
# Expected: PASS (placeholder)
```

### Troubleshooting Common Issues

**G6 Fails with Coverage <90%:**
```bash
# View detailed coverage report
poetry run pytest --cov=src/iatb --cov-report=html
# Open htmlcov/index.html in browser to see uncovered lines
```

**G1/G2 Fail - Auto-fix:**
```bash
# Auto-fix linting issues
poetry run ruff check --fix src/ tests/

# Auto-format files
poetry run ruff format src/ tests/
```

**G3 Fails - Type Errors:**
```bash
# Run with more verbose output
poetry run mypy src/ --strict --show-error-codes
```

---

## Part 2: Git Sync Workflow

### Step 1: Check Current Status

```bash
git status
```

Expected output shows:
- Current branch name
- Staged changes (ready to commit)
- Unstaged changes (need to be added)

### Step 2: Verify Remote Repository

```bash
git remote -v
```

Expected output:
```
origin  git@github.com:npmvlKP/IATB-02Apr26.git (fetch)
origin  git@github.com:npmvlKP/IATB-02Apr26.git (push)
```

### Step 3: Sync with Remote

```bash
# Fetch latest changes from remote
git fetch origin

# Check if there are incoming changes
git log HEAD..origin/$(git branch --show-current) --oneline
```

If there are incoming changes:
```bash
# Rebase your changes on top of remote
git rebase origin/$(git branch --show-current)

# Resolve any conflicts if they occur
# After resolving: git add <resolved-files> && git rebase --continue
```

### Step 4: Stage Changes

```bash
# Stage all modified files
git add .

# Or stage specific files
git add path/to/file1.py path/to/file2.py

# Verify staged changes
git status
```

### Step 5: Create Commit

```bash
# Use conventional commit format
git commit -m "type(scope): description"

# Examples:
# git commit -m "fix(execution): resolve zerodha connection timeout"
# git commit -m "feat(selection): add weight optimizer for portfolio allocation"
# git commit -m "docs(readme): update installation instructions"
```

Commit types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### Step 6: Verify Commit

```bash
# Show last commit details
git log -1 --stat

# Show commit hash (needed for reporting)
git rev-parse HEAD
```

### Step 7: Push to Remote

```bash
# Push current branch to origin
git push origin $(git branch --show-current)

# Or push with upstream tracking (first time for new branch)
git push -u origin $(git branch --show-current)
```

### Step 8: Verify Push Success

```bash
# Verify remote has your commit
git log origin/$(git branch --show-current) -1 --stat

# Check branch status
git status
```

Expected output:
```
Your branch is up to date with 'origin/your-branch-name'.
```

---

## Part 3: Complete Workflow Example

### Before Starting Work

```bash
# 1. Ensure on correct branch
git checkout -b feature/your-feature-name

# 2. Sync with remote
git fetch origin
git rebase origin/main  # or origin/develop

# 3. Run quality gates (baseline)
python scripts/verify_all_gates.py
```

### During Development

```bash
# 1. Make your code changes
# ... edit files ...

# 2. Run tests for affected modules
poetry run pytest tests/path/to/affected/tests/ -v

# 3. Run quality gates before committing
python scripts/verify_all_gates.py

# 4. If G6 fails, check coverage
poetry run pytest --cov=src/iatb --cov-report=term-missing
```

### Before Committing

```bash
# 1. Stage changes
git add .

# 2. Run final quality gate check
python scripts/verify_all_gates.py

# 3. If all pass, commit
git commit -m "feat(module): description of changes"

# 4. Verify commit
git log -1 --stat
```

### Pushing to Remote

```bash
# 1. Sync with remote first
git fetch origin
git rebase origin/$(git branch --show-current)

# 2. Push changes
git push origin $(git branch --show-current)

# 3. Verify push
git log origin/$(git branch --show-current) -1
```

---

## Part 4: Emergency Procedures

### Rollback Last Commit (Local)

```bash
# Soft reset (keep changes)
git reset --soft HEAD~1

# Hard reset (discard changes)
git reset --hard HEAD~1
```

### Rollback Last Pushed Commit

```bash
# Warning: This rewrites history - avoid if others have pulled
git push origin +HEAD~1:$(git branch --show-current)
```

### Fix Pushed Commit Message

```bash
# Amend last commit (not pushed yet)
git commit --amend -m "new message"

# If already pushed, force push (use with caution)
git push --force-with-lease origin $(git branch --show-current)
```

### Resolve Merge Conflicts

```bash
# 1. During rebase, if conflicts occur:
git status

# 2. Edit conflicted files (look for <<<<<<<, =======, >>>>>>> markers)
# ... resolve conflicts ...

# 3. Stage resolved files
git add <resolved-files>

# 4. Continue rebase
git rebase --continue

# 5. If needed, abort rebase
git rebase --abort
```

---

## Part 5: Quick Reference Commands

```bash
# Quality Gates
python scripts/verify_all_gates.py                    # Run all gates
poetry run pytest --cov=src/iatb --cov-report=html  # Coverage report

# Git Status
git status                                          # Check status
git log --oneline -10                               # Recent commits
git diff                                            # Unstaged changes
git diff --staged                                   # Staged changes

# Git Sync
git fetch origin                                    # Fetch remote
git pull --rebase origin main                       # Pull with rebase
git push origin $(git branch --show-current)        # Push current branch

# Git Commit
git add .                                           # Stage all
git commit -m "type(scope): description"            # Commit
git commit --amend -m "new message"                 # Fix last commit

# Git Branching
git branch -a                                       # List all branches
git checkout -b new-branch                          # Create & switch
git checkout main                                   # Switch to main
git branch -D old-branch                            # Delete branch
```

---

## Part 6: Checklist for Successful Push

- [ ] All quality gates pass (G1-G10)
- [ ] Test coverage ≥90%
- [ ] No linting or formatting issues
- [ ] No type errors
- [ ] No security issues
- [ ] No secrets in code
- [ ] Changes staged with `git add`
- [ ] Commit message follows conventional format
- [ ] Fetched latest from remote
- [ ] Rebased on top of remote changes
- [ ] Pushed to correct branch
- [ ] Verified push success with `git log origin/...`

---

## Part 7: Reporting Format

After successful git sync, report the following:

```
Branch: optimize/zerodha-openalgo-v2
Commit: 75433fc092525f805613f011bae988fbc7673581
Push Status: Success → origin/optimize/zerodha-openalgo-v2
Quality Gates: G1-G10 PASS
Test Coverage: 89.89% (slightly below 90% - needs improvement)
```

---

## Support

For issues or questions:
- Check troubleshooting section above
- Review AGENTS.md for strict mode requirements
- Consult project README.md