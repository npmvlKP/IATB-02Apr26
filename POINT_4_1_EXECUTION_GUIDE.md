# Point-4.1: Python Execution Steps & Git Sync Guide

## Overview

This guide provides straight Python script execution steps for verifying gates G7-G10 and sequential steps to update local development to the remote git repository.

---

## Part 1: Python Script Execution Steps

### Step 1: Verify Gates G7-G10

Run the comprehensive verification script:

```bash
python scripts/verify_g7_g8_g9_g10.py
```

**What it verifies:**
- **G7**: No float in financial paths (risk, backtesting, execution, selection, sentiment)
- **G8**: No naive datetime.now() in src/
- **G9**: No print() statements in src/
- **G10**: Function size <= 50 LOC in src/

**Expected Output:**
```
======================================================================
  IATB G7, G8, G9, G10 GATES VERIFICATION
======================================================================

======================================================================
  G7 - No Float in Financial Paths
======================================================================
[PASS] No float found in financial paths (PASS)

======================================================================
  G8 - No Naive Datetime
======================================================================
[PASS] No naive datetime.now() found (PASS)

======================================================================
  G9 - No Print Statements
======================================================================
[PASS] No print() found (PASS)

======================================================================
  G10 - Function Size <= 50 LOC
======================================================================
[PASS/FAIL] ...

======================================================================
  SUMMARY
======================================================================

Gates Passed: X/4
```

---

### Step 2: Interpret Results

**If all gates PASS:**
- Proceed to git sync steps (Part 2)

**If any gates FAIL:**
- Review the detailed violations shown in the output
- Fix the issues in the affected files
- Re-run: `python scripts/verify_g7_g8_g9_g10.py`
- Repeat until all gates pass

---

### Step 3: (Optional) Run All Quality Gates G1-G10

For complete verification including linting, formatting, type checking, security, secrets, and tests:

```bash
python scripts/verify_all_gates.py
```

---

## Part 2: Git Sync Steps (Local → Remote)

### Step 1: Check Current Git Status

```bash
git status
```

This shows:
- Current branch
- Modified files
- Staged files
- Untracked files

---

### Step 2: Stage All Changes

```bash
git add -A
```

This stages:
- All modified files
- All new files
- All deleted files

---

### Step 3: Verify Staged Changes

```bash
git status
```

Confirm all intended changes are staged.

---

### Step 4: Create Commit

```bash
git commit -m "type(scope): description"
```

**Commit Message Format (Conventional Commits):**
- `feat:` for new features
- `fix:` for bug fixes
- `refactor:` for code refactoring
- `docs:` for documentation changes
- `test:` for test changes
- `chore:` for maintenance tasks

**Example:**
```bash
git commit -m "feat(verification): add G7-G10 gate verification script"
```

---

### Step 5: Get Current Branch Name

```bash
git branch --show-current
```

Note the branch name (e.g., `optimize/instrument-scanner`)

---

### Step 6: Push to Remote

```bash
git push -u origin <branch-name>
```

**Replace `<branch-name>` with your actual branch from Step 5.**

**Example:**
```bash
git push -u origin optimize/instrument-scanner
```

The `-u` flag sets upstream tracking on the first push.

---

### Step 7: Verify Sync Success

```bash
git status
```

Should show:
```
Your branch is up to date with 'origin/<branch-name>'.
```

---

### Step 8: Verify Remote Commit

```bash
git fetch origin
git log --oneline -1
git log --oneline origin/<branch-name> -1
```

Both should show the same commit hash.

---

## Quick One-Liner (All Steps Combined)

```bash
git add -A && git commit -m "type(scope): description" && git push -u origin $(git branch --show-current) && git status
```

**Replace `type(scope): description` with your actual commit message.**

---

## Troubleshooting

### Error: "failed to push some refs"

**Cause:** Remote has commits that local doesn't have

**Solution:**
```bash
git fetch origin
git pull --rebase origin <branch-name>
git push -u origin <branch-name>
```

---

### Error: "Updates were rejected because the tip of your current branch is behind"

**Cause:** Remote branch has diverged

**Solution:**
```bash
git pull --rebase origin <branch-name>
git push -u origin <branch-name>
```

---

### Error: "Permission denied (publickey)"

**Cause:** SSH key not configured

**Solution:**
```bash
# Test SSH connection
ssh -T git@github.com

# If fails, generate new SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"
# Add the public key to GitHub account
```

---

### Error: "src refspec <branch> does not match any"

**Cause:** Wrong branch name referenced

**Solution:**
```bash
# Check actual branch name
git branch --show-current

# Use the correct branch name in push command
git push -u origin $(git branch --show-current)
```

---

## Verification After Sync

### Check Local vs Remote Match

```bash
git fetch origin
git diff HEAD origin/<branch-name>
```

Should produce no output (local and remote are identical).

---

### View Recent Commits

```bash
git log --oneline -5
```

---

### Check Remote Branches

```bash
git branch -r
```

Should now show: `remotes/origin/<branch-name>`

---

## Repository Information

- **Remote URL:** `git@github.com:npmvlKP/IATB-02Apr26.git`
- **Working Directory:** `G:\IATB-02Apr26\IATB`

---

## Summary

### Python Execution Steps:
1. `python scripts/verify_g7_g8_g9_g10.py`
2. Review results
3. Fix any failures (if any)
4. Re-run until all pass

### Git Sync Steps:
1. `git status` (check status)
2. `git add -A` (stage all)
3. `git commit -m "message"` (commit)
4. `git push -u origin $(git branch --show-current)` (push)
5. `git status` (verify sync)

---

## Notes

- Always run verification scripts before committing
- Use meaningful, conventional commit messages
- Verify sync success after pushing
- Keep remote in sync with local after each commit
- The `-u` flag is only needed for the first push to a new remote branch