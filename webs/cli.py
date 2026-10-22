"""CLI `webs`: buscar comercios sin web, preparar sus demos y dossiers, planificar visitas y pasarlos al panel NFC."""
import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from . import db as D
from . import demos, dossier, llm, nfc, osm, ruta
from .config import DATOS, SALIDA, cargar

SITIO = SALIDA / "sitio"
DOSSIERS = SALIDA / "dossiers"
ACTIVOS = ("demo", "publicado", "dossier", "visitado", "interesado", "cliente")


def _db():
    return D.abrir(DATOS / "leads.sqlite")


def _dict(r) -> dict:
    d = dict(r)
    d["tags"] = json.loads(d["tags"]) if d.get("tags") else {}
    return d


def _url(cfg: dict, c: dict) -> str:
    return f"https://{cfg['demos']['dominio']}/{c['slug']}/"


def _ids(db, ids: list[int], estado: str | None = None) -> list[dict]:
    if ids:
        return [_dict(D.obtener(db, i)) for i in ids]
    if estado:
        return [_dict(r) for r in db.execute("select * from comercios where estado = ? order by id", (estado,))]
    raise SystemExit("Indica ids o usa la opción para tomarlos por estado.")


def _puntuar(c: dict, centro: tuple[float, float]) -> float:
    """Más arriba: con teléfono y dirección (más fáciles de visitar) y cerca del centro elegido."""
    p = 0.0
    p += 2 if c.get("telefono") else 0
    p += 1 if c.get("direccion") else 0
    p += 1 if c.get("horario") else 0
    p -= osm.distancia_km(centro, (c["lat"], c["lon"])) / 2
    return p


# ── pasos ─────────────────────────────────────────────────────────────────────

def buscar(a, cfg) -> list[int]:
    print("Consultando OpenStreetMap (puede tardar si Overpass está saturado)…")
    bbox = tuple(float(x) for x in a.bbox.split(",")) if a.bbox else None
    datos = osm.descargar(osm.consulta(a.tipo or "todos", area=a.area, bbox=bbox))
    cands = osm.candidatos(datos)
    ya_nfc = nfc.nombres_existentes()
    cands = [c for c in cands if c["nombre_norm"] not in ya_nfc]
    db = _db()
    nuevos = D.guardar_candidatos(db, cands)
    total = db.execute("select count(*) from comercios").fetchone()[0]
    print(f"{len(datos.get('elements', []))} comercios en OSM → {len(cands)} sin web, sin cadenas y fuera del panel NFC "
          f"→ {nuevos} nuevos guardados ({total} en total).")
    return []


def lista(a, cfg):
    db = _db()
    q = "select id, nombre, sector, tipo, zona, telefono, estado, slug from comercios where 1=1"
    p: list = []
    if a.estado:
        q += " and estado = ?"
        p.append(a.estado)
    if a.tipo:
        q += " and sector = ?"
        p.append(osm.ALIAS.get(a.tipo, a.tipo))
    for r in db.execute(q + " order by id limit ?", (*p, a.n)):
        url = f"  {_url(cfg, dict(r))}" if r["slug"] else ""
        print(f"#{r['id']:<5} {r['estado']:<10} {r['sector']:<11} {r['nombre'][:38]:<38} {r['zona'] or '':<16} {r['telefono'] or ''}{url}")


def elegir(a, cfg) -> list[int]:
    """Los N mejores comercios nuevos de un sector, cerca de un punto."""
    db = _db()
    centro = tuple(float(x) for x in a.desde.split(",")) if a.desde else (cfg["zona"]["lat"], cfg["zona"]["lon"])
    q = "select * from comercios where estado = 'nuevo'"
    p: list = []
    if a.tipo:
        q += " and sector = ?"
        p.append(osm.ALIAS.get(a.tipo, a.tipo))
    cands = [_dict(r) for r in db.execute(q, p)]
    if a.radio:
        cands = [c for c in cands if osm.distancia_km(centro, (c["lat"], c["lon"])) <= a.radio]
    cands.sort(key=lambda c: _puntuar(c, centro), reverse=True)
    return [c["id"] for c in cands[: a.n]]


