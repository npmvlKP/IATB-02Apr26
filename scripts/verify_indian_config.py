#!/usr/bin/env python3
"""
Indian Market Configuration Verification Script
Verifies Zerodha settings, NSE/CDS/MCX configuration, and holiday calendar
"""

import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Use tomllib (Python 3.11+) or toml/tomli as fallback
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        import toml as tomllib


def load_toml_file(file_path: Path) -> dict[str, Any]:
    """Load and parse a TOML file."""
    try:
        with open(file_path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        print(f"X ERROR: File not found: {file_path}")
        return {}
    except Exception as e:
        print(f"X ERROR parsing {file_path}: {e}")
        return {}


def verify_settings_toml() -> bool:
    """Verify config/settings.toml has required Indian market settings."""
    print("\n" + "=" * 70)
    print("VERIFYING: config/settings.toml")
    print("=" * 70)

    settings_path = Path("config/settings.toml")
    settings = load_toml_file(settings_path)

    if not settings:
        return False

    all_checks_passed = True

    # Check required sections
    required_sections = ["broker", "network", "algorithm", "engine"]
    for section in required_sections:
        if section not in settings:
            print(f"X FAIL: Missing section [{section}]")
            all_checks_passed = False
        else:
            print(f"+ Section [{section}] exists")

    # Check broker settings
    if "broker" in settings:
        broker = settings["broker"]

        if broker.get("name") == "zerodha":
            print(f"+ Broker name: {broker.get('name')}")
        else:
            print(f"X FAIL: Broker name is '{broker.get('name')}', expected 'zerodha'")
            all_checks_passed = False

        if "live_trading_enabled" in broker:
            print(f"+ Live trading enabled: {broker.get('live_trading_enabled')}")
        else:
            print("X FAIL: Missing 'live_trading_enabled' in [broker]")
            all_checks_passed = False

    # Check network settings
    if "network" in settings:
        network = settings["network"]

        if "static_ip" in network:
            print(f"+ Static IP configured: {network.get('static_ip')}")
            if network.get("static_ip") == "your.static.ip.address":
                print("  ! WARNING: Static IP is placeholder, needs real value")
        else:
            print("X FAIL: Missing 'static_ip' in [network]")
            all_checks_passed = False

    # Check algorithm settings
    if "algorithm" in settings:
        algo = settings["algorithm"]

        if "algo_id" in algo:
            print(f"+ Algorithm ID: {algo.get('algo_id')}")
        else:
            print("X FAIL: Missing 'algo_id' in [algorithm]")
            all_checks_passed = False

    # Check engine settings
    if "engine" in settings:
        engine = settings["engine"]
        required_engine_keys = ["event_bus_max_queue_size", "event_bus_batch_size", "max_tasks"]
        for key in required_engine_keys:
            if key in engine:
                print(f"+ Engine setting: {key} = {engine[key]}")
            else:
                print(f"X FAIL: Missing engine setting: {key}")
                all_checks_passed = False

    # Check top-level settings
    top_level_checks = {
        "mode": "paper",
        "default_exchange": "NSE",
        "default_market_type": "SPOT",
        "timezone": "UTC",
        "paper_trade_enforced": True,
    }

    for key, expected_value in top_level_checks.items():
        if key in settings:
            actual_value = settings[key]
            if actual_value == expected_value:
                print(f"+ {key} = {actual_value}")
            else:
                print(f"! {key} = {actual_value} (expected: {expected_value})")
        else:
            print(f"X FAIL: Missing top-level setting: {key}")
            all_checks_passed = False

    return all_checks_passed


def verify_holidays_toml() -> bool:
    """Verify config/nse_holidays.toml exists and has valid structure."""
    print("\n" + "=" * 70)
    print("VERIFYING: config/nse_holidays.toml")
    print("=" * 70)

    holidays_path = Path("config/nse_holidays.toml")
    holidays = load_toml_file(holidays_path)

    if not holidays:
        return False

    all_checks_passed = True

    # Check for 2026 and 2027 sections
    required_years = ["2026", "2027"]
    for year in required_years:
        if year in holidays:
            print(f"+ Holiday data exists for year {year}")

            # Check for NSE/CDS holidays
            if f"{year}_nse_cds" in holidays[year]:
                nse_cds_count = len(holidays[year][f"{year}_nse_cds"])
                print(f"  + NSE/CDS holidays: {nse_cds_count} entries")
            else:
                print(f"  ! WARNING: No NSE/CDS holidays found for {year}")

            # Check for MCX holidays
            if f"{year}_mcx" in holidays[year]:
                mcx_count = len(holidays[year][f"{year}_mcx"])
                print(f"  + MCX holidays: {mcx_count} entries")
            else:
                print(f"  ! WARNING: No MCX holidays found for {year}")
        else:
            print(f"X FAIL: No holiday data for year {year}")
            all_checks_passed = False

    # Validate holiday structure
    total_holidays = 0
    for year in required_years:
        if year in holidays:
            for holiday_type in [f"{year}_nse_cds", f"{year}_mcx"]:
                if holiday_type in holidays[year]:
                    for holiday in holidays[year][holiday_type]:
                        total_holidays += 1
                        # Check required fields
                        required_fields = ["date", "name", "exchanges", "segments"]
                        for field in required_fields:
                            if field not in holiday:
                                print(
                                    f"X FAIL: Holiday missing field '{field}': {holiday.get('name', 'Unknown')}"
                                )
                                all_checks_passed = False

    print(f"+ Total holidays defined: {total_holidays}")

    return all_checks_passed


def verify_readme_content() -> bool:
    """Verify README.md contains Indian market specific content."""
    print("\n" + "=" * 70)
    print("VERIFYING: README.md (Indian Market Content)")
    print("=" * 70)

    readme_path = Path("README.md")

    if not readme_path.exists():
        print("X FAIL: README.md not found")
        return False

    with open(readme_path, encoding="utf-8") as f:
        content = f.read()

    all_checks_passed = True

    # Check for Indian market keywords
    indian_keywords = [
        "Zerodha",
        "NSE",
        "CDS",
        "MCX",
        "SEBI",
        "MIS",
        "Intraday",
        "Indian",
        "Kite Connect",
    ]

    missing_keywords = []
    for keyword in indian_keywords:
        if keyword in content:
            print(f"+ Found keyword: {keyword}")
        else:
            print(f"X FAIL: Missing keyword: {keyword}")
            missing_keywords.append(keyword)
            all_checks_passed = False

    # Check for specific sections
    required_sections = [
        "## Indian Market Configuration",
        "### Supported Exchanges",
        "## SEBI Compliance",
        "## Trading Hours & Holidays",
    ]

    for section in required_sections:
        if section in content:
            print(f"+ Found section: {section}")
        else:
            print(f"X FAIL: Missing section: {section}")
            all_checks_passed = False

    return all_checks_passed


def verify_config_directory() -> bool:
    """Verify config directory structure."""
    print("\n" + "=" * 70)
    print("VERIFYING: config/ Directory Structure")
    print("=" * 70)

    config_path = Path("config")

    if not config_path.exists():
        print("X FAIL: config/ directory not found")
        return False

    required_files = [
        "settings.toml",
        "nse_holidays.toml",
        "exchanges.toml",
        "logging.toml",
        "strategies.toml",
    ]

    all_checks_passed = True
    for file_name in required_files:
        file_path = config_path / file_name
        if file_path.exists():
            print(f"+ {file_name} exists")
        else:
            print(f"X FAIL: {file_name} not found")
            all_checks_passed = False

    return all_checks_passed


def print_summary(results: dict[str, bool]):
    """Print verification summary."""
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "+ PASS" if passed else "X FAIL"
        print(f"{status}: {test_name}")

    total_tests = len(results)
    passed_tests = sum(results.values())

    print("\n" + "-" * 70)
    print(f"Total: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n[SUCCESS] ALL VERIFICATIONS PASSED!")
        print("\nYour Indian market configuration is ready.")
        print("\nNext steps:")
        print("1. Update STATIC_IP in config/settings.toml with your actual IP")
        print("2. Update ALGO_ID in config/settings.toml with your unique identifier")
        print("3. Configure Zerodha API credentials in .env file")
        print("4. Run quality gates: .\\scripts\\quality_gate.ps1")
        return True
    else:
        print("\n[WARNING] SOME VERIFICATIONS FAILED")
        print("\nPlease fix the issues above before proceeding.")
        return False


def main():
    """Main verification entry point."""
    print("\n" + "=" * 70)
    print("IATB INDIAN MARKET CONFIGURATION VERIFICATION")
    print("=" * 70)
    print(f"Timestamp (UTC): {datetime.utcnow().isoformat()}")
    print(f"Timestamp (IST): {(datetime.utcnow()).replace(hour=(datetime.utcnow().hour + 5) % 24)}")

    results = {}

    # Run all verifications
    results["Config Directory Structure"] = verify_config_directory()
    results["settings.toml"] = verify_settings_toml()
    results["nse_holidays.toml"] = verify_holidays_toml()
    results["README.md Content"] = verify_readme_content()

    # Print summary and exit
    success = print_summary(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
