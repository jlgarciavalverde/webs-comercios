"""Comercios de OpenStreetMap (Overpass API): consulta, limpieza y clasificación por sector."""
import math
import re
import time
import unicodedata

import httpx

ESPEJOS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = "webs-comercios/0.1 (prospeccion local; github.com/jlgarciavalverde)"

# Si tiene cualquiera de estas etiquetas, ya tiene presencia web propia: no es candidato.
ETIQUETAS_WEB = ("website", "contact:website", "url", "facebook", "contact:facebook", "instagram", "contact:instagram")
# Cadenas y franquicias: deciden su web en la central.
ETIQUETAS_CADENA = ("brand", "brand:wikidata", "operator:wikidata")
EXCLUIR_TIPOS = {"supermarket", "convenience", "pharmacy", "tobacco", "lottery", "fuel", "vending_machine", "kiosk", "chemist"}

FILTROS = {
    "todos": [
        '["shop"]["name"]',
        '["amenity"~"^(restaurant|cafe|bar|fast_food|ice_cream|dentist|clinic|doctors|veterinary)$"]["name"]',
        '["craft"]["name"]',
        '["beauty"]["name"]',
        '["leisure"="fitness_centre"]["name"]',
        '["office"~"^(estate_agent|lawyer|accountant|insurance)$"]["name"]',
        '["healthcare"]["name"]',
    ],
    "restaurante": ['["amenity"~"^(restaurant|cafe|bar|fast_food|ice_cream)$"]["name"]'],
    "belleza": ['["shop"~"^(hairdresser|beauty|cosmetics|massage|tattoo)$"]["name"]', '["beauty"]["name"]'],
    "salud": [
        '["amenity"~"^(dentist|clinic|doctors|veterinary)$"]["name"]',
        '["healthcare"]["name"]',
        '["shop"="optician"]["name"]',
        '["leisure"="fitness_centre"]["name"]',
    ],
    "taller": ['["shop"~"^(car_repair|car|bicycle|motorcycle|tyres|car_parts)$"]["name"]', '["craft"]["name"]'],
    "tienda": ['["shop"]["name"]'],
}
# Alias en castellano para --tipo.
ALIAS = {
    "peluqueria": "belleza", "estetica": "belleza", "bar": "restaurante", "cafeteria": "restaurante",
    "clinica": "salud", "dentista": "salud", "fisio": "salud", "veterinario": "salud", "gimnasio": "salud",
    "mecanico": "taller", "bicis": "taller",
}

TIPOS_ES = {
    "hairdresser": "peluquería", "beauty": "centro de estética", "nails": "estética de uñas", "cosmetics": "perfumería",
    "massage": "masajes", "tattoo": "estudio de tatuajes", "restaurant": "restaurante", "cafe": "cafetería", "bar": "bar",
    "fast_food": "comida rápida", "ice_cream": "heladería", "dentist": "clínica dental", "clinic": "clínica",
    "doctors": "consulta médica", "veterinary": "clínica veterinaria", "optician": "óptica", "fitness_centre": "gimnasio",
    "physiotherapist": "fisioterapia", "car_repair": "taller mecánico", "car": "concesionario", "bicycle": "tienda de bicis",
    "motorcycle": "motos", "tyres": "neumáticos", "car_parts": "recambios", "clothes": "tienda de ropa",
    "shoes": "zapatería", "bakery": "panadería", "pastry": "pastelería", "confectionery": "confitería",
    "butcher": "carnicería", "greengrocer": "frutería", "jewelry": "joyería", "florist": "floristería",
    "furniture": "tienda de muebles", "electronics": "tienda de electrónica", "hardware": "ferretería",
    "stationery": "papelería", "books": "librería", "gift": "tienda de regalos", "pet": "tienda de mascotas",
    "estate_agent": "inmobiliaria", "lawyer": "despacho de abogados", "accountant": "asesoría",
    "insurance": "seguros", "carpenter": "carpintería", "electrician": "electricista", "plumber": "fontanería",
}


def normalizar(s: str) -> str:
    """Igual que `normalizar` de nfc-bot (packages/core/src/texto.ts), para cruzar nombres con el panel NFC."""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not (0x300 <= ord(c) <= 0x36F))
    return re.sub(r"[^a-z0-9ñ]+", " ", s.lower()).strip()


def consulta(sector: str = "todos", area: str = "Murcia", bbox: tuple[float, float, float, float] | None = None) -> str:
    filtros = FILTROS[ALIAS.get(sector, sector)]
    if bbox:
        b = ",".join(str(x) for x in bbox)
        partes = "".join(f"nwr{f}({b});" for f in filtros)
        return f"[out:json][timeout:120];({partes});out center tags;"
    partes = "".join(f"nwr(area.a){f};" for f in filtros)
    return f'[out:json][timeout:120];area["name"="{area}"]["admin_level"="8"]->.a;({partes});out center tags;'


