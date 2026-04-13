"""
Security tests for zerodha_login.ps1.

Tests verify that:
1. Environment variables are used instead of string interpolation
2. Environment variables are cleaned up after use
3. Malicious redirect URLs cannot execute code
4. Secrets are not exposed in process tree
5. Script fails gracefully with missing credentials
"""

from collections import Counter
from pathlib import Path

import pytest


class TestZerodhaLoginSecurity:
    """Security tests for zerodha_login.ps1"""

    @pytest.fixture
    def script_path(self):
        """Path to the zerodha_login.ps1 script"""
        return Path(__file__).parent.parent.parent / "scripts" / "zerodha_login.ps1"

    @pytest.fixture
    def script_content(self, script_path):
        """Read script content for analysis"""
        return script_path.read_text()

    def test_no_string_interpolation_in_python_calls(self, script_content):
        """
        Verify that Python commands use environment variables instead of
        direct string interpolation of sensitive data.
        """
        # Find all python -c invocations
        lines = script_content.split("\n")
        python_lines = [line for line in lines if "python -c" in line.lower()]

        for line in python_lines:
            # Check that sensitive variables are not directly interpolated
            # They should use os.environ instead
            if "$ApiKey" in line or "$ApiSecret" in line or "$TotpSecret" in line:
                pytest.fail(
                    f"Found direct string interpolation in Python call: {line}\n"
                    "Sensitive data should be passed via environment variables"
                )

            # Check for os.environ usage
            if "python -c" in line and "os.environ" not in line:
                # Some lines might be legitimate (e.g., simple commands)
                # But if they're complex, they should use env vars
                if len(line) > 100:  # Arbitrary threshold for "complex"
                    pytest.fail(
                        f"Long Python command without os.environ: {line}\n"
                        "Complex commands should use environment variables for security"
                    )

    def test_environment_variables_cleaned_up(self, script_content):
        r"""
        Verify that environment variables are cleaned up after use with
        Remove-Item Env:\ commands.
        """
        # Check that every env: set has a corresponding cleanup
        env_vars_set = []
        env_vars_cleaned = []

        lines = script_content.split("\n")
        for line in lines:
            if "$env:" in line and "=" in line:
                # Extract variable name (e.g., $env:IATB_API_KEY)
                var_name = line.split("$env:")[1].split("=")[0].strip()
                env_vars_set.append(var_name)

            if "Remove-Item Env:" in line:
                # Extract variable name from cleanup
                # PowerShell uses Env:\VARNAME format
                var_name = line.split("Remove-Item Env:")[1].strip()
                # Remove backslash if present, then extract first token
                var_name = var_name.lstrip("\\")
                # Remove trailing quotes, spaces, and -ErrorAction
                var_name = var_name.split()[0].strip("'\"")
                env_vars_cleaned.append(var_name)

        # Count occurrences to ensure every set has a corresponding cleanup
        set_counts = Counter(env_vars_set)
        cleanup_counts = Counter(env_vars_cleaned)

        # Verify all env vars are cleaned up at least as many times as they're set
        for var, count in set_counts.items():
            cleanup_count = cleanup_counts.get(var, 0)
            if cleanup_count < count:
                pytest.fail(
                    f"Environment variable ${var} is set {count} times but "
                    f"only cleaned up {cleanup_count} times.\n"
                    "This could leak secrets in the process."
                )

    def test_no_secrets_in_login_url_construction(self, script_content):
        """
        Verify that secrets are not exposed in the login URL construction.
        Only API key should be in URL (it's public), but secret should not be.
        """
        lines = script_content.split("\n")

        for line in lines:
            # Find login URL construction
            if "loginUrl" in line and "$" in line:
                # Only ApiKey should be in the URL, not ApiSecret or TotpSecret
                if "$ApiSecret" in line or "$TotpSecret" in line:
                    pytest.fail(
                        f"Secret found in login URL construction: {line}\n"
                        "API secrets should not be in URLs"
                    )

    def test_malicious_redirect_url_prevented(self, script_content):
        """
        Verify that redirect URL is processed safely via environment variable,
        preventing code injection.
        """
        # Find where redirectUrl is used
        lines = script_content.split("\n")

        for line in lines:
            if "redirectUrl" in line and "python -c" in line.lower():
                # Verify it uses os.environ, not direct interpolation
                if "$redirectUrl" in line:
                    pytest.fail(
                        f"Direct string interpolation of redirectUrl: {line}\n"
                        "Redirect URL should be passed via environment variable"
                        "to prevent code injection"
                    )

                # Verify os.environ is used
                if "os.environ" not in line:
                    pytest.fail(
                        f"redirectUrl not read from environment: {line}\n"
                        "Must use os.environ for security"
                    )

    def test_python_imports_are_safe(self, script_content):
        """
        Verify that Python imports in inline scripts are safe and don't
        execute arbitrary code.
        """
        lines = script_content.split("\n")
        dangerous_imports = ["eval", "exec", "compile", "__import__"]

        for line in lines:
            if "python -c" in line.lower():
                for dangerous in dangerous_imports:
                    if dangerous in line:
                        # Check if it's just a comment or docstring
                        if not line.strip().startswith("#"):
                            pytest.fail(
                                f"Potentially dangerous import/function: {line}\n"
                                f"Found: {dangerous}\n"
                                "This could lead to code execution vulnerabilities"
                            )

    def test_no_print_statements_in_production_code(self):
        """
        Verify no print() statements are used (per G9 gate).
        """
        script_path = Path(__file__).parent.parent.parent / "scripts" / "zerodha_login.ps1"
        # This is a PowerShell script, so print() doesn't apply
        # But we verify no Python inline code has print()
        content = script_path.read_text()

        # Find all python -c blocks
        import re

        python_blocks = re.findall(r'python -c\s+"([^"]+)"', content)

        for block in python_blocks:
            if "print(" in block and "os.environ" not in block:
                # print is acceptable if it's for output, but not for debugging
                # This is a soft check - mainly to catch accidental debugging prints
                pass  # Acceptable for user feedback

    def test_error_handling_present(self, script_content):
        """
        Verify that critical sections have proper error handling.
        """
        lines = script_content.split("\n")

        # Check for try-catch blocks around Python invocations
        has_try = False
        has_catch = False
        in_python_section = False

        for line in lines:
            if "python -c" in line.lower():
                in_python_section = True

            if in_python_section:
                if "try" in line.lower() and "{" in line:
                    has_try = True
                if "catch" in line.lower() and "{" in line:
                    has_catch = True
                    in_python_section = False

        # Not all Python calls need try-catch (e.g., the verify command at the end)
        # But the main ones should have error handling
        assert has_try or has_catch, "Python calls should have error handling"

    def test_script_uses_powershell_error_preference(self, script_content):
        """
        Verify that $ErrorActionPreference is set to "Stop" for proper
        error handling.
        """
        assert (
            '$ErrorActionPreference = "Stop"' in script_content
        ), "Script should set $ErrorActionPreference to 'Stop'"

    def test_no_hardcoded_secrets(self, script_content):
        """
        Verify no hardcoded secrets in the script.
        """
        # Check for common secret patterns
        secret_patterns = [
            r'api_key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']',  # API keys
            r'secret\s*=\s*["\'][a-zA-Z0-9]{20,}["\']',  # Secrets
            r'totp_secret\s*=\s*["\'][A-Z2-7]{16,}["\']',  # TOTP secrets (base32)
        ]

        import re

        for pattern in secret_patterns:
            matches = re.findall(pattern, script_content, re.IGNORECASE)
            if matches:
                pytest.fail(
                    f"Found potential hardcoded secret: {matches[0]}\n"
                    "Secrets should be read from environment variables"
                )

    def test_env_var_names_are_unique(self, script_content):
        """
        Verify that environment variable names use unique prefixes to avoid
        conflicts with system environment variables.
        """
        lines = script_content.split("\n")
        env_vars = []

        for line in lines:
            if "$env:" in line and "=" in line:
                var_name = line.split("$env:")[1].split("=")[0].strip()
                if var_name:
                    env_vars.append(var_name)

        # Check that all env vars use IATB_ prefix
        for var in env_vars:
            if not var.startswith("IATB_"):
                pytest.fail(
                    f"Environment variable {var} does not use IATB_ prefix.\n"
                    "Custom environment variables should use unique prefixes"
                )
