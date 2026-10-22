"""Textos de la demo y del dossier con un LLM (OmniRoute local, OpenAI-compatible) y respaldo fijo por sector."""
import json
import os
import re
from pathlib import Path

import httpx

BASE = {
    "restaurante": {
        "eslogan": "Cocina de siempre, en el corazón de Murcia",
        "servicios": ["Menú del día", "Tapas y raciones", "Comida para llevar", "Reservas para grupos"],
        "sobre": "Un sitio de barrio donde se come bien y se trata mejor. Producto fresco, recetas de la tierra y un equipo que te hace sentir en casa.",
        "beneficios": [
            "Que te encuentren en Google al buscar «dónde comer cerca»",
            "Carta y menú del día siempre actualizados, sin imprimir nada",
            "Reservas por WhatsApp o formulario a cualquier hora",
            "Más reseñas en Google con la placa NFC en la mesa",
        ],
    },
    "belleza": {
        "eslogan": "Tu momento para cuidarte",
        "servicios": ["Corte y peinado", "Color y mechas", "Tratamientos capilares", "Manicura y estética"],
        "sobre": "Un espacio cercano donde cuidamos de ti con calma, buenos productos y las últimas tendencias.",
        "beneficios": [
            "Citas online 24 horas: menos llamadas mientras trabajas",
            "Galería de trabajos que convence a clientes nuevos",
            "Precios y servicios claros antes de venir",
            "Más reseñas en Google con la placa NFC en el mostrador",
        ],
    },
    "salud": {
        "eslogan": "Cuidamos de tu salud con cercanía",
        "servicios": ["Primera consulta", "Revisiones", "Tratamientos personalizados", "Seguimiento"],
        "sobre": "Profesionales con experiencia que te atienden sin prisas y te explican cada paso.",
        "beneficios": [
            "Confianza: equipo, instalaciones y especialidades a la vista",
            "Petición de cita online y recordatorios",
            "Aparecer cuando buscan tu especialidad en tu barrio",
            "Más reseñas en Google con la placa NFC en recepción",
        ],
    },
    "taller": {
        "eslogan": "Trabajo bien hecho, precio claro",
        "servicios": ["Diagnosis", "Mantenimiento y revisiones", "Reparaciones", "Presupuesto sin compromiso"],
        "sobre": "Un taller de confianza: te decimos lo que necesita de verdad y te lo dejamos listo cuanto antes.",
        "beneficios": [
            "Pedir presupuesto o cita sin llamar",
            "Que te encuentren al buscar «taller cerca de mí»",
            "Mostrar trabajos, marcas y garantías",
            "Más reseñas en Google con la placa NFC en el mostrador",
        ],
    },
    "tienda": {
        "eslogan": "Lo que buscas, a la vuelta de la esquina",
        "servicios": ["Atención personalizada", "Novedades cada temporada", "Encargos", "Envoltorio para regalo"],
        "sobre": "Comercio de barrio con producto seleccionado y el trato de siempre.",
        "beneficios": [
            "Escaparate abierto 24 horas: novedades y ofertas",
            "Pedidos y reservas por WhatsApp",
            "Aparecer en Google Maps con horario y fotos",
            "Más reseñas en Google con la placa NFC junto a la caja",
        ],
    },
    "generica": {
        "eslogan": "Profesionales cerca de ti",
        "servicios": ["Atención personalizada", "Asesoramiento", "Presupuestos", "Seguimiento"],
        "sobre": "Un equipo cercano que conoce el barrio y a sus vecinos.",
        "beneficios": [
            "Imagen profesional y de confianza",
            "Contacto fácil por teléfono, WhatsApp o formulario",
            "Aparecer en Google cuando te buscan",
            "Más reseñas en Google con la placa NFC",
        ],
    },
}


def respaldo(c: dict) -> dict:
    t = json.loads(json.dumps(BASE.get(c["sector"], BASE["generica"])))
    t["guion"] = (
        f"Hola, soy José Luis, de aquí de Murcia. He preparado una web de ejemplo para {c['nombre']}: "
        "tienes el QR en esta hoja y la puedes ver ahora en el móvil. Se adapta a lo que necesitéis "
        "y va con una placa NFC para conseguir más reseñas en Google. ¿Le echas un vistazo?"
    )
    t["origen"] = "base"
    return t