def enriquecer(db, c: dict, cliente: httpx.Client) -> dict:
    if c.get("direccion") and c.get("zona"):
        return c
    extra = osm.nominatim_inverso(c["lat"], c["lon"], cliente)
    cambios = {k: v for k, v in extra.items() if v and not c.get(k)}
    if cambios:
        D.actualizar(db, c["id"], **cambios)
        c.update(cambios)
    return c


def redactar(ids: list[int], cfg) -> None:
    db = _db()
    for c in _ids(db, ids):
        t = llm.redactar(c, cfg)
        D.actualizar(db, c["id"], textos=json.dumps(t, ensure_ascii=False))
        print(f"#{c['id']} {c['nombre']}: textos ({t['origen']}) · «{t['eslogan']}»")


def demo(ids: list[int], cfg) -> None:
    db = _db()
    autor = cfg["autor"]["nombre"]
    with httpx.Client(timeout=30, headers={"User-Agent": osm.UA}) as cl:
        for c in _ids(db, ids):
            c = enriquecer(db, c, cl)
            if not c.get("textos"):
                c["textos"] = json.dumps(llm.redactar(c, cfg), ensure_ascii=False)
                D.actualizar(db, c["id"], textos=c["textos"])
            if not c.get("slug"):
                c["slug"] = D.slug(c["nombre"])
                D.actualizar(db, c["id"], slug=c["slug"])
            demos.generar(c, json.loads(c["textos"]), SITIO, autor)
            if c["estado"] == "nuevo":
                D.actualizar(db, c["id"], estado="demo")
            print(f"#{c['id']} {c['nombre']}: demo en {SITIO / c['slug'] / 'index.html'}")


def _activos(db) -> list[dict]:
    marcas = ",".join("?" * len(ACTIVOS))
    return [_dict(r) for r in db.execute(f"select * from comercios where slug is not null and estado in ({marcas})", ACTIVOS)]


def publicar(cfg, desplegar: bool = True) -> None:
    db = _db()
    act = _activos(db)
    demos.construir_sitio([(c, json.loads(c["textos"])) for c in act], SITIO, cfg["autor"]["nombre"])
    print(f"Sitio con {len(act)} demos en {SITIO}")
    if not desplegar:
        return
    from .publicar import desplegar as subir
    subir(SITIO, cfg["demos"]["proyecto_pages"])
    for c in act:
        if c["estado"] == "demo":
            D.actualizar(db, c["id"], estado="publicado", publicado=D.ahora())
        elif not c["publicado"]:
            D.actualizar(db, c["id"], publicado=D.ahora())
    print(f"Publicado: https://{cfg['demos']['dominio']}/<slug>/")


def hacer_dossier(ids: list[int], cfg) -> list[Path]:
    db = _db()
    out = []
    for c in _ids(db, ids):
        if not c.get("slug"):
            raise SystemExit(f"#{c['id']} no tiene demo: ejecuta antes `webs demo {c['id']}`.")
        html = SITIO / c["slug"] / "index.html"
        if not html.exists():
            demos.generar(c, json.loads(c["textos"]), SITIO, cfg["autor"]["nombre"])
        movil = dossier.captura(html, 390, 844)
        pc = dossier.captura(html, 1366, 860)
        destino = DOSSIERS / f"{c['id']:04d}-{c['slug']}.pdf"
        dossier.pdf(dossier.html_dossier(c, json.loads(c["textos"]), _url(cfg, c), cfg, movil, pc), destino)
        if c["estado"] in ("demo", "publicado"):
            D.actualizar(db, c["id"], estado="dossier")
        print(f"#{c['id']} {c['nombre']}: {destino} ({dossier.paginas(destino)} págs.)")
        out.append(destino)
    return out