def descargar(q: str, intentos: int = 6, espera: float = 15, cliente: httpx.Client | None = None) -> dict:
    """Overpass se satura a menudo (502/429): reintenta rotando espejos con espera creciente."""
    c = cliente or httpx.Client(timeout=200, headers={"User-Agent": UA})
    ultimo = ""
    for i in range(intentos):
        url = ESPEJOS[i % len(ESPEJOS)]
        try:
            r = c.post(url, data={"data": q})
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return r.json()
            ultimo = f"{url}: HTTP {r.status_code}"
        except httpx.HTTPError as e:
            ultimo = f"{url}: {e}"
        if i < intentos - 1:
            time.sleep(espera * (i + 1))
    raise RuntimeError(f"Overpass no responde ({ultimo}). Prueba en unos minutos.")


def tipo_osm(t: dict) -> str:
    for k in ("shop", "amenity", "craft", "beauty", "healthcare", "office", "leisure"):
        if t.get(k):
            v = t[k]
            return "nails" if k == "beauty" and v == "nails" else ("beauty" if k == "beauty" else v)
    return "otro"


def sector(t: dict) -> str:
    tipo = tipo_osm(t)
    if t.get("amenity") in {"restaurant", "cafe", "bar", "fast_food", "ice_cream"}:
        return "restaurante"
    if t.get("beauty") or tipo in {"hairdresser", "beauty", "cosmetics", "massage", "tattoo", "nails"}:
        return "belleza"
    if t.get("healthcare") or tipo in {"dentist", "clinic", "doctors", "veterinary", "optician", "fitness_centre"}:
        return "salud"
    if t.get("craft") or tipo in {"car_repair", "car", "bicycle", "motorcycle", "tyres", "car_parts"}:
        return "taller"
    if t.get("shop"):
        return "tienda"
    return "generica"


def direccion(t: dict) -> str:
    calle = t.get("addr:street", "")
    num = t.get("addr:housenumber", "")
    cp = t.get("addr:postcode", "")
    ciudad = t.get("addr:city", "")
    linea = f"{calle} {num}".strip()
    resto = " ".join(x for x in (cp, ciudad) if x)
    return ", ".join(x for x in (linea, resto) if x)


def telefono(t: dict) -> str:
    tel = t.get("phone") or t.get("contact:phone") or t.get("contact:mobile") or t.get("mobile") or ""
    return tel.split(";")[0].strip()


def tiene_web(t: dict) -> bool:
    return any(t.get(k) for k in ETIQUETAS_WEB)


def es_cadena(t: dict) -> bool:
    return any(t.get(k) for k in ETIQUETAS_CADENA)


def candidatos(datos: dict) -> list[dict]:
    """Elementos de Overpass → comercios sin web, sin cadenas y con nombre, sin repetir."""
    vistos: set[str] = set()
    out = []
    for e in datos.get("elements", []):
        t = e.get("tags", {})
        nombre = (t.get("name") or "").strip()
        if not nombre or tiene_web(t) or es_cadena(t) or tipo_osm(t) in EXCLUIR_TIPOS:
            continue
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        norm = normalizar(nombre)
        if norm in vistos or lat is None:
            continue
        vistos.add(norm)
        out.append({
            "osm_id": f"{e['type']}/{e['id']}",
            "nombre": nombre,
            "nombre_norm": norm,
            "sector": sector(t),
            "tipo": TIPOS_ES.get(tipo_osm(t), tipo_osm(t).replace("_", " ")),
            "direccion": direccion(t),
            "telefono": telefono(t),
            "horario": t.get("opening_hours", ""),
            "lat": lat,
            "lon": lon,
            "tags": t,
        })
    return out


def distancia_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def nominatim_inverso(lat: float, lon: float, cliente: httpx.Client) -> dict:
    """Dirección y barrio. Nominatim exige como mucho 1 petición por segundo."""
    r = cliente.get(
        "https://nominatim.openstreetmap.org/reverse",
        params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "accept-language": "es"},
    )
    time.sleep(1.1)
    if r.status_code != 200:
        return {}
    a = r.json().get("address", {})
    calle = " ".join(x for x in (a.get("road", ""), a.get("house_number", "")) if x)
    return {
        "direccion": ", ".join(x for x in (calle, " ".join(x for x in (a.get("postcode", ""), a.get("city") or a.get("town") or a.get("village") or "") if x)) if x),
        "zona": a.get("suburb") or a.get("quarter") or a.get("neighbourhood") or a.get("village") or a.get("town") or "",
    }