PROMPT = """Eres redactor web para pequeños comercios de Murcia (España). Escribe en castellano de España, cercano y sencillo.
Comercio: {nombre}
Tipo: {tipo} (sector {sector})
Barrio/dirección: {lugar}
Datos públicos de OpenStreetMap: {extra}

Devuelve SOLO un JSON con estas claves:
- "eslogan": frase corta (máx. 60 caracteres), sin el nombre del comercio.
- "servicios": lista de 4 a 6 servicios típicos de este tipo de negocio (2-5 palabras cada uno).
- "sobre": 2 frases genéricas para «Sobre nosotros» (máx. 220 caracteres).
- "beneficios": 4 beneficios concretos de tener web para ESTE tipo de negocio (máx. 80 caracteres cada uno); el último sobre conseguir más reseñas en Google con una placa NFC.
- "guion": lo que diría José Luis en 30 segundos al entrar en el comercio para enseñarle la demo (máx. 400 caracteres, tuteo).
Prohibido inventar precios, años de experiencia, premios, reseñas, nombres de personas o datos concretos del comercio."""


def _clave(cfg: dict) -> str:
    if os.environ.get("OMNIROUTE_API_KEY"):
        return os.environ["OMNIROUTE_API_KEY"]
    ruta = Path(cfg["llm"]["env_clave"]).expanduser()
    if ruta.exists():
        for linea in ruta.read_text().splitlines():
            if linea.startswith("OMNIROUTE_API_KEY="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def validar(d: object) -> dict | None:
    """El JSON del modelo solo se acepta si tiene la forma esperada y longitudes razonables."""
    if not isinstance(d, dict):
        return None
    try:
        out = {
            "eslogan": str(d["eslogan"]).strip()[:80],
            "servicios": [str(s).strip()[:60] for s in d["servicios"]][:6],
            "sobre": str(d["sobre"]).strip()[:300],
            "beneficios": [str(s).strip()[:110] for s in d["beneficios"]][:4],
            "guion": str(d["guion"]).strip()[:500],
        }
    except (KeyError, TypeError):
        return None
    if not out["eslogan"] or len(out["servicios"]) < 3 or len(out["beneficios"]) < 3 or not out["sobre"]:
        return None
    if re.search(r"\d+\s*(€|euros)", json.dumps(out, ensure_ascii=False)):
        return None  # nada de precios inventados
    # No sabemos cómo se llama quien atiende: fuera saludos con nombre propio («¡Hola Ana!»).
    out["guion"] = re.sub(r"^¡?Hola,?\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]*\s*[!,.]", "¡Hola!", out["guion"])
    return out


def extraer_json(texto: str) -> object:
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def redactar(c: dict, cfg: dict, cliente: httpx.Client | None = None) -> dict:
    clave = _clave(cfg)
    if not clave:
        return respaldo(c)
    tags = c.get("tags") or {}
    extra = {k: v for k, v in tags.items() if k in ("cuisine", "opening_hours", "takeaway", "delivery", "outdoor_seating", "healthcare:speciality", "beauty", "craft", "diet:vegetarian")}
    msg = PROMPT.format(nombre=c["nombre"], tipo=c["tipo"], sector=c["sector"], lugar=c.get("zona") or c.get("direccion") or "Murcia", extra=json.dumps(extra, ensure_ascii=False))
    cl = cliente or httpx.Client(timeout=90)
    try:
        r = cl.post(
            f"{cfg['llm']['url']}/chat/completions",
            headers={"Authorization": f"Bearer {clave}"},
            json={"model": cfg["llm"]["modelo"], "messages": [{"role": "user", "content": msg}], "temperature": 0.7, "max_tokens": 1500},
        )
        r.raise_for_status()
        contenido = r.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return respaldo(c)
    ok = validar(extraer_json(contenido))
    if not ok:
        return respaldo(c)
    ok["origen"] = "ia"
    return ok
