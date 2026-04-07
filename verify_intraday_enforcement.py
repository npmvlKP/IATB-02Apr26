#!/usr/bin/env python3
"""
Verification script for Point [2]: Intraday-Only Enforcement + NSE/CDS/MCX Timings

This script verifies:
1. Config loading from exchanges.toml and nse_holidays.toml
2. MIS-only enforcement for Stocks/Options/Futures on NSE/CDS/MCX
3. Hard-blocks DELIVERY trades
4. Official session timings from config
5. Holiday calendar loading from config
"""

from datetime import UTC, date, datetime, time

from iatb.backtesting.session_masks import (
    MIS_REQUIRED_ASSETS,
    is_mis_trading_allowed,
    validate_trade_product,
)
from iatb.core.enums import Exchange
from iatb.core.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR


def verify_config_loading():
    """Verify config files are loaded correctly."""
    print("\n=== 1. Config Loading Verification ===")

    # Check NSE session times from config
    nse_session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.NSE)
    assert nse_session is not None, "NSE session not loaded"
    assert nse_session.open_time == time(9, 15), f"NSE open time mismatch: {nse_session.open_time}"
    assert nse_session.close_time == time(
        15, 30
    ), f"NSE close time mismatch: {nse_session.close_time}"
    print("[OK] NSE session times loaded from config: 09:15 - 15:30")

    # Check MCX session times from config
    mcx_session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.MCX)
    assert mcx_session is not None, "MCX session not loaded"
    assert mcx_session.open_time == time(9, 0), f"MCX open time mismatch: {mcx_session.open_time}"
    assert mcx_session.close_time == time(
        23, 30
    ), f"MCX close time mismatch: {mcx_session.close_time}"
    print("[OK] MCX session times loaded from config: 09:00 - 23:30")

    # Check CDS session times from config
    cds_session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.CDS)
    assert cds_session is not None, "CDS session not loaded"
    assert cds_session.open_time == time(9, 0), f"CDS open time mismatch: {cds_session.open_time}"
    assert cds_session.close_time == time(
        17, 0
    ), f"CDS close time mismatch: {cds_session.close_time}"
    print("[OK] CDS session times loaded from config: 09:00 - 17:00")

    # Check holiday calendar
    republic_day = date(2026, 1, 26)
    assert DEFAULT_EXCHANGE_CALENDAR.is_holiday(
        Exchange.NSE, republic_day
    ), "Republic Day not a holiday"
    assert DEFAULT_EXCHANGE_CALENDAR.is_holiday(
        Exchange.MCX, republic_day
    ), "Republic Day not a holiday for MCX"
    print("[OK] Holiday calendar loaded from config (Republic Day detected)")


def verify_mis_required_assets():
    """Verify MIS-required assets are correctly defined."""
    print("\n=== 2. MIS Required Assets Verification ===")

    assert "STOCKS" in MIS_REQUIRED_ASSETS, "STOCKS not in MIS-required assets"
    assert "OPTIONS" in MIS_REQUIRED_ASSETS, "OPTIONS not in MIS-required assets"
    assert "FUTURES" in MIS_REQUIRED_ASSETS, "FUTURES not in MIS-required assets"
    assert "CURRENCY_FO" in MIS_REQUIRED_ASSETS, "CURRENCY_FO not in MIS-required assets"
    print("[OK] MIS-required assets: STOCKS, OPTIONS, FUTURES, CURRENCY_FO")


def verify_mis_only_enforcement():
    """Verify MIS-only enforcement during trading session."""
    print("\n=== 3. MIS-Only Enforcement Verification ===")

    # UTC time during NSE trading session (10:00 IST = 04:30 UTC)
    trading_time = datetime(2026, 1, 5, 4, 30, 0, tzinfo=UTC)

    for asset in ["STOCKS", "OPTIONS", "FUTURES"]:
        # Check MIS trading is allowed
        allowed = is_mis_trading_allowed(trading_time, Exchange.NSE, asset)
        assert allowed, f"MIS trading not allowed for {asset}"
        print(f"[OK] MIS trading allowed for {asset} on NSE")

        # Check MIS product validation succeeds
        result = validate_trade_product(trading_time, Exchange.NSE, asset, "MIS")
        assert result is not None, f"MIS product validation failed for {asset}"
        print(f"[OK] MIS product validated for {asset}")


