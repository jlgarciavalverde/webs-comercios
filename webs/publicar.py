"""Publicación del sitio de demos en Cloudflare Pages con wrangler (direct upload)."""
import shutil
import subprocess
from pathlib import Path


def desplegar(sitio: Path, proyecto: str) -> str:
    if not shutil.which("npx"):
        raise SystemExit("Falta npx (Node.js) para usar wrangler.")
    r = subprocess.run(
        ["npx", "--yes", "wrangler@4", "pages", "deploy", str(sitio), "--project-name", proyecto, "--branch", "main", "--commit-dirty=true"],
        capture_output=True, text=True,
    )
    salida = r.stdout + r.stderr
    if r.returncode != 0:
        if "login" in salida.lower() or "authentication" in salida.lower():
            raise SystemExit("wrangler no tiene sesión: ejecuta una vez `npx wrangler login` y vuelve a publicar.")
        raise SystemExit(f"Falló el despliegue:\n{salida[-2000:]}")
    return salida