def hacer_ruta(ids: list[int], cfg, inicio: tuple[float, float]) -> Path:
    db = _db()
    cs = _ids(db, ids)
    for c in cs:
        c["guion"] = json.loads(c["textos"]).get("guion", "") if c.get("textos") else ""
    orden = ruta.ordenar(cs, inicio)
    fecha = datetime.now().strftime("%Y-%m-%d")
    carpeta = SALIDA / "rutas" / fecha
    carpeta.mkdir(parents=True, exist_ok=True)
    hoja = dossier.pdf(ruta.hoja(orden, f"Ruta de visitas · {fecha}"), carpeta / "hoja-de-ruta.pdf")
    pdfs = [DOSSIERS / f"{c['id']:04d}-{c['slug']}.pdf" for c in orden]
    faltan = [p for p in pdfs if not p.exists()]
    if faltan:
        print("Aviso: faltan dossiers de", ", ".join(p.name for p in faltan))
    pdfs = [p for p in pdfs if p.exists()]
    if pdfs:
        dossier.unir(pdfs, carpeta / "dossiers-para-imprimir.pdf")
    print(f"Ruta: {hoja}\nImprimir: {carpeta / 'dossiers-para-imprimir.pdf'}\nGoogle Maps: {ruta.enlace_maps(orden)}")
    return carpeta


def anotar(a, cfg) -> None:
    db = _db()
    c = D.obtener(db, a.id)
    nota = " · ".join(x for x in (c["nota"], " ".join(a.nota)) if x) if a.nota else c["nota"]
    D.actualizar(db, a.id, estado=a.estado, nota=nota)
    print(f"#{a.id} {c['nombre']} → {a.estado}")


def importar_nfc(cfg) -> None:
    db = _db()
    filas_db = [_dict(r) for r in db.execute(
        "select * from comercios where estado in ('visitado','interesado','cliente') and nfc_importado = 0")]
    filas = [nfc.fila(c, _url(cfg, c)) for c in filas_db]
    creados = nfc.importar(filas)
    for c in filas_db:
        D.actualizar(db, c["id"], nfc_importado=1)
    print(f"{len(creados)} comercios nuevos en el panel NFC ({len(filas) - len(creados)} ya estaban).")
    for l in creados:
        print("  ", l)


def limpiar(a, cfg) -> None:
    """Retira las demos caducadas de comercios que no están interesados ni son clientes."""
    db = _db()
    limite = (datetime.now(timezone.utc) - timedelta(days=a.dias if a.dias is not None else cfg["demos"]["caducidad_dias"])).isoformat()
    rs = db.execute("select id, nombre, slug from comercios where slug is not null and estado not in ('interesado','cliente')"
                    " and coalesce(publicado, creado) <= ?", (limite,)).fetchall()
    for r in rs:
        print(f"{'[prueba] ' if a.dry_run else ''}retiro demo #{r['id']} {r['nombre']}")
        if not a.dry_run:
            shutil.rmtree(SITIO / r["slug"], ignore_errors=True)
            D.actualizar(db, r["id"], slug=None, estado="descartado")
    if rs and not a.dry_run:
        publicar(cfg)


def borrar(a, cfg) -> None:
    """Derecho de supresión: borra el comercio, su demo y su dossier."""
    db = _db()
    c = D.obtener(db, a.id)
    if c["slug"]:
        shutil.rmtree(SITIO / c["slug"], ignore_errors=True)
        for p in DOSSIERS.glob(f"{a.id:04d}-*.pdf"):
            p.unlink()
    db.execute("delete from comercios where id = ?", (a.id,))
    db.commit()
    print(f"Borrado #{a.id} {c['nombre']}. Ejecuta `webs publicar` para retirarlo también de internet.")