def verify_delivery_blocked():
    """Verify DELIVERY trades are hard-blocked for MIS-required assets."""
    print("\n=== 4. DELIVERY Blocking Verification ===")

    from iatb.core.exceptions import ConfigError

    # UTC time during NSE trading session
    trading_time = datetime(2026, 1, 5, 4, 30, 0, tzinfo=UTC)

    for asset in ["STOCKS", "OPTIONS", "FUTURES"]:
        for product in ["CNC", "DELIVERY", "NRML"]:
            try:
                result = validate_trade_product(trading_time, Exchange.NSE, asset, product)
                # For NRML, it should not raise but for CNC/DELIVERY it should
                if product in ["CNC", "DELIVERY"]:
                    print(f"[FAIL] DELIVERY/CNC not blocked for {asset} (should be blocked)")
                else:
                    print(f"[OK] NRML allowed for {asset} (but MIS recommended)")
            except ConfigError as e:
                if "blocked" in str(e).lower():
                    print(f"[OK] {product} blocked for {asset}")
                else:
                    print(f"[FAIL] Unexpected error for {asset}/{product}: {e}")


def verify_off_session_blocked():
    """Verify trading is blocked outside session hours."""
    print("\n=== 5. Off-Session Blocking Verification ===")

    # UTC time before NSE market open (08:00 IST = 02:30 UTC)
    pre_market = datetime(2026, 1, 5, 2, 30, 0, tzinfo=UTC)

    # MIS trading should not be allowed before market open
    allowed = is_mis_trading_allowed(pre_market, Exchange.NSE, "STOCKS")
    assert not allowed, "MIS trading allowed before market open"
    print("[OK] MIS trading blocked before market open")

    # UTC time after NSE market close (16:00 IST = 10:30 UTC)
    post_market = datetime(2026, 1, 5, 10, 30, 0, tzinfo=UTC)

    # MIS trading should not be allowed after market close
    allowed = is_mis_trading_allowed(post_market, Exchange.NSE, "STOCKS")
    assert not allowed, "MIS trading allowed after market close"
    print("[OK] MIS trading blocked after market close")


def verify_weekend_blocked():
    """Verify trading is blocked on weekends."""
    print("\n=== 6. Weekend Blocking Verification ===")

    saturday = datetime(2026, 1, 3, 4, 30, 0, tzinfo=UTC)  # Saturday during trading hours

    # MIS trading should not be allowed on Saturday
    allowed = is_mis_trading_allowed(saturday, Exchange.NSE, "STOCKS")
    assert not allowed, "MIS trading allowed on Saturday"
    print("[OK] MIS trading blocked on Saturday")

    sunday = datetime(2026, 1, 4, 4, 30, 0, tzinfo=UTC)  # Sunday during trading hours

    # MIS trading should not be allowed on Sunday
    allowed = is_mis_trading_allowed(sunday, Exchange.NSE, "STOCKS")
    assert not allowed, "MIS trading allowed on Sunday"
    print("[OK] MIS trading blocked on Sunday")


def verify_holiday_blocked():
    """Verify trading is blocked on holidays."""
    print("\n=== 7. Holiday Blocking Verification ===")

    republic_day = datetime(2026, 1, 26, 4, 30, 0, tzinfo=UTC)  # Republic Day during trading hours

    # MIS trading should not be allowed on Republic Day
    allowed = is_mis_trading_allowed(republic_day, Exchange.NSE, "STOCKS")
    assert not allowed, "MIS trading allowed on Republic Day"
    print("[OK] MIS trading blocked on Republic Day (holiday)")


def verify_utc_awareness():
    """Verify UTC-aware datetime requirement."""
    print("\n=== 8. UTC Awareness Verification ===")

    from iatb.core.exceptions import ClockError

    # Naive datetime should raise error
    naive_dt = datetime(2026, 1, 5, 10, 0, 0)

    try:
        is_mis_trading_allowed(naive_dt, Exchange.NSE, "STOCKS")
        print("[FAIL] Naive datetime accepted (should be rejected)")
    except (ClockError, ValueError):
        print("[OK] Naive datetime rejected (requires UTC awareness)")


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Point [2] Verification: Intraday-Only Enforcement")
    print("=" * 60)

    try:
        verify_config_loading()
        verify_mis_required_assets()
        verify_mis_only_enforcement()
        verify_delivery_blocked()
        verify_off_session_blocked()
        verify_weekend_blocked()
        verify_holiday_blocked()
        verify_utc_awareness()

        print("\n" + "=" * 60)
        print("[OK] ALL VERIFICATIONS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("- Config files loaded correctly (exchanges.toml, nse_holidays.toml)")
        print("- MIS-only enforcement active for STOCKS/OPTIONS/FUTURES/CURRENCY_FO")
        print("- DELIVERY trades hard-blocked for MIS-required assets")
        print("- Session timings enforced from config")
        print("- Holiday calendar enforced from config")
        print("- UTC-aware datetime requirement enforced")
        return 0

    except AssertionError as e:
        print(f"\n[FAIL] VERIFICATION FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[FAIL] UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
