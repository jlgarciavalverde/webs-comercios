"""Alta de comercios visitados en el panel NFC (nfc-bot) por SQL en el VPS.

Imita `crearComercio` de nfc-bot (packages/core/src/servicios/comercios.ts): no duplica por `nombre_norm` entre los
comercios vivos y registra la operación (origen «webs») para que salga en la actividad del panel y se pueda deshacer.
Los datos viajan como JSON dentro de un literal con etiqueta aleatoria: no hay interpolación de SQL.
"""
import json
import secrets
import subprocess

VPS = "joseluis@192.168.18.7"


def sql_importar(filas: list[dict]) -> str:
    datos = json.dumps(filas, ensure_ascii=False)
    tag = "j" + secrets.token_hex(6)
    while f"${tag}$" in datos:
        tag = "j" + secrets.token_hex(6)
    return f"""
with d as (
  select * from json_to_recordset(${tag}${datos}${tag}$::json)
    as x(nombre text, nombre_norm text, tipo text, zona text, direccion text, contacto text, nota text, lat real, lon real)
), autor as (
  select id from socios where rol = 'admin' and activo order by id limit 1
), ins as (
  insert into comercios (nombre, nombre_norm, tipo, zona, direccion, contacto, nota, lat, lon, creado_por)
  select d.nombre, d.nombre_norm, d.tipo, d.zona, d.direccion, d.contacto, d.nota, d.lat, d.lon, (select id from autor)
  from d
  where not exists (select 1 from comercios c where c.nombre_norm = d.nombre_norm and c.anulado_at is null)
  returning id, nombre
), op as (
  insert into operaciones (socio_id, tipo, resumen, deshacer, origen)
  select (select id from autor), 'comercio', 'Nuevo comercio ' || ins.nombre, jsonb_build_object('t', 'comercio', 'comercioId', ins.id), 'webs'
  from ins
)
select id || '|' || nombre from ins;
"""


def fila(c: dict, url: str) -> dict:
    return {
        "nombre": c["nombre"][:120],
        "nombre_norm": c["nombre_norm"],
        "tipo": c["tipo"],
        "zona": c.get("zona") or None,
        "direccion": c.get("direccion") or None,
        "contacto": c.get("telefono") or None,
        "nota": f"Demo web: {url}" + (f" · {c['nota']}" if c.get("nota") else ""),
        "lat": c["lat"],
        "lon": c["lon"],
    }


def nombres_existentes(vps: str = VPS) -> set[str]:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", vps,
                        "docker exec nfc-db psql -U nfc -d nfc -Atc 'select nombre_norm from comercios where anulado_at is null'"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return set()
    return {l.strip() for l in r.stdout.splitlines() if l.strip()}


def importar(filas: list[dict], vps: str = VPS) -> list[str]:
    if not filas:
        return []
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", vps,
                        "docker exec -i nfc-db psql -U nfc -d nfc -v ON_ERROR_STOP=1 -At -f -"],
                       input=sql_importar(filas), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"No se pudo importar en el panel NFC:\n{r.stderr[-1500:]}\n"
                         "¿Hiciste `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` en una terminal?")
    return [l for l in r.stdout.splitlines() if "|" in l]
