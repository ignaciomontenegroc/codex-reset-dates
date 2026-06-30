#!/usr/bin/env python3
"""Show available Codex reset-credit expiration dates.

The script reads the local Codex Desktop auth file and calls a ChatGPT
first-party endpoint. It prints only sanitized reset-credit fields.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment]


API_URL = "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits"
EXPECTED_SCHEME = "https"
EXPECTED_HOST = "chatgpt.com"
DEFAULT_AUTH_PATH = "~/.codex/auth.json"


@dataclass(frozen=True)
class Credit:
    number: int
    title: str
    status: str
    reset_type: str
    granted_at: Optional[datetime]
    expires_at: Optional[datetime]
    redeem_started_at: Optional[datetime]
    redeemed_at: Optional[datetime]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show available Codex rate-limit reset credits and expiry dates."
    )
    parser.add_argument(
        "--auth",
        default=DEFAULT_AUTH_PATH,
        help=f"Path to Codex auth.json. Default: {DEFAULT_AUTH_PATH}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print sanitized JSON instead of a human-readable table.",
    )
    parser.add_argument(
        "--include-unavailable",
        action="store_true",
        help="Include redeemed or unavailable credits.",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help=(
            "IANA timezone for local dates, for example America/New_York. "
            "Defaults to the system timezone. Requires Python 3.9+."
        ),
    )
    parser.add_argument(
        "--reminders",
        default="",
        help=(
            "Comma-separated reminder offsets in days before expiry, for example 14,7. "
            "Omit to hide reminder dates."
        ),
    )
    parser.add_argument(
        "--reminder-time",
        default="06:00",
        help="Local HH:MM time for reminder dates. Default: 06:00.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds. Default: 30.",
    )
    return parser.parse_args()


def fail(message: str, exit_code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def parse_reminder_offsets(value: str) -> List[int]:
    if not value.strip():
        return []

    offsets: List[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            days = int(item)
        except ValueError:
            fail(f"invalid --reminders value {item!r}; expected comma-separated integers")
        if days < 0:
            fail(f"invalid --reminders value {item!r}; days must be zero or greater")
        if days not in offsets:
            offsets.append(days)

    return sorted(offsets, reverse=True)


def parse_reminder_time(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        fail(f"invalid --reminder-time {value!r}; expected HH:MM")


def local_tzinfo(timezone_name: Optional[str]):
    if timezone_name is None:
        return datetime.now().astimezone().tzinfo

    if ZoneInfo is None:
        fail("--timezone requires Python 3.9+ because it uses the standard zoneinfo module")

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        fail(f"unknown timezone: {timezone_name}")


def format_timestamp(value: Optional[datetime], tzinfo=None) -> str:
    if value is None:
        return "-"
    if tzinfo is not None:
        value = value.astimezone(tzinfo)
    return value.strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def iso_timestamp(value: Optional[datetime], tzinfo=None) -> Optional[str]:
    if value is None:
        return None
    if tzinfo is not None:
        value = value.astimezone(tzinfo)
    return value.isoformat()


def load_auth(auth_path: str) -> Tuple[str, str]:
    path = Path(auth_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"auth file not found: {path}")
    except PermissionError:
        fail(f"permission denied reading auth file: {path}")
    except json.JSONDecodeError as exc:
        fail(f"auth file is not valid JSON: {path} ({exc})")

    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        fail(f"missing tokens object in {path}")

    token = tokens.get("access_token")
    account_id = tokens.get("account_id")

    if not isinstance(token, str) or not token:
        fail(f"missing tokens.access_token in {path}")
    if not isinstance(account_id, str) or not account_id:
        fail(f"missing tokens.account_id in {path}")

    return token, account_id


def validate_endpoint(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != EXPECTED_SCHEME or parsed.hostname != EXPECTED_HOST:
        fail("refusing to send credentials to an unexpected endpoint")


def fetch_reset_credits(token: str, account_id: str, timeout: float) -> Dict[str, Any]:
    validate_endpoint(API_URL)

    request = urllib.request.Request(
        API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "ChatGPT-Account-ID": account_id,
            "OpenAI-Beta": "codex-1",
            "originator": "Codex Desktop",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        fail(f"reset-credit endpoint returned HTTP {exc.code}")
    except urllib.error.URLError as exc:
        fail(f"could not reach reset-credit endpoint: {exc.reason}")
    except TimeoutError:
        fail(f"request timed out after {timeout:g} seconds")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        fail("endpoint returned non-JSON data")

    if not isinstance(payload, dict):
        fail("endpoint returned an unexpected JSON shape")

    return payload


def sanitized_credits(payload: Dict[str, Any], include_unavailable: bool) -> List[Credit]:
    raw_credits = payload.get("credits")
    if raw_credits is None:
        return []
    if not isinstance(raw_credits, list):
        fail("endpoint returned an unexpected credits field")

    credits: List[Credit] = []
    for raw_index, raw_credit in enumerate(raw_credits, start=1):
        if not isinstance(raw_credit, dict):
            continue

        status = str(raw_credit.get("status") or "")
        if status != "available" and not include_unavailable:
            continue

        credits.append(
            Credit(
                number=raw_index,
                title=str(raw_credit.get("title") or "Codex reset credit"),
                status=status,
                reset_type=str(raw_credit.get("reset_type") or ""),
                granted_at=parse_timestamp(raw_credit.get("granted_at")),
                expires_at=parse_timestamp(raw_credit.get("expires_at")),
                redeem_started_at=parse_timestamp(raw_credit.get("redeem_started_at")),
                redeemed_at=parse_timestamp(raw_credit.get("redeemed_at")),
            )
        )

    return sorted(
        credits,
        key=lambda credit: credit.expires_at or datetime.max.replace(tzinfo=timezone.utc),
    )


def reminder_at(
    expires_at: datetime,
    days_before: int,
    reminder_time: time,
    tzinfo,
) -> datetime:
    local_expiry = expires_at.astimezone(tzinfo)
    reminder_date = local_expiry.date() - timedelta(days=days_before)
    return datetime.combine(reminder_date, reminder_time, tzinfo=tzinfo)


def reminder_rows(
    credit: Credit,
    offsets: List[int],
    reminder_time: time,
    tzinfo,
) -> List[Dict[str, str]]:
    if credit.expires_at is None:
        return []

    rows = []
    now = datetime.now(tzinfo)
    for days_before in offsets:
        remind_at = reminder_at(credit.expires_at, days_before, reminder_time, tzinfo)
        rows.append(
            {
                "days_before": str(days_before),
                "local_time": remind_at.isoformat(),
                "status": "past" if remind_at < now else "upcoming",
            }
        )
    return rows


def serializable_credit(
    credit: Credit,
    reminder_offsets: List[int],
    reminder_time: time,
    tzinfo,
) -> Dict[str, Any]:
    return {
        "number": credit.number,
        "title": credit.title,
        "status": credit.status,
        "reset_type": credit.reset_type,
        "granted_at_utc": iso_timestamp(credit.granted_at),
        "expires_at_utc": iso_timestamp(credit.expires_at),
        "expires_at_local": iso_timestamp(credit.expires_at, tzinfo),
        "redeem_started_at_utc": iso_timestamp(credit.redeem_started_at),
        "redeemed_at_utc": iso_timestamp(credit.redeemed_at),
        "reminders": reminder_rows(credit, reminder_offsets, reminder_time, tzinfo),
    }


def print_json(
    payload: Dict[str, Any],
    credits: List[Credit],
    reminder_offsets: List[int],
    reminder_time: time,
    tzinfo,
) -> None:
    print(
        json.dumps(
            {
                "available_count": payload.get("available_count"),
                "credits_shown": len(credits),
                "local_timezone": str(tzinfo),
                "credits": [
                    serializable_credit(credit, reminder_offsets, reminder_time, tzinfo)
                    for credit in credits
                ],
            },
            indent=2,
        )
    )


def print_table(
    payload: Dict[str, Any],
    credits: List[Credit],
    reminder_offsets: List[int],
    reminder_time: time,
    tzinfo,
) -> None:
    print(f"Available reset credits: {payload.get('available_count', '-')}")
    print(f"Credits shown: {len(credits)}")
    print(f"Local timezone: {tzinfo}")
    if reminder_offsets:
        offsets = ", ".join(f"{days}d" for days in reminder_offsets)
        print(f"Reminder dates: {offsets} before expiry at {reminder_time.strftime('%H:%M')}")
    print()

    if not credits:
        print("No matching reset credits found.")
        return

    for credit in credits:
        print(f"Credit {credit.number}: {credit.title}")
        print(f"  Status:        {credit.status or '-'}")
        print(f"  Type:          {credit.reset_type or '-'}")
        print(f"  Granted UTC:   {format_timestamp(credit.granted_at, timezone.utc)}")
        print(f"  Expires UTC:   {format_timestamp(credit.expires_at, timezone.utc)}")
        print(f"  Expires local: {format_timestamp(credit.expires_at, tzinfo)}")

        for row in reminder_rows(credit, reminder_offsets, reminder_time, tzinfo):
            print(
                f"  Remind {row['days_before']:>2}d:    "
                f"{row['local_time']} ({row['status']})"
            )

        if credit.redeem_started_at or credit.redeemed_at:
            print(f"  Redeem start:  {format_timestamp(credit.redeem_started_at, timezone.utc)}")
            print(f"  Redeemed UTC:  {format_timestamp(credit.redeemed_at, timezone.utc)}")

        print()


def main() -> int:
    args = parse_args()

    if args.timeout <= 0:
        fail("--timeout must be greater than zero")

    tzinfo = local_tzinfo(args.timezone)
    reminder_offsets = parse_reminder_offsets(args.reminders)
    reminder_time = parse_reminder_time(args.reminder_time)

    token, account_id = load_auth(args.auth)
    payload = fetch_reset_credits(token, account_id, args.timeout)
    credits = sanitized_credits(payload, include_unavailable=args.include_unavailable)

    if args.json:
        print_json(payload, credits, reminder_offsets, reminder_time, tzinfo)
    else:
        print_table(payload, credits, reminder_offsets, reminder_time, tzinfo)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
