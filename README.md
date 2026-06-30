# Codex Reset Dates

A small dependency-free Python CLI that shows your available Codex rate-limit reset credits and when they expire.

The script reads your local Codex Desktop auth file, calls the ChatGPT reset-credit endpoint, and prints only sanitized fields. It does not print your access token, account ID, profile image URL, profile user ID, email-like fields, or the raw API response.

## Requirements

- Python 3.9+
- Codex Desktop logged in on the same machine
- A local Codex auth file at `~/.codex/auth.json`

No external packages are required.

## Install

Clone or download this repository, then run the script directly:

```bash
python3 codex_reset_dates.py
```

On Windows:

```powershell
py .\codex_reset_dates.py
```

## Usage

Show available credits:

```bash
python3 codex_reset_dates.py
```

Show expiration dates plus reminder dates two weeks and one week before expiry:

```bash
python3 codex_reset_dates.py --reminders 14,7
```

Use a specific local timezone and reminder time:

```bash
python3 codex_reset_dates.py --timezone America/New_York --reminders 14,7 --reminder-time 06:00
```

Print sanitized JSON:

```bash
python3 codex_reset_dates.py --json
```

Use a custom auth file:

```bash
python3 codex_reset_dates.py --auth ~/.codex/auth.json
```

Include redeemed or unavailable credits:

```bash
python3 codex_reset_dates.py --include-unavailable
```

## Options

```text
--auth PATH              Path to Codex auth.json. Default: ~/.codex/auth.json
--json                   Print sanitized JSON instead of a table.
--include-unavailable    Include redeemed or unavailable credits.
--timezone NAME          IANA timezone for local dates. Defaults to system timezone.
--reminders DAYS         Comma-separated days before expiry, for example 14,7.
--reminder-time HH:MM    Local reminder time. Default: 06:00.
--timeout SECONDS        HTTP timeout. Default: 30.
```

## Example Output

```text
Available reset credits: 2
Credits shown: 2
Local timezone: America/New_York
Reminder dates: 14d, 7d before expiry at 06:00

Credit 1: Full reset (Weekly + 5 hr)
  Status:        available
  Type:          codex_rate_limits
  Granted UTC:   2026-01-01 12:00:00 UTC
  Expires UTC:   2026-01-31 12:00:00 UTC
  Expires local: 2026-01-31 07:00:00 EST
  Remind 14d:    2026-01-17T06:00:00-05:00 (past)
  Remind  7d:    2026-01-24T06:00:00-05:00 (upcoming)

Credit 2: Full reset (Weekly + 5 hr)
  Status:        available
  Type:          codex_rate_limits
  Granted UTC:   2026-01-08 18:30:00 UTC
  Expires UTC:   2026-02-07 18:30:00 UTC
  Expires local: 2026-02-07 13:30:00 EST
  Remind 14d:    2026-01-24T06:00:00-05:00 (upcoming)
  Remind  7d:    2026-01-31T06:00:00-05:00 (upcoming)
```

## Security Notes

- This script reads `~/.codex/auth.json`, which contains sensitive local auth material.
- It sends the token only to `https://chatgpt.com/...`.
- It validates the endpoint before sending credentials.
- It does not print the token, account ID, raw response, profile URL, or profile user ID.
- Do not publish your real command output without checking it first.
- Do not commit `~/.codex/auth.json`, copied API responses, screenshots that show account fields, or terminal logs that include your local username.

## Caveats

This uses an undocumented ChatGPT backend endpoint. It may change or stop working without notice.

These credits are Codex rate-limit reset credits. They are not necessarily the same thing as your normal rolling usage-limit reset time.

## License

MIT
