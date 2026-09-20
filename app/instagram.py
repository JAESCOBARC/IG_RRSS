"""Cliente mínimo de la API de Instagram (Instagram Login) para publicar imágenes y carruseles."""
import os
import time

import requests

API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")
API = f"https://graph.instagram.com/{API_VERSION}"
POLL_SECONDS = 3
POLL_ATTEMPTS = 40


class IGError(Exception):
    """Error de la API de Instagram."""


def api_call(method: str, path: str, token: str, **params) -> dict:
    params["access_token"] = token
    resp = requests.request(method, f"{API}/{path}", params=params, timeout=60)
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:300]}
    if resp.status_code >= 400 or "error" in body:
        err = body.get("error", body)
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise IGError(f"API {resp.status_code}: {msg}")
    return body


def wait_until_ready(container_id: str, token: str) -> None:
    for _ in range(POLL_ATTEMPTS):
        status = api_call("GET", container_id, token, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise IGError(f"el contenedor {container_id} quedó en estado {status}")
        time.sleep(POLL_SECONDS)
    raise IGError(f"el contenedor {container_id} no terminó de procesarse a tiempo")


def publish(image_urls: list[str], caption: str, user_id: str, token: str, kind: str = "carrusel") -> dict:
    """Publica una historia (1 imagen), una publicación (1 imagen) o un carrusel (2-10).
    Devuelve {"media_id", "permalink"}. Las historias no admiten texto de publicación."""
    if kind == "historia":
        container = api_call("POST", f"{user_id}/media", token,
                             media_type="STORIES", image_url=image_urls[0])["id"]
    elif len(image_urls) == 1:
        container = api_call("POST", f"{user_id}/media", token,
                             image_url=image_urls[0], caption=caption)["id"]
    else:
        children = [api_call("POST", f"{user_id}/media", token,
                             image_url=url, is_carousel_item="true")["id"] for url in image_urls]
        for child in children:
            wait_until_ready(child, token)
        container = api_call("POST", f"{user_id}/media", token, media_type="CAROUSEL",
                             children=",".join(children), caption=caption)["id"]
    wait_until_ready(container, token)
    media_id = api_call("POST", f"{user_id}/media_publish", token, creation_id=container)["id"]
    permalink = ""
    try:
        permalink = api_call("GET", media_id, token, fields="permalink").get("permalink", "")
    except IGError:
        pass  # ya está publicado; el permalink es solo informativo
    return {"media_id": media_id, "permalink": permalink}


def refresh(token: str) -> tuple[str, int]:
    """Renueva un token de larga duración (debe tener >24 h y no haber caducado)."""
    resp = requests.get("https://graph.instagram.com/refresh_access_token",
                        params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400 or "access_token" not in body:
        err = body.get("error", {})
        raise IGError(f"no se pudo renovar el token: {err.get('message') if isinstance(err, dict) else body}")
    return body["access_token"], int(body.get("expires_in", 0))
