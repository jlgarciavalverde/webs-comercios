"""Genera la demo estática de cada comercio y el sitio completo que se publica en Cloudflare Pages."""
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import PLANTILLAS
from .horario import legible

# Aspecto por sector: colores, tipografía, icono y textos de las llamadas a la acción.
TEMAS = {
    "restaurante": {"color": "#b4441f", "suave": "#fbefe7", "oscuro": "#3b1a0e", "fuente": "Fraunces", "icono": "plato",
                    "cta": "Reservar mesa", "seccion": "Nuestra carta", "form": "Reserva tu mesa"},
    "belleza": {"color": "#a2457a", "suave": "#f9edf4", "oscuro": "#3a1630", "fuente": "Playfair Display", "icono": "tijeras",
                "cta": "Pedir cita", "seccion": "Servicios", "form": "Pide tu cita"},
    "salud": {"color": "#167a7a", "suave": "#e8f5f4", "oscuro": "#0c3433", "fuente": "Nunito", "icono": "cruz",
              "cta": "Pedir cita", "seccion": "Especialidades", "form": "Solicita tu cita"},
    "taller": {"color": "#c2410c", "suave": "#f3f4f6", "oscuro": "#1f2937", "fuente": "Oswald", "icono": "llave",
               "cta": "Pedir presupuesto", "seccion": "Qué hacemos", "form": "Pide presupuesto"},
    "tienda": {"color": "#2f5aa8", "suave": "#eef3fb", "oscuro": "#14264a", "fuente": "DM Serif Display", "icono": "bolsa",
               "cta": "Escríbenos", "seccion": "Lo que encontrarás", "form": "Haz tu encargo"},
    "generica": {"color": "#334155", "suave": "#f1f5f9", "oscuro": "#0f172a", "fuente": "Inter", "icono": "estrella",
                 "cta": "Contactar", "seccion": "Servicios", "form": "Contacta con nosotros"},
}

ROBOTS = "User-agent: *\nDisallow: /\n"
CABECERAS = "/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n"


def _entorno() -> Environment:
    return Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))


def _movil(tel: str) -> str:
    """Solo móviles españoles (6xx/7xx) tienen WhatsApp con sentido."""
    d = re.sub(r"\D", "", tel)
    if d.startswith("34"):
        d = d[2:]
    return f"34{d}" if len(d) == 9 and d[0] in "67" else ""


def contexto(c: dict, textos: dict, autor: str) -> dict:
    tema = TEMAS.get(c["sector"], TEMAS["generica"])
    lat, lon = c["lat"], c["lon"]
    d = 0.004
    return {
        "c": c,
        "t": textos,
        "tema": tema,
        "autor": autor,
        "horario": legible(c.get("horario") or ""),
        "tel_href": "tel:" + re.sub(r"[^\d+]", "", c["telefono"]) if c.get("telefono") else "",
        "whatsapp": _movil(c.get("telefono") or ""),
        "mapa": f"https://www.openstreetmap.org/export/embed.html?bbox={lon - d}%2C{lat - d / 2}%2C{lon + d}%2C{lat + d / 2}&layer=mapnik&marker={lat}%2C{lon}",
        "como_llegar": f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lon}",
        "fuente_url": quote(tema["fuente"]),
    }


def generar(c: dict, textos: dict, destino: Path, autor: str) -> Path:
    """Escribe `destino/<slug>/index.html`."""
    html = _entorno().get_template("demo.html").render(**contexto(c, textos, autor))
    carpeta = destino / c["slug"]
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "index.html").write_text(html)
    return carpeta / "index.html"


def construir_sitio(demos: list[tuple[dict, dict]], sitio: Path, autor: str) -> None:
    """Rehace el sitio entero: solo las demos activas, raíz sin listado y nada indexable."""
    if sitio.exists():
        shutil.rmtree(sitio)
    sitio.mkdir(parents=True)
    (sitio / "robots.txt").write_text(ROBOTS)
    (sitio / "_headers").write_text(CABECERAS)
    (sitio / "index.html").write_text(_entorno().get_template("raiz.html").render(autor=autor))
    for c, t in demos:
        generar(c, t, sitio, autor)
