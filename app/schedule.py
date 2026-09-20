"""Huecos de publicación, leídos de schedule.txt (formato explicado en ese archivo).

Cada hueco es «día HH:MM tipo». En cada hueco se publica UN post de ese tipo.
"""
import datetime as dt
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEDULE_FILE = os.environ.get("SCHEDULE_FILE", str(Path(__file__).with_name("schedule.txt")))
UTC = dt.timezone.utc

KINDS = ("carrusel", "publicacion", "historia")
KIND_ALIASES = {"carrusel": "carrusel", "publicacion": "publicacion", "publicación": "publicacion",
                "historia": "historia"}
KIND_LABELS = {"carrusel": "carrusel", "publicacion": "publicación", "historia": "historia"}

DAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}
DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


class ScheduleError(Exception):
    """schedule.txt no es válido."""


class Schedule:
    def __init__(self, tz: ZoneInfo, tz_name: str, tolerance: dt.timedelta,
                 slots: list[tuple[int, dt.time, str]]):
        self.tz, self.tz_name, self.tolerance, self.slots = tz, tz_name, tolerance, slots

    def kinds(self) -> set[str]:
        return {kind for _, _, kind in self.slots}

    def slot_times(self, start: dt.datetime, end: dt.datetime, kind: str) -> list[dt.datetime]:
        """Huecos de ese tipo (en UTC) con start <= hueco <= end, ordenados."""
        out = []
        day = (start.astimezone(self.tz) - dt.timedelta(days=1)).date()
        last_day = (end.astimezone(self.tz) + dt.timedelta(days=1)).date()
        while day <= last_day:
            for weekday, at, slot_kind in self.slots:
                if slot_kind == kind and day.weekday() == weekday:
                    slot = dt.datetime.combine(day, at, tzinfo=self.tz).astimezone(UTC)
                    if start <= slot <= end:
                        out.append(slot)
            day += dt.timedelta(days=1)
        return sorted(out)

    def due_slots(self, now: dt.datetime) -> dict[str, dt.datetime]:
        """Por tipo, el hueco más reciente que ya empezó y sigue dentro de la tolerancia."""
        due = {}
        for kind in KINDS:
            candidates = self.slot_times(now - self.tolerance, now, kind)
            if candidates:
                due[kind] = candidates[-1]
        return due

    def upcoming(self, now: dt.datetime, last_used: dt.datetime | None, n: int, kind: str) -> list[dt.datetime]:
        """Próximos n huecos aprovechables de ese tipo (los ya usados no cuentan)."""
        found = []
        for slot in self.slot_times(now - self.tolerance, now + dt.timedelta(days=60), kind):
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
        return ", ".join(f"{DAY_NAMES[d]} {t:%H:%M} ({KIND_LABELS[k]})" for d, t, k in sorted(self.slots))


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
        m = re.fullmatch(r"([A-Za-záéíóúÁÉÍÓÚñÑ]+)\s+(\d{1,2}):(\d{2})\s+([A-Za-záéíóúÁÉÍÓÚñÑ]+)", line)
        if not m or m.group(1).lower() not in DAYS:
            raise ScheduleError(
                f"línea {number}: no entiendo «{raw.strip()}» (usa «martes 15:30 carrusel»)")
        kind = KIND_ALIASES.get(m.group(4).lower())
        if not kind:
            raise ScheduleError(
                f"línea {number}: tipo desconocido «{m.group(4)}» (usa carrusel, publicacion o historia)")
        hour, minute = int(m.group(2)), int(m.group(3))
        if hour > 23 or minute > 59:
            raise ScheduleError(f"línea {number}: hora no válida")
        slots.append((DAYS[m.group(1).lower()], dt.time(hour, minute), kind))
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
