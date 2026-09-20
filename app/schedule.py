"""Huecos de publicación, leídos de schedule.txt (formato explicado en ese archivo)."""
import datetime as dt
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEDULE_FILE = os.environ.get("SCHEDULE_FILE", str(Path(__file__).with_name("schedule.txt")))
UTC = dt.timezone.utc

DAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}
DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


class ScheduleError(Exception):
    """schedule.txt no es válido."""


class Schedule:
    def __init__(self, tz: ZoneInfo, tz_name: str, tolerance: dt.timedelta, slots: list[tuple[int, dt.time]]):
        self.tz, self.tz_name, self.tolerance, self.slots = tz, tz_name, tolerance, slots

    def slot_times(self, start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
        """Todos los huecos (en UTC) con start <= hueco <= end, ordenados."""
        out = []
        day = (start.astimezone(self.tz) - dt.timedelta(days=1)).date()
        last_day = (end.astimezone(self.tz) + dt.timedelta(days=1)).date()
        while day <= last_day:
            for weekday, at in self.slots:
                if day.weekday() == weekday:
                    slot = dt.datetime.combine(day, at, tzinfo=self.tz).astimezone(UTC)
                    if start <= slot <= end:
                        out.append(slot)
            day += dt.timedelta(days=1)
        return sorted(out)

    def due_slot(self, now: dt.datetime):
        """Hueco más reciente que ya empezó y sigue dentro de la tolerancia, o None."""
        candidates = self.slot_times(now - self.tolerance, now)
        return candidates[-1] if candidates else None

    def upcoming(self, now: dt.datetime, last_used: dt.datetime | None, n: int) -> list[dt.datetime]:
        """Próximos n huecos aprovechables (los ya usados no cuentan)."""
        found = []
        for slot in self.slot_times(now - self.tolerance, now + dt.timedelta(days=60)):
            if last_used and slot <= last_used:
                continue
            found.append(slot)
            if len(found) == n:
                break
        return found

    def label(self, slot: dt.datetime) -> str:
        local = slot.astimezone(self.tz)
        return f"{DAY_NAMES[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, {local:%H:%M}"

    def describe(self) -> str:
        return ", ".join(f"{DAY_NAMES[d]} {t:%H:%M}" for d, t in sorted(self.slots))


def parse(text: str) -> Schedule:
    tz_name, tolerance, slots = "Europe/Madrid", dt.timedelta(minutes=120), []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" in line and line.split(":", 1)[0].strip().lower() in ("zona", "tolerancia_minutos"):
            key, value = (p.strip() for p in line.split(":", 1))
            if key.lower() == "zona":
                tz_name = value
            else:
                if not value.isdigit():
                    raise ScheduleError(f"línea {number}: tolerancia_minutos debe ser un número")
                tolerance = dt.timedelta(minutes=int(value))
            continue
        m = re.fullmatch(r"([A-Za-záéíóúÁÉÍÓÚñÑ]+)\s+(\d{1,2}):(\d{2})", line)
        if not m or m.group(1).lower() not in DAYS:
            raise ScheduleError(f"línea {number}: no entiendo «{raw.strip()}» (usa «martes 15:30»)")
        hour, minute = int(m.group(2)), int(m.group(3))
        if hour > 23 or minute > 59:
            raise ScheduleError(f"línea {number}: hora no válida")
        slots.append((DAYS[m.group(1).lower()], dt.time(hour, minute)))
    if not slots:
        raise ScheduleError("no hay ningún hueco definido")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError(f"zona horaria desconocida: {tz_name}")
    return Schedule(tz, tz_name, tolerance, sorted(set(slots)))


def load(path: str | None = None) -> Schedule:
    try:
        text = Path(path or SCHEDULE_FILE).read_text(encoding="utf-8")
    except OSError as exc:
        raise ScheduleError(f"no se puede leer schedule.txt: {exc}")
    return parse(text)
