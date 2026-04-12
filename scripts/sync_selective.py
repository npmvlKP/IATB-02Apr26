#!/usr/bin/env python3
"""
Git Selective Sync Script (Option B)
Automates selective staging, committing, and pushing specific files to remote repository
"""

import subprocess
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="G:/IATB-02Apr26/IATB")
    return result.returncode, result.stdout, result.stderr


def stage_specific_files(files: list[str]) -> bool:
    """Stage specific files for commit"""
    print("\n" + "=" * 70)
    print("STEP 1: STAGING SPECIFIC FILES")
    print("=" * 70)

    staged_count = 0

    for file_pattern in files:
        print(f"\nStaging: {file_pattern}")
        code, stdout, stderr = run_command(["git", "add", file_pattern])

        if code != 0:
            print(f"[WARN] Could not stage {file_pattern}: {stderr}")
        else:
            print(f"[OK] Staged: {file_pattern}")
            staged_count += 1

    if staged_count == 0:
        print("[FAIL] No files were staged")
        return False

    print(f"\n[OK] Successfully staged {staged_count} file patterns")

    # Show what was staged
    code, stdout, stderr = run_command(["git", "status", "--short"])
    if stdout.strip():
        print("\nStaged files:")
        for line in stdout.strip().split("\n"):
            print(f"  {line}")

    return True


def create_commit() -> bool:
    """Create a commit with staged changes"""
    print("\n" + "=" * 70)
    print("STEP 2: CREATING COMMIT")
    print("=" * 70)

    # Get current branch
    _, current_branch, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = current_branch.strip()

    # Generate commit message
    scope = current_branch.replace("optimize/", "").replace("feat/", "").replace("feature/", "")
    commit_msg = f"feat({scope}): selective file updates"

    print(f"Commit message: {commit_msg}")

    # Create commit
    code, stdout, stderr = run_command(["git", "commit", "-m", commit_msg])

    if code != 0:
        print(f"[FAIL] Failed to create commit: {stderr}")
        return False

    print("[OK] Commit created successfully")

    # Show commit details
    code, stdout, stderr = run_command(["git", "log", "-1", "--oneline"])
    print(f"Commit: {stdout.strip()}")

    return True


def push_to_remote() -> bool:
    """Push changes to remote repository"""
    print("\n" + "=" * 70)
    print("STEP 3: PUSHING TO REMOTE")
    print("=" * 70)

    # Get current branch
    _, current_branch, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = current_branch.strip()

    print(f"Pushing to: origin/{current_branch}")

    # Push with upstream tracking
    code, stdout, stderr = run_command(["git", "push", "-u", "origin", current_branch])

    if code != 0:
        print(f"[FAIL] Failed to push: {stderr}")
        return False

    print("[OK] Push successful")
    print(stdout)

    return True


def verify_sync() -> bool:
    """Verify that sync was successful"""
    print("\n" + "=" * 70)
    print("STEP 4: VERIFYING SYNC")
    print("=" * 70)

    # Get current commit hash
    _, local_hash, _ = run_command(["git", "rev-parse", "HEAD"])
    local_hash = local_hash.strip()
    print(f"Local commit: {local_hash[:8]}")

    # Get remote tracking branch
    _, current_branch, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = current_branch.strip()

    # Fetch to update remote refs
    _, _, _ = run_command(["git", "fetch", "origin"])

    # Get remote commit hash
    code, remote_hash, stderr = run_command(["git", "rev-parse", f"origin/{current_branch}"])

    if code != 0:
        print(f"[WARN] Could not verify remote commit: {stderr}")
        return True  # Don't fail if we can't verify

    remote_hash = remote_hash.strip()
    print(f"Remote commit: {remote_hash[:8]}")

    if local_hash == remote_hash:
        print("[OK] Local and remote are in sync")
        return True
    else:
        print("[FAIL] Local and remote are out of sync")
        return False


def get_git_status() -> dict:
    """Get current Git status summary"""
    status = {}

    # Get current branch
    _, branch, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    status["branch"] = branch.strip()

    # Get remote URL
    _, remote_url, _ = run_command(["git", "config", "--get", "remote.origin.url"])
    status["remote_url"] = remote_url.strip()

    # Get latest commit
    _, commit, _ = run_command(["git", "log", "-1", "--oneline"])
    status["latest_commit"] = commit.strip()

    return status


def main():
    """Main execution"""
    print("\n" + "=" * 70)
    print("GIT SELECTIVE SYNC TO REMOTE (OPTION B)")
    print("=" * 70)

    # Define file patterns to stage (Option B defaults)
    # Can be customized as needed
    files_to_stage = [
        "fix_*.py",
        "sync_*.py",
        "verify_*.py",
    ]

    print(f"\nFiles to stage: {', '.join(files_to_stage)}")
    print("(Edit sync_selective.py to customize file patterns)")

    # Show initial status
    status = get_git_status()
    print(f"\nCurrent branch: {status['branch']}")
    print(f"Remote URL: {status['remote_url']}")
    print(f"Latest commit: {status['latest_commit']}")

    # Execute sync steps
    if not stage_specific_files(files_to_stage):
        print("\n[FAIL] SYNC FAILED: Could not stage files")
        sys.exit(1)

    if not create_commit():
        print("\n[FAIL] SYNC FAILED: Could not create commit")
        sys.exit(1)

    if not push_to_remote():
        print("\n[FAIL] SYNC FAILED: Could not push to remote")
        sys.exit(1)

    if not verify_sync():
        print("\n[FAIL] SYNC FAILED: Verification failed")
        sys.exit(1)

    # Success
    print("\n" + "=" * 70)
    print("[OK] SELECTIVE SYNC COMPLETED SUCCESSFULLY")
    print("=" * 70)

    # Show final status
    final_status = get_git_status()
    print(f"\nBranch: {final_status['branch']}")
    print(f"Remote URL: {final_status['remote_url']}")
    print(f"Latest commit: {final_status['latest_commit']}")
    print("\nYour selected files are now synced to the remote repository!")
    print("=" * 70)

    sys.exit(0)


if __name__ == "__main__":
    main()
