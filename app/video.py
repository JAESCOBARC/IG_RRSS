"""Lectura mínima de cabeceras MP4 (sin ffmpeg en el servidor): duración, tamaño y códec."""
import struct


def _boxes(data: bytes, start: int, end: int):
    """(tipo, inicio_del_contenido, fin) de cada caja entre start y end."""
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        head = 8
        if size == 1 and pos + 16 <= end:
            size, head = struct.unpack(">Q", data[pos + 8:pos + 16])[0], 16
        elif size == 0:
            size = end - pos
        if size < head or pos + size > end:
            return
        yield kind, pos + head, pos + size
        pos += size


def mp4_info(data: bytes) -> dict | None:
    """{"seconds", "width", "height", "h264"} de un MP4, o None si no se puede leer."""
    if data[4:8] != b"ftyp":
        return None
    info = {"seconds": None, "width": 0, "height": 0, "h264": b"avc1" in data}
    for kind, a, b in _boxes(data, 0, len(data)):
        if kind != b"moov":
            continue
        for k2, a2, b2 in _boxes(data, a, b):
            if k2 == b"mvhd":
                version = data[a2]
                if version == 1:
                    scale, dur = struct.unpack(">IQ", data[a2 + 20:a2 + 32])
                else:
                    scale, dur = struct.unpack(">II", data[a2 + 12:a2 + 20])
                info["seconds"] = dur / scale if scale else None
            elif k2 == b"trak":
                for k3, a3, b3 in _boxes(data, a2, b2):
                    if k3 == b"tkhd":
                        w, h = struct.unpack(">II", data[b3 - 8:b3])
                        if (w >> 16) and (h >> 16) and not info["width"]:
                            info["width"], info["height"] = w >> 16, h >> 16
    return info if info["seconds"] and info["width"] else None
