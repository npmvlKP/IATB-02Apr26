#!/usr/bin/env python3
"""
Git State Verification Script
Checks branch status, staged/unstaged changes, and remote sync readiness
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


def check_branch() -> dict:
    """Check current branch and remote tracking"""
    print("=" * 70)
    print("CHECKING BRANCH STATUS")
    print("=" * 70)

    # Get current branch
    _, current_branch, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = current_branch.strip()
    print(f"[OK] Current branch: {current_branch}")

    # Check if remote branch exists
    _, remote_branches, _ = run_command(["git", "branch", "-r"])
    remote_exists = f"origin/{current_branch}" in remote_branches
    print(f"[OK] Remote branch exists: {remote_exists}")

    # Get remote URL
    _, remote_url, _ = run_command(["git", "config", "--get", "remote.origin.url"])
    print(f"[OK] Remote URL: {remote_url.strip()}")

    return {
        "current_branch": current_branch,
        "remote_exists": remote_exists,
        "remote_url": remote_url.strip(),
    }


def check_changes() -> dict:
    """Check staged and unstaged changes"""
    print("\n" + "=" * 70)
    print("CHECKING CHANGES")
    print("=" * 70)

    # Get staged changes
    _, staged_output, _ = run_command(["git", "diff", "--cached", "--name-status"])
    staged_files = [line for line in staged_output.split("\n") if line.strip()]
    print(f"[OK] Staged files: {len(staged_files)}")

    # Get unstaged changes
    _, unstaged_output, _ = run_command(["git", "diff", "--name-status"])
    unstaged_files = [line for line in unstaged_output.split("\n") if line.strip()]
    print(f"[OK] Unstaged modified files: {len(unstaged_files)}")

    # Get untracked files
    _, untracked_output, _ = run_command(["git", "ls-files", "--others", "--exclude-standard"])
    untracked_files = [line for line in untracked_output.split("\n") if line.strip()]
    print(f"[OK] Untracked files: {len(untracked_files)}")

    return {"staged": staged_files, "unstaged": unstaged_files, "untracked": untracked_files}


def verify_push_readiness(branch_info: dict, changes: dict) -> bool:
    """Check if repository is ready for push"""
    print("\n" + "=" * 70)
    print("PUSH READINESS CHECK")
    print("=" * 70)

    issues = []

    # Check for unstaged changes
    if changes["unstaged"]:
        issues.append(f"[FAIL] {len(changes['unstaged'])} unstaged modified files")
    else:
        print("[OK] No unstaged modifications")

    # Check for untracked files
    if changes["untracked"]:
        issues.append(f"[FAIL] {len(changes['untracked'])} untracked files")
    else:
        print("[OK] No untracked files")

    # Check if staged
    if not changes["staged"]:
        issues.append("[FAIL] No staged changes to commit")
    else:
        print(f"[OK] {len(changes['staged'])} files staged for commit")

    # Check if branch exists locally
    if not branch_info["current_branch"]:
        issues.append("[FAIL] Could not determine current branch")
    else:
        print(f"[OK] On branch: {branch_info['current_branch']}")

    if issues:
        print("\n" + "=" * 70)
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
        print("=" * 70)
        return False
    else:
        print("\n" + "=" * 70)
        print("[OK] REPOSITORY IS READY FOR COMMIT AND PUSH")
        print("=" * 70)
        return True


def print_recommendations(branch_info: dict, changes: dict):
    """Print actionable recommendations"""
    print("\n" + "=" * 70)
    print("RECOMMENDED ACTIONS")
    print("=" * 70)

    current_branch = branch_info["current_branch"]

    if changes["unstaged"]:
        print("\n1. Stage unstaged files:")
        print(
            f"   git add {' '.join([f.split()[1] if f.split()[0] != '?' else f for f in changes['unstaged'][:5]])}"
        )
        if len(changes["unstaged"]) > 5:
            print(f"   ... and {len(changes['unstaged']) - 5} more")

    if changes["untracked"]:
        print("\n2. Add untracked files (if needed):")
        print(f"   git add {' '.join(changes['untracked'][:3])}")
        if len(changes["untracked"]) > 3:
            print(f"   ... and {len(changes['untracked']) - 3} more")

    if changes["staged"]:
        print("\n3. Commit staged changes:")
        commit_msg = (
            f"feat({current_branch.replace('optimize/', '')}): quality gate fixes and updates"
        )
        print(f'   git commit -m "{commit_msg}"')

    print("\n4. Push to correct branch:")
    print(f"   git push -u origin {current_branch}")

    print("\n" + "=" * 70)
    print("FULL SEQUENCE:")
    print("=" * 70)
    print("# Step 1: Stage all changes")
    print("git add -A")
    print("\n# Step 2: Commit changes")
    print(
        f"git commit -m \"feat({current_branch.replace('optimize/', '')}): quality gate fixes and updates\""
    )
    print("\n# Step 3: Push to correct remote branch")
    print(f"git push -u origin {current_branch}")
    print("=" * 70)


def main():
    """Main execution"""
    print("\n" + "=" * 70)
    print("GIT STATE VERIFICATION")
    print("=" * 70)

    try:
        branch_info = check_branch()
        changes = check_changes()
        is_ready = verify_push_readiness(branch_info, changes)
        print_recommendations(branch_info, changes)

        print("\n" + "=" * 70)
        if is_ready:
            print("STATUS: READY TO COMMIT AND PUSH")
            sys.exit(0)
        else:
            print("STATUS: ACTION REQUIRED BEFORE PUSH")
            sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
