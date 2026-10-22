"""`opening_hours` de OSM → líneas legibles en castellano. Si no se entiende, se devuelve tal cual."""
import re

DIAS = {"Mo": "lunes", "Tu": "martes", "We": "miércoles", "Th": "jueves", "Fr": "viernes", "Sa": "sábado", "Su": "domingo", "PH": "festivos"}
ORDEN = list(DIAS)


def _dias(s: str) -> str:
    partes = []
    for trozo in s.split(","):
        if "-" in trozo:
            a, b = trozo.split("-", 1)
            if a in DIAS and b in DIAS:
                partes.append(f"{DIAS[a]} a {DIAS[b]}")
                continue
        if trozo not in DIAS:
            raise ValueError(trozo)
        partes.append(DIAS[trozo])
    texto = ", ".join(partes)
    return texto[0].upper() + texto[1:]


def _horas(s: str) -> str:
    if s.strip() == "off":
        return "cerrado"
    franjas = []
    for f in s.split(","):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", f)
        if not m:
            raise ValueError(f)
        h1, m1, h2, m2 = m.groups()
        franjas.append(f"{int(h1)}:{m1}–{int(h2)}:{m2}")
    return " y ".join(franjas)


def legible(oh: str) -> list[str]:
    if not oh:
        return []
    if oh.strip() == "24/7":
        return ["Abierto 24 horas"]
    try:
        lineas = []
        for regla in oh.split(";"):
            regla = regla.strip()
            if not regla:
                continue
            m = re.fullmatch(r"([A-Za-z,\-]+)\s+(.+)", regla)
            if not m:
                raise ValueError(regla)
            lineas.append(f"{_dias(m.group(1))}: {_horas(m.group(2))}")
        return lineas
    except ValueError:
        return [oh]
