"""Ruta de visitas del día: orden por cercanía y hoja de ruta imprimible."""
import base64
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import PLANTILLAS
from .dossier import qr_png
from .horario import legible
from .osm import distancia_km


def ordenar(comercios: list[dict], inicio: tuple[float, float]) -> list[dict]:
    """Vecino más próximo desde `inicio`: suficiente para una ruta a pie de 10–15 paradas."""
    pendientes = list(comercios)
    orden = []
    pos = inicio
    while pendientes:
        sig = min(pendientes, key=lambda c: distancia_km(pos, (c["lat"], c["lon"])))
        pendientes.remove(sig)
        orden.append(sig)
        pos = (sig["lat"], sig["lon"])
    return orden


def enlace_maps(orden: list[dict]) -> str:
    """Google Maps a pie con paradas (máx. 9 intermedias: lo que admite la URL)."""
    pts = [f"{c['lat']},{c['lon']}" for c in orden[:11]]
    if len(pts) < 2:
        return f"https://www.google.com/maps/search/?api=1&query={pts[0]}" if pts else ""
    url = f"https://www.google.com/maps/dir/?api=1&travelmode=walking&origin={pts[0]}&destination={pts[-1]}"
    if len(pts) > 2:
        url += "&waypoints=" + quote("|".join(pts[1:-1]))
    return url


def hoja(orden: list[dict], titulo: str) -> str:
    env = Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))
    paradas = [{**c, "horario_txt": "; ".join(legible(c.get("horario") or "")) or "Sin horario en OSM",
                } for c in orden]
    maps = enlace_maps(orden)
    qr = "data:image/png;base64," + base64.b64encode(qr_png(maps)).decode() if maps else ""
    return env.get_template("ruta.html").render(paradas=paradas, titulo=titulo, qr=qr)