def lote(a, cfg) -> None:
    db = _db()
    if not db.execute("select 1 from comercios limit 1").fetchone():
        buscar(argparse.Namespace(tipo=None, area=a.area, bbox=None), cfg)
    ids = elegir(a, cfg)
    if not ids:
        raise SystemExit("No quedan comercios nuevos con esos filtros (prueba otro --tipo o `webs buscar`).")
    print(f"Elegidos: {ids}")
    redactar(ids, cfg)
    demo(ids, cfg)
    publicar(cfg, desplegar=not a.sin_publicar)
    hacer_dossier(ids, cfg)
    inicio = tuple(float(x) for x in a.desde.split(",")) if a.desde else (cfg["zona"]["lat"], cfg["zona"]["lon"])
    hacer_ruta(ids, cfg, inicio)
    print("\nRevisa las demos y los dossiers antes de imprimir. Tras cada visita: `webs anotar <id> <estado> [nota]`.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="webs", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("buscar", help="descarga comercios sin web de OpenStreetMap")
    s.add_argument("--tipo", help="restaurante, belleza, salud, taller, tienda (o peluqueria, bar, dentista…)")
    s.add_argument("--area", default="Murcia")
    s.add_argument("--bbox", help="sur,oeste,norte,este en lugar del municipio")

    s = sub.add_parser("lista", help="lista los comercios guardados")
    s.add_argument("--estado", choices=D.ESTADOS)
    s.add_argument("--tipo")
    s.add_argument("--n", type=int, default=50)

    for nombre, ayuda in (("redactar", "textos con IA"), ("demo", "genera la demo"), ("dossier", "PDF para llevar")):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("ids", type=int, nargs="+")

    sub.add_parser("publicar", help="sube todas las demos activas a Cloudflare Pages")

    s = sub.add_parser("ruta", help="hoja de ruta + PDF para imprimir de los comercios dados")
    s.add_argument("ids", type=int, nargs="+")
    s.add_argument("--desde", help="lat,lon de salida")

    s = sub.add_parser("anotar", help="resultado de una visita")
    s.add_argument("id", type=int)
    s.add_argument("estado", choices=D.ESTADOS)
    s.add_argument("nota", nargs="*")

    sub.add_parser("importar-nfc", help="pasa los visitados al panel NFC")

    s = sub.add_parser("limpiar", help="retira demos caducadas")
    s.add_argument("--dias", type=int)
    s.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("borrar", help="borra un comercio y su demo (derecho de supresión)")
    s.add_argument("id", type=int)

    s = sub.add_parser("lote", help="todo seguido: elegir, redactar, demo, publicar, dossier y ruta")
    s.add_argument("--tipo")
    s.add_argument("--n", type=int, default=10)
    s.add_argument("--desde", help="lat,lon desde donde empiezas la ruta")
    s.add_argument("--radio", type=float, default=2.0, help="km alrededor de --desde")
    s.add_argument("--area", default="Murcia")
    s.add_argument("--sin-publicar", action="store_true")

    a = p.parse_args(argv)
    cfg = cargar()
    match a.cmd:
        case "buscar": buscar(a, cfg)
        case "lista": lista(a, cfg)
        case "redactar": redactar(a.ids, cfg)
        case "demo": demo(a.ids, cfg)
        case "dossier": hacer_dossier(a.ids, cfg)
        case "publicar": publicar(cfg)
        case "ruta":
            ini = tuple(float(x) for x in a.desde.split(",")) if a.desde else (cfg["zona"]["lat"], cfg["zona"]["lon"])
            hacer_ruta(a.ids, cfg, ini)
        case "anotar": anotar(a, cfg)
        case "importar-nfc": importar_nfc(cfg)
        case "limpiar": limpiar(a, cfg)
        case "borrar": borrar(a, cfg)
        case "lote": lote(a, cfg)


if __name__ == "__main__":
    main(sys.argv[1:])
