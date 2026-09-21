"""Usuarios del panel: alta, baja, contraseñas y comprobación de acceso.

Hay dos orígenes de cuenta:
- «admin»: la cuenta integrada, con la contraseña de ADMIN_PASSWORD (variable de entorno de
  Render). No vive en la base de datos, no se puede borrar y sirve de recuperación.
- Las cuentas creadas desde el panel, guardadas con la contraseña cifrada (hash).
"""
import re
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

import db

ENV_USERNAME = "admin"
ENV_ID = "env"
ROLES = {"admin": "Administrador", "editor": "Editor"}
MIN_PASSWORD, MAX_PASSWORD = 8, 128
_DUMMY_HASH = generate_password_hash("sin-usuario")  # para no delatar por el tiempo si un usuario existe


class AccountError(Exception):
    """Dato no válido al crear o cambiar una cuenta (el mensaje se muestra tal cual)."""


def env_user() -> dict:
    return {"id": ENV_ID, "username": ENV_USERNAME, "role": "admin", "builtin": True}


def normalize_username(name: str) -> str:
    name = (name or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,32}", name):
        raise AccountError("El usuario debe tener entre 3 y 32 caracteres: letras, números, punto, guion o guion bajo.")
    if name == ENV_USERNAME:
        raise AccountError("«admin» está reservado para la cuenta integrada.")
    return name


def check_password_rules(password: str) -> None:
    if not MIN_PASSWORD <= len(password or "") <= MAX_PASSWORD:
        raise AccountError(f"La contraseña debe tener entre {MIN_PASSWORD} y {MAX_PASSWORD} caracteres.")


def create(conn, username: str, password: str, role: str, created_by: str) -> dict:
    name = normalize_username(username)
    check_password_rules(password)
    if role not in ROLES:
        raise AccountError("Rol no válido.")
    if db.one(conn, "SELECT 1 AS x FROM users WHERE username = %s", (name,)):
        raise AccountError(f"Ya existe un usuario «{name}».")
    uid = uuid.uuid4().hex
    try:
        db.execute(conn, ("INSERT INTO users (id, username, password_hash, role, created_at, created_by) "
                          "VALUES (%s, %s, %s, %s, %s, %s)"),
                   (uid, name, generate_password_hash(password), role, db.now(), created_by))
    except Exception as exc:  # dos altas simultáneas con el mismo nombre: gana la primera
        if db.one(conn, "SELECT 1 AS x FROM users WHERE username = %s", (name,)):
            raise AccountError(f"Ya existe un usuario «{name}».") from exc
        raise
    return {"id": uid, "username": name, "role": role}


def get(conn, uid: str):
    return db.one(conn, "SELECT id, username, role, created_at, created_by FROM users WHERE id = %s", (uid,))


def list_all(conn) -> list[dict]:
    return db.query(conn, "SELECT id, username, role, created_at, created_by FROM users ORDER BY created_at ASC")


def delete(conn, uid: str) -> bool:
    return bool(db.query(conn, "DELETE FROM users WHERE id = %s RETURNING id", (uid,)))


def set_password(conn, uid: str, password: str) -> None:
    check_password_rules(password)
    db.execute(conn, "UPDATE users SET password_hash = %s WHERE id = %s", (generate_password_hash(password), uid))


def verify_password(conn, uid: str, password: str) -> bool:
    row = db.one(conn, "SELECT password_hash FROM users WHERE id = %s", (uid,))
    return bool(row) and check_password_hash(row["password_hash"], password)


def authenticate(conn, username: str, password: str, env_password: str, same) -> dict | None:
    """Usuario si las credenciales son correctas. `same` compara textos en tiempo constante."""
    name = (username or "").strip().lower()
    if name == ENV_USERNAME:
        return env_user() if env_password and same(password or "", env_password) else None
    row = db.one(conn, "SELECT id, username, role, password_hash FROM users WHERE username = %s", (name,))
    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password or "")
    return {"id": row["id"], "username": row["username"], "role": row["role"]} if row and ok else None
