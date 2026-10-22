"""Configuración: `config.toml` en la raíz del proyecto, con valores por defecto de `config.toml.example`."""
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDA = RAIZ / "salida"
PLANTILLAS = RAIZ / "plantillas"


def _mezclar(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _mezclar(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def cargar(ruta: Path | None = None) -> dict:
    base = tomllib.loads((RAIZ / "config.toml.example").read_text())
    ruta = ruta or RAIZ / "config.toml"
    return _mezclar(base, tomllib.loads(ruta.read_text())) if ruta.exists() else base
