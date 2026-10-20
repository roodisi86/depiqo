"""Small shared helpers: time, money, identifiers, formatting."""
import hashlib
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MONTHS_NL = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
             "september", "oktober", "november", "december"]


def now():
    return datetime.now(timezone.utc)


def now_iso():
    return now().isoformat(timespec="seconds")


LOCAL_TZ = ZoneInfo("Europe/Amsterdam")  # NL and BE share this zone; legal deadlines run on the local calendar date


def today():
    """Calendar date in Nederland/België. Not the UTC date: between 00:00 and 02:00 local time those differ."""
    return datetime.now(LOCAL_TZ).date()


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_dt(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def add_months(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    days_in_month = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, days_in_month))


def token():
    return secrets.token_urlsafe(32)


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_pid():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def parse_euros(value):
    """'2.400,50' / '2400.50' / '2400' -> cents. Returns None when invalid."""
    if value is None:
        return None
    s = str(value).strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d{1,9}(\.\d{1,2})?", s):
        return None
    euros, _, cents = s.partition(".")
    return int(euros) * 100 + int((cents + "00")[:2])


def eur(cents, decimals=True):
    if cents is None:
        return "—"
    neg = cents < 0
    cents = abs(int(cents))
    whole = f"{cents // 100:,}".replace(",", ".")
    text = f"€ {whole},{cents % 100:02d}" if decimals else f"€ {whole}"
    return ("− " if neg else "") + text


def date_nl(value):
    d = parse_date(value) if not isinstance(value, datetime) else value.date()
    if not d:
        return "—"
    return f"{d.day} {MONTHS_NL[d.month - 1]} {d.year}"


def datetime_nl(value):
    dt = parse_dt(value) if isinstance(value, str) else value
    if not dt:
        return "—"
    local = dt.astimezone(LOCAL_TZ)
    return f"{local.day} {MONTHS_NL[local.month - 1][:3]} {local.year}, {local:%H:%M}"


def pct(bps):
    """Basis points as a Dutch percentage: 10000 -> '100%', 10150 -> '101,5%'."""
    if bps is None:
        return "—"
    whole, rest = divmod(int(bps), 100)
    return f"{whole}%" if rest == 0 else f"{bps / 100:.1f}%".replace(".", ",")


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def valid_email(value):
    return bool(re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}", value or ""))


def valid_iban(value):
    s = re.sub(r"\s+", "", (value or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def format_iban(value):
    s = re.sub(r"\s+", "", (value or "")).upper()
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))
