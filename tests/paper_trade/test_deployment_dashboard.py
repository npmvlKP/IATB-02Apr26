"""
Tests for paper-trade deployment dashboard logic.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError
from iatb.paper_trade import deployment_dashboard as dashboard
from iatb.paper_trade.deployment_dashboard import (
    build_deployment_report,
    check_exchange_instruments,
    evaluate_nse_calendar_status,
    load_zerodha_user_info,
    render_deployment_dashboard,
)


def _full_user_env() -> dict[str, str]:
    return {
        "ZERODHA_USER_NAME": "Test Trader",
        "ZERODHA_EMAIL": "trader@example.com",
        "ZERODHA_USER_ID": "ABCD1234",
        "ZERODHA_AVAILABLE_BALANCE": "250000.50",
    }


def test_load_zerodha_user_info_from_environment() -> None:
    user = load_zerodha_user_info(_full_user_env())
    assert user.full_name == "Test Trader"
    assert user.email == "trader@example.com"
    assert user.user_id == "ABCD1234"
    assert user.available_balance == Decimal("250000.50")
    assert user.is_complete


def test_load_zerodha_user_info_from_profile_file(tmp_path: Path) -> None:
    profile_path = tmp_path / "zerodha_profile.json"
    profile_path.write_text(
        (
            '{"personal_info":"Paper User","mail_id":"paper@example.com",'
            '"uid":"PAPER001","balance":"1000.00"}'
        ),
        encoding="utf-8",
    )
    env = {"ZERODHA_PROFILE_PATH": profile_path.as_posix()}
    report = build_deployment_report(
        datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC), env, tmp_path / "instruments"
    )
    assert report.zerodha_user.full_name == "Paper User"
    assert report.zerodha_user.email == "paper@example.com"
    assert report.zerodha_user.user_id == "PAPER001"
    assert report.zerodha_user.available_balance == Decimal("1000.00")


def test_load_zerodha_user_info_missing_fields_marked() -> None:
    user = load_zerodha_user_info({"ZERODHA_AVAILABLE_BALANCE": "not-a-decimal"})
    assert not user.is_complete
    assert user.missing_fields == ("personal info", "mail id", "uid", "available balance")


def test_evaluate_nse_calendar_status_holiday() -> None:
    holiday_time = datetime(2026, 1, 26, 5, 0, 0, tzinfo=UTC)
    status = evaluate_nse_calendar_status(holiday_time)
    assert status.status == "HOLIDAY"
    assert status.note.startswith("NSE holiday")
    assert status.next_open_utc is not None


def test_check_exchange_instruments_uses_env_count() -> None:
    env = {"IATB_NSE_INSTRUMENT_COUNT": "1420"}
    status = check_exchange_instruments(Exchange.NSE, env, Path("data/instruments"))
    assert status.status == "HEALTHY"
    assert status.instrument_count == 1420


def test_check_exchange_instruments_reads_json_snapshot(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    (instrument_dir / "MCX.json").write_text('[{"symbol":"CRUDEOIL"},{"symbol":"NATURALGAS"}]')
    status = check_exchange_instruments(Exchange.MCX, {}, instrument_dir)
    assert status.status == "HEALTHY"
    assert status.instrument_count == 2


def test_build_deployment_report_flags_missing_exchange_snapshot(tmp_path: Path) -> None:
    report = build_deployment_report(
        datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC), _full_user_env(), tmp_path / "instruments"
    )
    assert report.has_blockers
    assert report.deployment_mode == "CORRECTIVE_ACTION_REQUIRED"
    assert report.corrective_actions


def test_build_deployment_report_live_mode_when_all_checks_pass(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    for exchange in ("NSE", "MCX", "CDS"):
        (instrument_dir / f"{exchange}.json").write_text('[{"symbol":"DUMMY"}]', encoding="utf-8")
    report = build_deployment_report(
        datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC), _full_user_env(), instrument_dir
    )
    assert not report.has_blockers
    assert report.deployment_mode == "LIVE_PAPER_TRADING"


def test_render_deployment_dashboard_contains_expected_sections(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    for exchange in ("NSE", "MCX", "CDS"):
        (instrument_dir / f"{exchange}.json").write_text('[{"symbol":"OK"}]', encoding="utf-8")
    report = build_deployment_report(
        datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC), _full_user_env(), instrument_dir
    )
    rendered = render_deployment_dashboard(report)
    assert "NSE Market Calendar" in rendered
    assert "Zerodha Login User Details" in rendered
    assert "Exchange Instrument Fetch Status" in rendered
    assert "Deployment Mode: LIVE_PAPER_TRADING" in rendered


def test_build_deployment_report_standby_mode_when_market_closed(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    for exchange in ("NSE", "MCX", "CDS"):
        (instrument_dir / f"{exchange}.json").write_text('[{"symbol":"OK"}]', encoding="utf-8")
    report = build_deployment_report(
        datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC), _full_user_env(), instrument_dir
    )
    assert not report.has_blockers
    assert report.deployment_mode == "STANDBY_UNTIL_NSE_OPEN"
    assert "Next Open (UTC):" in render_deployment_dashboard(report)


def test_check_exchange_instruments_with_invalid_env_count() -> None:
    status = check_exchange_instruments(
        Exchange.NSE,
        {"IATB_NSE_INSTRUMENT_COUNT": "bad-value"},
        Path("data/instruments"),
    )
    assert status.status == "MISSING"
    assert status.instrument_count == 0


def test_check_exchange_instruments_with_explicit_env_file_path(tmp_path: Path) -> None:
    snapshot = tmp_path / "nse.csv"
    snapshot.write_text("symbol,token\nINFY,101\nTCS,102\n", encoding="utf-8")
    env = {"IATB_NSE_INSTRUMENT_FILE": snapshot.as_posix()}
    status = check_exchange_instruments(Exchange.NSE, env, tmp_path)
    assert status.status == "HEALTHY"
    assert status.source == snapshot.as_posix()
    assert status.instrument_count == 2


def test_check_exchange_instruments_with_json_data_key(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    (instrument_dir / "CDS.json").write_text('{"data":[{"a":1},{"a":2}]}', encoding="utf-8")
    status = check_exchange_instruments(Exchange.CDS, {}, instrument_dir)
    assert status.status == "HEALTHY"
    assert status.instrument_count == 2


def test_check_exchange_instruments_with_invalid_json_snapshot(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "instruments"
    instrument_dir.mkdir(parents=True, exist_ok=True)
    (instrument_dir / "NSE.json").write_text("{not-valid-json}", encoding="utf-8")
    status = check_exchange_instruments(Exchange.NSE, {}, instrument_dir)
    assert status.status == "MISSING"


def test_count_csv_entries_without_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "raw.csv"
    csv_path.write_text("INFY\nTCS\n", encoding="utf-8")
    assert dashboard._count_csv_entries(csv_path) == 2


def test_count_csv_entries_empty_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")
    assert dashboard._count_csv_entries(csv_path) == 0


def test_count_csv_entries_missing_file_returns_zero(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing.csv"
    assert dashboard._count_csv_entries(csv_path) == 0


def test_count_instruments_unknown_suffix_returns_zero(tmp_path: Path) -> None:
    snapshot = tmp_path / "NSE.txt"
    snapshot.write_text("abc", encoding="utf-8")
    assert dashboard._count_instruments(snapshot) == 0


def test_load_profile_map_handles_non_dict_payload(tmp_path: Path) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text('["a","b"]', encoding="utf-8")
    assert dashboard._load_profile_map(profile) == {}


def test_load_profile_map_handles_invalid_json(tmp_path: Path) -> None:
    profile = tmp_path / "profile_invalid.json"
    profile.write_text("{broken", encoding="utf-8")
    assert dashboard._load_profile_map(profile) == {}


def test_build_report_with_profile_and_env_marks_combined_source(tmp_path: Path) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(
        '{"mail_id":"from-file@example.com","uid":"FILE001","balance":"50.00"}',
        encoding="utf-8",
    )
    env = _full_user_env() | {"ZERODHA_PROFILE_PATH": profile.as_posix()}
    report = build_deployment_report(
        datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC), env, tmp_path / "instruments"
    )
    assert report.zerodha_user.source.startswith("environment + ")


def test_evaluate_nse_calendar_status_closed_without_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoSessionCalendar:
        def session_for(self, exchange: Exchange, trading_date: object) -> None:
            return None

        def is_holiday(self, exchange: Exchange, trading_date: object) -> bool:
            return False

    monkeypatch.setattr(dashboard.TradingSessions, "calendar", NoSessionCalendar())
    status = evaluate_nse_calendar_status(datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC))
    assert status.status == "CLOSED"
    assert status.session_window_ist == "No active session"


def test_collect_operational_notes_when_next_open_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise_clock_error(_: datetime, __: Exchange) -> datetime:
        msg = "no next open"
        raise ClockError(msg)

    monkeypatch.setattr(dashboard.TradingSessions, "next_open_time", _raise_clock_error)
    report = build_deployment_report(
        datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC), _full_user_env(), tmp_path / "instruments"
    )
    expected_note = "Unable to resolve next NSE open time from current calendar."
    assert expected_note in report.operational_notes


def test_require_utc_validation_errors(tmp_path: Path) -> None:
    naive = datetime(2024, 1, 1, 9, 0, 0)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        build_deployment_report(naive, _full_user_env(), tmp_path / "instruments")
    ist = timezone(timedelta(hours=5, minutes=30))
    non_utc = datetime(2024, 1, 1, 9, 0, 0, tzinfo=ist)
    with pytest.raises(ValueError, match="use UTC"):
        build_deployment_report(non_utc, _full_user_env(), tmp_path / "instruments")


def test_render_deployment_dashboard_with_missing_balance_and_no_next_open() -> None:
    status = dashboard.NseCalendarStatus(
        status="CLOSED",
        trading_date=datetime(2024, 1, 1, tzinfo=UTC).date(),
        ist_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        session_window_ist="No active session",
        note="Test",
        next_open_utc=None,
    )
    user = dashboard.ZerodhaUserInfo(
        full_name="",
        email="",
        user_id="",
        available_balance=None,
        missing_fields=("personal info", "mail id", "uid", "available balance"),
        source="environment",
    )
    instrument = dashboard.ExchangeInstrumentStatus(
        exchange=Exchange.NSE,
        status="MISSING",
        instrument_count=0,
        source="missing",
        detail="missing",
        corrective_action="fix",
    )
    report = dashboard.DeploymentReport(
        timestamp_utc=datetime(2024, 1, 1, tzinfo=UTC),
        zerodha_user=user,
        nse_calendar=status,
        instruments=(instrument,),
        corrective_actions=("fix",),
        operational_notes=(),
    )
    rendered = render_deployment_dashboard(report)
    assert "Available Balance: MISSING" in rendered
    assert "Next Open (UTC):" not in rendered
