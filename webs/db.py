"""Estado local de los comercios trabajados (SQLite en `datos/leads.sqlite`)."""
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .osm import normalizar

ESTADOS = ("nuevo", "demo", "publicado", "dossier", "visitado", "interesado", "no", "cliente", "descartado")

ESQUEMA = """
create table if not exists comercios (
  id integer primary key,
  osm_id text unique,
  nombre text not null,
  nombre_norm text not null,
  sector text not null,
  tipo text,
  direccion text,
  zona text,
  telefono text,
  horario text,
  lat real,
  lon real,
  tags text,
  textos text,
  slug text unique,
  estado text not null default 'nuevo',
  nota text,
  nfc_importado integer not null default 0,
  creado text not null,
  actualizado text not null,
  publicado text
);
create index if not exists comercios_estado on comercios(estado);
"""


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def abrir(ruta: Path) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ruta)
    db.row_factory = sqlite3.Row
    db.executescript(ESQUEMA)
    return db


def slug(nombre: str) -> str:
    """`<nombre-corto>-<6 caracteres aleatorios>`: no se puede adivinar la URL de una demo a partir del nombre."""
    base = "-".join(normalizar(nombre).replace("ñ", "n").split()[:3])[:30] or "comercio"
    return f"{base}-{secrets.token_hex(3)}"


def guardar_candidatos(db: sqlite3.Connection, cands: list[dict]) -> int:
    """Inserta los nuevos (por osm_id o nombre); no pisa los que ya se están trabajando. Devuelve cuántos son nuevos."""
    nuevos = 0
    for c in cands:
        ya = db.execute("select 1 from comercios where osm_id = ? or nombre_norm = ?", (c["osm_id"], c["nombre_norm"])).fetchone()
        if ya:
            continue
        db.execute(
            "insert into comercios (osm_id, nombre, nombre_norm, sector, tipo, direccion, zona, telefono, horario, lat, lon, tags, creado, actualizado)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["osm_id"], c["nombre"], c["nombre_norm"], c["sector"], c["tipo"], c["direccion"], c.get("zona", ""),
             c["telefono"], c["horario"], c["lat"], c["lon"], json.dumps(c["tags"], ensure_ascii=False), ahora(), ahora()),
        )
        nuevos += 1
    db.commit()
    return nuevos


def obtener(db: sqlite3.Connection, cid: int) -> sqlite3.Row:
    r = db.execute("select * from comercios where id = ?", (cid,)).fetchone()
    if not r:
        raise SystemExit(f"No existe el comercio {cid}.")
    return r


def actualizar(db: sqlite3.Connection, cid: int, **campos) -> None:
    if "estado" in campos and campos["estado"] not in ESTADOS:
        raise SystemExit(f"Estado no válido: {campos['estado']} (válidos: {', '.join(ESTADOS)})")
    campos["actualizado"] = ahora()
    sets = ", ".join(f"{k} = ?" for k in campos)
    db.execute(f"update comercios set {sets} where id = ?", (*campos.values(), cid))
    db.commit()


def textos(r: sqlite3.Row) -> dict:
    return json.loads(r["textos"]) if r["textos"] else {}
