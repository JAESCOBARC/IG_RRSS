"""Huecos de publicación. Cada hueco es «día HH:MM tipo» y en cada uno se publica UN post de ese tipo.

La programación vigente vive en la base de datos y se edita desde el panel (schedule_store.py).
schedule.txt (formato explicado en ese archivo) solo es la programación inicial: se copia a la
base de datos la primera vez que arranca la app.
"""
import datetime as dt
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEDULE_FILE = os.environ.get("SCHEDULE_FILE", str(Path(__file__).with_name("schedule.txt")))
UTC = dt.timezone.utc
EPOCH = dt.datetime(1970, 1, 1, tzinfo=UTC)
MIN_TOLERANCE, MAX_TOLERANCE = 30, 720  # minutos; el programador avisa cada 30

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
                 slots: list[tuple[int, dt.time, str]],
                 since: dict[tuple[int, dt.time, str], dt.datetime] | None = None):
        self.tz, self.tz_name, self.tolerance, self.slots = tz, tz_name, tolerance, slots
        # desde cuándo vale cada hueco: uno recién creado no publica a posteriori una hora ya pasada
        self.since = since or {}

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
                    if start <= slot <= end and slot >= self.since.get((weekday, at, kind), EPOCH):
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
        if not self.slots:
            return "ninguno"
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
    tz = build_tz(tz_name)
    return Schedule(tz, tz_name, tolerance, sorted(set(slots)))


def build_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError(f"zona horaria desconocida: {tz_name}")


def check_tolerance(minutes) -> int:
    if not isinstance(minutes, int) or not MIN_TOLERANCE <= minutes <= MAX_TOLERANCE:
        raise ScheduleError(f"la tolerancia debe ser un número de minutos entre {MIN_TOLERANCE} y {MAX_TOLERANCE}")
    return minutes


def parse_day(text) -> int:
    text = str(text).strip().lower()
    day = int(text) if text.isdigit() else DAYS.get(text)
    if day is None or not 0 <= day <= 6:
        raise ScheduleError("día no válido")
    return day


def parse_time(text: str) -> dt.time:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", (text or "").strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ScheduleError("hora no válida (usa HH:MM)")
    return dt.time(int(m.group(1)), int(m.group(2)))


def parse_kind(text: str) -> str:
    kind = KIND_ALIASES.get((text or "").strip().lower())
    if not kind:
        raise ScheduleError("tipo no válido (carrusel, publicación o historia)")
    return kind


def build(tz_name: str, tolerance_minutes: int, rows: list[dict]) -> Schedule:
    """Programación a partir de filas de la base de datos (puede no tener ningún hueco)."""
    slots, since = [], {}
    for r in rows:
        key = (r["weekday"], parse_time(r["slot_time"]), r["kind"])
        slots.append(key)
        since[key] = dt.datetime.fromisoformat(r["created_at"])
    return Schedule(build_tz(tz_name), tz_name, dt.timedelta(minutes=tolerance_minutes), sorted(set(slots)), since)


def load(path: str | None = None) -> Schedule:
    try:
        text = Path(path or SCHEDULE_FILE).read_text(encoding="utf-8")
    except OSError as exc:
        raise ScheduleError(f"no se puede leer schedule.txt: {exc}")
    return parse(text)
