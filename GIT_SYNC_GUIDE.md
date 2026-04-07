# Git Sync Guide for IATB Repository

## Problem Analysis

### Original Error
```
error: src refspec feature/instrument-scanner does not match any
error: failed to push some refs to 'github.com:npmvlKP/IATB-02Apr26.git'
```

### Root Cause
1. **Wrong Branch Name**: You tried to push `feature/instrument-scanner` but your current branch is `optimize/instrument-scanner`
2. **Unstaged Changes**: You have 9 unstaged modified files that need to be staged before committing
3. **Untracked Files**: 2 new Python scripts need to be added to Git
4. **No Remote Branch**: The branch `optimize/instrument-scanner` doesn't exist on remote yet (first push)

## Solution Overview

Two Python scripts have been created to automate verification and sync:

### 1. `verify_git_state.py` - Verification Script
Checks repository state and provides actionable recommendations.

### 2. `sync_to_remote.py` - Sync Script
Automates the complete process: stage → commit → push → verify.

---

## Python Script Execution Steps

### Step 1: Verify Current State
```bash
python verify_git_state.py
```

**What it does:**
- Checks current branch and remote tracking
- Identifies staged, unstaged, and untracked files
- Verifies push readiness
- Provides specific recommendations

**Expected Output:**
- Shows branch: `optimize/instrument-scanner`
- Shows 35 staged files
- Shows 9 unstaged modified files
- Shows 2 untracked files
- Provides full sequence of commands to run

---

### Step 2: Sync to Remote (Automated)
```bash
python sync_to_remote.py
```

**What it does:**
1. **Stage All Changes**: Runs `git add -A` to stage all modified, new, and deleted files
2. **Create Commit**: Creates a commit with automatic message:
   ```
   feat(instrument-scanner): quality gate fixes and updates
   ```
3. **Push to Remote**: Pushes to correct branch `origin/optimize/instrument-scanner`
4. **Verify Sync**: Confirms local and remote are in sync

**Expected Output:**
- Shows progress through each step
- Displays commit hash
- Shows push success message
- Verifies local and remote match

---

## Manual Git Commands (Alternative)

If you prefer manual commands instead of the Python scripts:

### Option A: Quick Sync (All Changes)
```bash
# Step 1: Stage everything
git add -A

# Step 2: Commit with message
git commit -m "feat(instrument-scanner): quality gate fixes and updates"

# Step 3: Push to correct branch (sets upstream tracking)
git push -u origin optimize/instrument-scanner
```

### Option B: Selective Staging
```bash
# Step 1: Stage only specific files
git add fix_*.py
git add sync_to_remote.py verify_git_state.py

# Step 2: Commit
git commit -m "feat(instrument-scanner): quality gate fixes and updates"

# Step 3: Push
git push -u origin optimize/instrument-scanner
```

---

## Why the Original Command Failed

### Wrong Branch Reference
```bash
# ❌ WRONG - branch doesn't exist locally
git push origin feature/instrument-scanner

# ✅ CORRECT - use actual current branch
git push origin optimize/instrument-scanner
```

### Missing Commit
- You had staged files but never committed them
- Git cannot push uncommitted changes
- Must commit before pushing

### First Push Requires Upstream Tracking
```bash
# For first push to new remote branch, use -u flag
git push -u origin optimize/instrument-scanner
```

---

## Branch Information

### Current State
- **Local Branch**: `optimize/instrument-scanner`
- **Remote Branch**: Does not exist yet (will be created on first push)
- **Remote URL**: `git@github.com:npmvlKP/IATB-02Apr26.git`

### Why This Branch?
The branch `optimize/instrument-scanner` exists locally but was created from a different branch. The remote branch `feature/instrument-scanner` is a different branch entirely.

---

## Verification After Sync

### Check Sync Status
```bash
# Verify local and remote match
git fetch origin
git rev-parse HEAD
git rev-parse origin/optimize/instrument-scanner
# Both should show the same commit hash
```

### View Commit History
```bash
git log --oneline -5
```

### Check Remote Branches
```bash
git branch -r
# Should now show: remotes/origin/optimize/instrument-scanner
```

---

## Summary of Changes Being Pushed

### Staged Files (35 files)
- Modified: `AGENTS.md`, `config/exchanges.toml`, `pyproject.toml`
- Modified: Various source files in `src/iatb/`
- Modified: Test files in `tests/`
- New: Quality gate scripts in `scripts/`
- New: Fix scripts (`fix_*.py`)
- New: `G7_Floats_Found.csv`, `verify_intraday_enforcement.py`

### Unstaged Files (9 files)
- Modified: `fix_*.py` scripts (8 files)
- Modified: `src/iatb/scanner/instrument_scanner.py`

### Untracked Files (2 files)
- `verify_git_state.py` (new)
- `sync_to_remote.py` (new)

---

## Troubleshooting

### Error: "failed to push some refs"
**Cause**: Remote has commits that local doesn't have
**Solution**:
```bash
git fetch origin
git rebase origin/optimize/instrument-scanner
git push -u origin optimize/instrument-scanner
```

### Error: "Updates were rejected because the tip of your current branch is behind"
**Cause**: Remote branch has diverged
**Solution**:
```bash
git pull --rebase origin optimize/instrument-scanner
git push -u origin optimize/instrument-scanner
```

### Error: "Permission denied (publickey)"
**Cause**: SSH key not configured
**Solution**:
```bash
# Check SSH key
ssh -T git@github.com

# If fails, generate new key
ssh-keygen -t ed25519 -C "your_email@example.com"
# Then add to GitHub account
```

---

## Best Practices

1. **Always verify before pushing**: Run `python verify_git_state.py` first
2. **Use Python scripts for automation**: They handle edge cases and provide clear feedback
3. **Commit frequently**: Don't let staged changes sit uncommitted
4. **Push after commit**: Keep remote in sync with local
5. **Use meaningful commit messages**: Follow conventional commits format

---

## Quick Reference

```bash
# Verify state
python verify_git_state.py

# Automated sync (recommended)
python sync_to_remote.py

# Manual sync (alternative)
git add -A && git commit -m "feat(instrument-scanner): quality gate fixes and updates" && git push -u origin optimize/instrument-scanner

# Check status
git status

# View recent commits
git log --oneline -5

# Verify sync
git fetch origin && git diff HEAD origin/optimize/instrument-scanner
```

---

## Conclusion

The original error occurred because:
1. You referenced a non-existent branch name
2. You had unstaged changes
3. You hadn't committed your staged changes

**Recommended Action**: Run `python sync_to_remote.py` to automatically fix all issues and push your changes to the correct remote branch.