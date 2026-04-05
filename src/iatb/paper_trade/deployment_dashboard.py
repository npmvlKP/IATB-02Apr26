"""
Paper trading deployment dashboard domain logic.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from iatb.core.clock import Clock, TradingSessions
from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError

InstrumentHealth = Literal["HEALTHY", "MISSING"]
CalendarHealth = Literal["OPEN", "CLOSED", "HOLIDAY", "WEEKEND"]
INSTRUMENT_EXCHANGES: tuple[Exchange, ...] = (Exchange.NSE, Exchange.MCX, Exchange.CDS)


@dataclass(frozen=True)
class ZerodhaUserInfo:
    """Normalized Zerodha user details for dashboard rendering."""

    full_name: str
    email: str
    user_id: str
    available_balance: Decimal | None
    missing_fields: tuple[str, ...]
    source: str

    @property
    def is_complete(self) -> bool:
        """Return True when all mandatory user fields are available."""
        return len(self.missing_fields) == 0


@dataclass(frozen=True)
class NseCalendarStatus:
    """NSE market calendar snapshot for the current timestamp."""

    status: CalendarHealth
    trading_date: date
    ist_timestamp: datetime
    session_window_ist: str
    note: str
    next_open_utc: datetime | None

    @property
    def can_trade_now(self) -> bool:
        """Return True when the NSE session is currently active."""
        return self.status == "OPEN"


@dataclass(frozen=True)
class ExchangeInstrumentStatus:
    """Instrument fetch-health status for an exchange."""

    exchange: Exchange
    status: InstrumentHealth
    instrument_count: int
    source: str
    detail: str
    corrective_action: str

    @property
    def is_healthy(self) -> bool:
        """Return True if instrument fetch state is healthy."""
        return self.status == "HEALTHY"


@dataclass(frozen=True)
class DeploymentReport:
    """Comprehensive paper-trade deployment status report."""

    timestamp_utc: datetime
    zerodha_user: ZerodhaUserInfo
    nse_calendar: NseCalendarStatus
    instruments: tuple[ExchangeInstrumentStatus, ...]
    corrective_actions: tuple[str, ...]
    operational_notes: tuple[str, ...]

    @property
    def has_blockers(self) -> bool:
        """Return True if readiness blockers are present."""
        if not self.zerodha_user.is_complete:
            return True
        return any(not item.is_healthy for item in self.instruments)

    @property
    def deployment_mode(self) -> str:
        """Human-friendly deployment mode string."""
        if self.has_blockers:
            return "CORRECTIVE_ACTION_REQUIRED"
        if self.nse_calendar.can_trade_now:
            return "LIVE_PAPER_TRADING"
        return "STANDBY_UNTIL_NSE_OPEN"


def build_deployment_report(
    now_utc: datetime,
    env: Mapping[str, str],
    instrument_dir: Path = Path("data/instruments"),
) -> DeploymentReport:
    """Build a full dashboard report for paper-trade deployment."""
    _require_utc(now_utc)
    profile_path = _profile_path_from_env(env)
    user_info = load_zerodha_user_info(env, profile_path)
    calendar_status = evaluate_nse_calendar_status(now_utc)
    instruments = tuple(
        check_exchange_instruments(exchange, env, instrument_dir)
        for exchange in INSTRUMENT_EXCHANGES
    )
    corrective_actions = _collect_corrective_actions(user_info, instruments)
    operational_notes = _collect_operational_notes(calendar_status)
    return DeploymentReport(
        timestamp_utc=now_utc,
        zerodha_user=user_info,
        nse_calendar=calendar_status,
        instruments=instruments,
        corrective_actions=corrective_actions,
        operational_notes=operational_notes,
    )


def load_zerodha_user_info(
    env: Mapping[str, str], profile_path: Path | None = None
) -> ZerodhaUserInfo:
    """Load Zerodha user details from env and optional JSON profile."""
    profile = _load_profile_map(profile_path)
    full_name = _pick_value(
        env, profile, "ZERODHA_USER_NAME", ("name", "full_name", "user_name", "personal_info")
    )
    email = _pick_value(env, profile, "ZERODHA_EMAIL", ("email", "mail_id", "mail"))
    user_id = _pick_value(env, profile, "ZERODHA_USER_ID", ("user_id", "uid", "kite_user_id"))
    balance_raw = _pick_value(
        env,
        profile,
        "ZERODHA_AVAILABLE_BALANCE",
        ("available_balance", "balance", "cash_available"),
    )
    available_balance = _parse_decimal(balance_raw)
    missing_fields = _missing_user_fields(full_name, email, user_id, available_balance)
    source = _resolve_user_source(env, profile, profile_path)
    return ZerodhaUserInfo(
        full_name=full_name,
        email=email,
        user_id=user_id,
        available_balance=available_balance,
        missing_fields=missing_fields,
        source=source,
    )


def evaluate_nse_calendar_status(now_utc: datetime) -> NseCalendarStatus:
    """Evaluate NSE status using the configured exchange calendar."""
    _require_utc(now_utc)
    ist_now = Clock.to_ist(now_utc)
    trading_date = ist_now.date()
    session = TradingSessions.calendar.session_for(Exchange.NSE, trading_date)
    if session is None:
        return _closed_nse_status(now_utc, ist_now, trading_date)

    open_label = _session_window_label(session.open_time.hour, session.open_time.minute)
    close_label = _session_window_label(session.close_time.hour, session.close_time.minute)
    session_window = f"{open_label} - {close_label} IST"
    if TradingSessions.is_market_open(now_utc, Exchange.NSE):
        note = "NSE market is currently open."
        return NseCalendarStatus("OPEN", trading_date, ist_now, session_window, note, None)

    next_open = _safe_next_open(now_utc)
    note = "NSE trading day is active, but the current clock is outside session hours."
    return NseCalendarStatus("CLOSED", trading_date, ist_now, session_window, note, next_open)


def check_exchange_instruments(
    exchange: Exchange, env: Mapping[str, str], instrument_dir: Path
) -> ExchangeInstrumentStatus:
    """Resolve instrument-fetch health for an exchange."""
    env_count = _read_exchange_count_from_env(exchange, env)
    if env_count is not None:
        source = f"env:IATB_{exchange.value}_INSTRUMENT_COUNT"
        return _status_from_count(exchange, env_count, source)

    instrument_path = _resolve_instrument_file(exchange, env, instrument_dir)
    if instrument_path is None:
        return _missing_instrument_status(exchange, "No instrument snapshot file found.")

    instrument_count = _count_instruments(instrument_path)
    source = instrument_path.as_posix()
    return _status_from_count(exchange, instrument_count, source)


def render_deployment_dashboard(report: DeploymentReport) -> str:
    """Render report as a user-friendly plain-text dashboard."""
    lines = [
        "=" * 78,
        "IATB PAPER TRADING DEPLOYMENT DASHBOARD",
        "=" * 78,
        f"Timestamp (UTC): {report.timestamp_utc.isoformat()}",
        "",
        "NSE Market Calendar",
        f"  Status: {report.nse_calendar.status}",
        f"  Trading Date (IST): {report.nse_calendar.trading_date.isoformat()}",
        f"  Session Window (IST): {report.nse_calendar.session_window_ist}",
        f"  Note: {report.nse_calendar.note}",
    ]
    next_open_line = _format_next_open_line(report.nse_calendar.next_open_utc)
    if next_open_line:
        lines.append(next_open_line)

    lines.extend(
        [
            "",
            "Zerodha Login User Details",
            f"  Personal Info: {_display_value(report.zerodha_user.full_name)}",
            f"  Mail ID: {_display_value(report.zerodha_user.email)}",
            f"  UID: {_display_value(report.zerodha_user.user_id)}",
            f"  Available Balance: {_format_balance(report.zerodha_user.available_balance)}",
            f"  Source: {report.zerodha_user.source}",
            "",
            "Exchange Instrument Fetch Status",
        ]
    )
    lines.extend(_render_instrument_lines(report.instruments))
    lines.append("")
    lines.append(f"Deployment Mode: {report.deployment_mode}")
    lines.extend(_render_action_lines("Corrective Actions", report.corrective_actions))
    lines.extend(_render_action_lines("Operational Notes", report.operational_notes))
    return "\n".join(lines)


def _collect_corrective_actions(
    user_info: ZerodhaUserInfo, instruments: tuple[ExchangeInstrumentStatus, ...]
) -> tuple[str, ...]:
    actions: list[str] = []
    if user_info.missing_fields:
        missing = ", ".join(user_info.missing_fields)
        actions.append(
            "Provide Zerodha fields "
            f"({missing}) via environment variables or a JSON profile file."
        )
    for status in instruments:
        if not status.is_healthy:
            actions.append(status.corrective_action)
    return _unique_tuple(actions)


def _collect_operational_notes(status: NseCalendarStatus) -> tuple[str, ...]:
    if status.can_trade_now:
        return ("NSE session is open; paper trading can run in active mode.",)
    if status.next_open_utc is None:
        return ("Unable to resolve next NSE open time from current calendar.",)
    return (
        "Paper trading stays in standby until NSE reopens.",
        f"Next NSE open (UTC): {status.next_open_utc.isoformat()}",
    )


def _read_exchange_count_from_env(exchange: Exchange, env: Mapping[str, str]) -> int | None:
    raw_count = _safe_text(env.get(f"IATB_{exchange.value}_INSTRUMENT_COUNT"))
    if raw_count == "":
        return None
    try:
        return max(int(raw_count), 0)
    except ValueError:
        return 0


def _resolve_instrument_file(
    exchange: Exchange, env: Mapping[str, str], instrument_dir: Path
) -> Path | None:
    env_path = _safe_text(env.get(f"IATB_{exchange.value}_INSTRUMENT_FILE"))
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate

    for candidate in _instrument_candidates(exchange, instrument_dir):
        if candidate.is_file():
            return candidate
    return None


def _instrument_candidates(exchange: Exchange, instrument_dir: Path) -> tuple[Path, ...]:
    exchange_name = exchange.value
    lower_name = exchange_name.lower()
    return (
        instrument_dir / f"{exchange_name}.json",
        instrument_dir / f"{exchange_name}.csv",
        instrument_dir / f"{lower_name}.json",
        instrument_dir / f"{lower_name}.csv",
    )


def _count_instruments(instrument_path: Path) -> int:
    suffix = instrument_path.suffix.lower()
    if suffix == ".json":
        return _count_json_entries(instrument_path)
    if suffix == ".csv":
        return _count_csv_entries(instrument_path)
    return 0


def _count_json_entries(instrument_path: Path) -> int:
    try:
        payload = json.loads(instrument_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        nested = payload.get("data")
        if isinstance(nested, list):
            return len(nested)
        return len(payload)
    return 0


def _count_csv_entries(instrument_path: Path) -> int:
    try:
        lines = instrument_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    if not lines:
        return 0
    header_offset = 1 if "," in lines[0] else 0
    return max(len(lines) - header_offset, 0)


def _status_from_count(exchange: Exchange, count: int, source: str) -> ExchangeInstrumentStatus:
    if count > 0:
        detail = f"{count} instruments loaded."
        action = "No corrective action required."
        return ExchangeInstrumentStatus(exchange, "HEALTHY", count, source, detail, action)
    detail = "Instrument details are missing or unreadable."
    return _missing_instrument_status(exchange, detail, source, count)


def _missing_instrument_status(
    exchange: Exchange, detail: str, source: str = "unavailable", count: int = 0
) -> ExchangeInstrumentStatus:
    action = (
        f"Fetch {exchange.value} instruments and place snapshot at "
        f"data/instruments/{exchange.value}.json "
        f"or set IATB_{exchange.value}_INSTRUMENT_COUNT."
    )
    return ExchangeInstrumentStatus(exchange, "MISSING", count, source, detail, action)


def _closed_nse_status(
    now_utc: datetime, ist_now: datetime, trading_date: date
) -> NseCalendarStatus:
    is_holiday = TradingSessions.calendar.is_holiday(Exchange.NSE, trading_date)
    status: CalendarHealth
    if is_holiday:
        status = "HOLIDAY"
        note = "NSE holiday as per configured exchange calendar."
    elif trading_date.weekday() >= 5:
        status = "WEEKEND"
        note = "NSE weekend closure (Saturday/Sunday)."
    else:
        status = "CLOSED"
        note = "NSE has no active session configured for this date."
    next_open = _safe_next_open(now_utc)
    return NseCalendarStatus(status, trading_date, ist_now, "No active session", note, next_open)


def _safe_next_open(now_utc: datetime) -> datetime | None:
    try:
        return TradingSessions.next_open_time(now_utc, Exchange.NSE)
    except ClockError:
        return None


def _profile_path_from_env(env: Mapping[str, str]) -> Path | None:
    raw_path = _safe_text(env.get("ZERODHA_PROFILE_PATH"))
    if raw_path == "":
        return None
    return Path(raw_path)


def _load_profile_map(profile_path: Path | None) -> dict[str, str]:
    if profile_path is None or not profile_path.is_file():
        return {}
    try:
        raw_payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_payload, dict):
        return {}
    return {str(key): _safe_text(value) for key, value in raw_payload.items()}


def _pick_value(
    env: Mapping[str, str], profile: Mapping[str, str], env_key: str, profile_keys: tuple[str, ...]
) -> str:
    env_value = _safe_text(env.get(env_key))
    if env_value:
        return env_value
    for key in profile_keys:
        profile_value = _safe_text(profile.get(key))
        if profile_value:
            return profile_value
    return ""


def _missing_user_fields(
    full_name: str, email: str, user_id: str, available_balance: Decimal | None
) -> tuple[str, ...]:
    missing: list[str] = []
    if full_name == "":
        missing.append("personal info")
    if email == "":
        missing.append("mail id")
    if user_id == "":
        missing.append("uid")
    if available_balance is None:
        missing.append("available balance")
    return tuple(missing)


def _resolve_user_source(
    env: Mapping[str, str], profile: Mapping[str, str], profile_path: Path | None
) -> str:
    has_env_data = any(
        _safe_text(env.get(key))
        for key in (
            "ZERODHA_USER_NAME",
            "ZERODHA_EMAIL",
            "ZERODHA_USER_ID",
            "ZERODHA_AVAILABLE_BALANCE",
        )
    )
    if profile and profile_path is not None and has_env_data:
        return f"environment + {profile_path.as_posix()}"
    if profile and profile_path is not None:
        return profile_path.as_posix()
    return "environment"


def _parse_decimal(raw_value: str) -> Decimal | None:
    if raw_value == "":
        return None
    try:
        return Decimal(raw_value)
    except InvalidOperation:
        return None


def _session_window_label(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _require_utc(now_utc: datetime) -> None:
    if now_utc.tzinfo is None:
        msg = "Timestamp must be timezone-aware in UTC."
        raise ValueError(msg)
    if now_utc.tzinfo != UTC:
        msg = "Timestamp must use UTC timezone."
        raise ValueError(msg)


def _safe_text(raw_value: object) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _format_next_open_line(next_open_utc: datetime | None) -> str:
    if next_open_utc is None:
        return ""
    return f"  Next Open (UTC): {next_open_utc.isoformat()}"


def _render_instrument_lines(instruments: tuple[ExchangeInstrumentStatus, ...]) -> list[str]:
    lines: list[str] = []
    for instrument in instruments:
        lines.extend(
            [
                f"  {instrument.exchange.value}: {instrument.status}",
                f"    Count: {instrument.instrument_count}",
                f"    Source: {instrument.source}",
                f"    Detail: {instrument.detail}",
            ]
        )
    return lines


def _render_action_lines(title: str, actions: tuple[str, ...]) -> list[str]:
    lines = ["", title]
    if not actions:
        lines.append("  None")
        return lines
    for index, action in enumerate(actions, start=1):
        lines.append(f"  {index}. {action}")
    return lines


def _display_value(raw_value: str) -> str:
    return raw_value if raw_value else "MISSING"


def _format_balance(balance: Decimal | None) -> str:
    if balance is None:
        return "MISSING"
    return f"₹{balance}"


def _unique_tuple(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
