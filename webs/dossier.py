"""Dossier A4 de 2 páginas por comercio: capturas de su demo, beneficios, QR y pack con precios. HTML → PDF con Chrome."""
import base64
import io
import subprocess
import tempfile
from pathlib import Path

import qrcode
from PIL import Image
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import PLANTILLAS
from .demos import TEMAS

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def qr_png(url: str) -> bytes:
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    q.add_data(url)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def _b64(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _chrome(*args: str) -> None:
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", *args],
                   check=True, capture_output=True, timeout=120)


def captura(html: Path, ancho: int, alto: int) -> bytes:
    """Captura de la demo local a `ancho`×`alto`. Chrome headless no baja de ~500 px de ventana, así que la demo va en un
    iframe del ancho exacto y luego se recorta."""
    with tempfile.TemporaryDirectory() as d:
        envoltorio = Path(d) / "w.html"
        envoltorio.write_text(f'<!doctype html><body style="margin:0"><iframe src="{html.as_uri()}" '
                              f'style="border:0;width:{ancho}px;height:{alto}px;display:block"></iframe>')
        out = Path(d) / "c.png"
        _chrome(f"--window-size={max(ancho, 600)},{alto}", "--allow-file-access-from-files", "--virtual-time-budget=5000",
                f"--screenshot={out}", envoltorio.as_uri())
        img = Image.open(out).crop((0, 0, ancho, alto))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def html_dossier(c: dict, textos: dict, url: str, cfg: dict, cap_movil: bytes, cap_pc: bytes) -> str:
    env = Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))
    return env.get_template("dossier.html").render(
        c=c, t=textos, url=url, cfg=cfg, tema=TEMAS.get(c["sector"], TEMAS["generica"]),
        qr=_b64(qr_png(url)), movil=_b64(cap_movil), pc=_b64(cap_pc),
    )


def pdf(html: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".html")
    tmp.write_text(html)
    _chrome("--no-pdf-header-footer", "--virtual-time-budget=3000", f"--print-to-pdf={destino}", tmp.as_uri())
    tmp.unlink()
    return destino


def unir(pdfs: list[Path], destino: Path) -> Path:
    """Une PDFs con la herramienta del sistema de macOS (sin dependencias extra)."""
    join = "/System/Library/Automator/Combine PDF Pages.action/Contents/MacOS/join"
    subprocess.run([join, "-o", str(destino), *map(str, pdfs)], check=True, capture_output=True)
    return destino


def paginas(ruta: Path) -> int:
    datos = ruta.read_bytes()
    return datos.count(b"/Type /Page") - datos.count(b"/Type /Pages") or datos.count(b"/Type/Page") - datos.count(b"/Type/Pages")
