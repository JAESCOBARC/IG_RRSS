"""Programación guardada en la base de datos (se edita desde el panel).

La primera vez que arranca la app, se copia la de schedule.txt; a partir de ahí manda la base
de datos y schedule.txt ya no se lee.
"""
import datetime as dt
import uuid

import db
import schedule
from schedule import Schedule, ScheduleError

KEY_SEEDED, KEY_TZ, KEY_TOLERANCE = "schedule_seeded", "schedule_tz", "schedule_tolerance"


def _seed(conn) -> None:
    cfg = schedule.load()  # ScheduleError si schedule.txt no es válido
    for weekday, at, kind in cfg.slots:
        db.execute(conn, ("INSERT INTO schedule_slots (id, weekday, slot_time, kind, created_at) "
                          "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING"),
                   (uuid.uuid4().hex, weekday, f"{at:%H:%M}", kind, schedule.EPOCH.isoformat()))
    db.kv_set(conn, KEY_TZ, cfg.tz_name)
    db.kv_set(conn, KEY_TOLERANCE, str(int(cfg.tolerance.total_seconds() // 60)))
    db.kv_set(conn, KEY_SEEDED, db.now())


def load(conn) -> Schedule:
    if db.kv_get(conn, KEY_SEEDED) is None:
        _seed(conn)
    rows = db.query(conn, "SELECT weekday, slot_time, kind, created_at FROM schedule_slots")
    return schedule.build(db.kv_get(conn, KEY_TZ), int(db.kv_get(conn, KEY_TOLERANCE)), rows)


def list_slots(conn) -> list[dict]:
    """Huecos ordenados por día y hora, con el nombre del día y la etiqueta del tipo."""
    load(conn)  # asegura la carga inicial
    rows = db.query(conn, "SELECT id, weekday, slot_time, kind FROM schedule_slots")
    rows.sort(key=lambda r: (r["weekday"], r["slot_time"].zfill(5), r["kind"]))
    for r in rows:
        r["day"] = schedule.DAY_NAMES[r["weekday"]]
        r["kind_label"] = schedule.KIND_LABELS[r["kind"]]
    return rows


def add_slot(conn, day, time_text: str, kind_text: str) -> None:
    load(conn)
    weekday, at, kind = schedule.parse_day(day), schedule.parse_time(time_text), schedule.parse_kind(kind_text)
    try:
        db.execute(conn, ("INSERT INTO schedule_slots (id, weekday, slot_time, kind, created_at) "
                          "VALUES (%s, %s, %s, %s, %s)"),
                   (uuid.uuid4().hex, weekday, f"{at:%H:%M}", kind, db.now_precise()))
    except Exception as exc:
        if db.one(conn, "SELECT 1 AS x FROM schedule_slots WHERE weekday = %s AND slot_time = %s AND kind = %s",
                  (weekday, f"{at:%H:%M}", kind)):
            raise ScheduleError("Ese hueco ya existe.") from exc
        raise


def delete_slot(conn, slot_id: str) -> bool:
    return bool(db.query(conn, "DELETE FROM schedule_slots WHERE id = %s RETURNING id", (slot_id,)))


def save_settings(conn, tz_name: str, tolerance_text: str) -> None:
    load(conn)
    tz_name = (tz_name or "").strip()
    schedule.build_tz(tz_name)
    try:
        minutes = int(str(tolerance_text).strip())
    except ValueError:
        minutes = None
    schedule.check_tolerance(minutes)
    db.kv_set(conn, KEY_TZ, tz_name)
    db.kv_set(conn, KEY_TOLERANCE, str(minutes))
