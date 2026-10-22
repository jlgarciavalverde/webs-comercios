import json
import re
from pathlib import Path

import httpx
import pytest

from webs import db as D
from webs import demos, horario, llm, nfc, osm, ruta
from webs.config import cargar

FIX = json.loads((Path(__file__).parent / "fixtures" / "overpass.json").read_text())


def test_candidatos_filtra_web_cadenas_y_sin_nombre():
    nombres = [c["nombre"] for c in osm.candidatos(FIX)]
    assert nombres == ["Peluquería Ana", "Taller Hermanos López", "Clínica Dental Sonrisa", "Zapatería Pasos", "Estética Luna"]


def test_candidatos_campos_y_sector():
    cs = {c["nombre"]: c for c in osm.candidatos(FIX)}
    ana = cs["Peluquería Ana"]
    assert ana["sector"] == "belleza" and ana["tipo"] == "peluquería"
    assert ana["direccion"] == "Calle Mayor 3" and ana["telefono"] == "+34 968 000 001"
    assert cs["Taller Hermanos López"]["sector"] == "taller" and cs["Taller Hermanos López"]["telefono"] == "968000004"
    assert cs["Clínica Dental Sonrisa"]["sector"] == "salud"
    assert cs["Estética Luna"]["sector"] == "belleza" and cs["Estética Luna"]["tipo"] == "estética de uñas"
    assert cs["Zapatería Pasos"]["sector"] == "tienda"


def test_normalizar_igual_que_nfc():
    assert osm.normalizar("  Peluquería  Ñoña's ") == "peluqueria nona s"


def test_guardar_candidatos_no_duplica(tmp_path):
    db = D.abrir(tmp_path / "l.sqlite")
    cs = osm.candidatos(FIX)
    assert D.guardar_candidatos(db, cs) == 5
    assert D.guardar_candidatos(db, cs) == 0


def test_slug_no_adivinable():
    a, b = D.slug("Peluquería Ana"), D.slug("Peluquería Ana")
    assert a != b and re.fullmatch(r"peluqueria-ana-[0-9a-f]{6}", a)


def test_horario_legible():
    assert horario.legible("Mo-Fr 09:30-14:00,17:00-20:30; Sa 09:30-14:00") == [
        "Lunes a viernes: 9:30–14:00 y 17:00–20:30", "Sábado: 9:30–14:00"]
    assert horario.legible("raro") == ["raro"]
    assert horario.legible("") == []


@pytest.mark.parametrize("malo", [None, [], {"eslogan": "x"}, {"eslogan": "x", "servicios": ["a"], "sobre": "s", "beneficios": ["a", "b", "c"], "guion": "g"},
                                  {"eslogan": "x", "servicios": ["a", "b", "c"], "sobre": "s", "beneficios": ["Corte por 15 €", "b", "c"], "guion": "g"}])
def test_validar_rechaza_json_invalido_o_con_precios(malo):
    assert llm.validar(malo) is None


def test_redactar_cae_al_respaldo_si_el_llm_falla(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_API_KEY", "x")
    c = osm.candidatos(FIX)[0]
    transporte = httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "no es json"}}]}))
    t = llm.redactar(c, cargar(), cliente=httpx.Client(transport=transporte))
    assert t["origen"] == "base" and "Peluquería Ana" in t["guion"]


def test_redactar_acepta_json_valido(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_API_KEY", "x")
    bueno = {"eslogan": "Tu pelo, en buenas manos", "servicios": ["Corte", "Color", "Peinado"], "sobre": "Somos de barrio.",
             "beneficios": ["Citas online", "Google", "Galería", "Reseñas con NFC"], "guion": "Hola"}
    transporte = httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "```json\n" + json.dumps(bueno) + "\n```"}}]}))
    t = llm.redactar(osm.candidatos(FIX)[0], cargar(), cliente=httpx.Client(transport=transporte))
    assert t["origen"] == "ia" and t["eslogan"] == "Tu pelo, en buenas manos"


def test_demo_marcada_y_no_indexable(tmp_path):
    c = osm.candidatos(FIX)[0] | {"slug": "peluqueria-ana-abc123", "zona": "Centro"}
    demos.construir_sitio([(c, llm.respaldo(c))], tmp_path, "José Luis García")
    html = (tmp_path / "peluqueria-ana-abc123" / "index.html").read_text()
    assert "DEMO" in html and "No es su web oficial" in html
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert "Lunes a viernes: 9:30–14:00 y 17:00–20:30" in html
    assert "wa.me" not in html  # fijo, no móvil: sin WhatsApp
    assert "X-Robots-Tag: noindex" in (tmp_path / "_headers").read_text()
    assert "Disallow: /" in (tmp_path / "robots.txt").read_text()


def test_demo_escapa_html(tmp_path):
    c = osm.candidatos(FIX)[0] | {"slug": "x-000000", "nombre": "<script>alert(1)</script>"}
    demos.generar(c, llm.respaldo(c), tmp_path, "yo")
    assert "<script>alert(1)" not in (tmp_path / "x-000000" / "index.html").read_text()


def test_whatsapp_solo_moviles():
    assert demos._movil("+34 600 00 00 00") == "34600000000"
    assert demos._movil("968 000 001") == ""


def test_ruta_vecino_mas_proximo_y_enlace():
    cs = [{"lat": 0, "lon": 3}, {"lat": 0, "lon": 1}, {"lat": 0, "lon": 2}]
    orden = ruta.ordenar(cs, (0, 0))
    assert [c["lon"] for c in orden] == [1, 2, 3]
    assert "waypoints=" in ruta.enlace_maps(orden)


def test_sql_importar_sin_interpolacion():
    filas = [{"nombre": "O'Hara $$; drop table x", "nombre_norm": "o hara drop table x", "tipo": "bar", "zona": None,
              "direccion": None, "contacto": None, "nota": "n", "lat": 1.0, "lon": 2.0}]
    sql = nfc.sql_importar(filas)
    tag = re.search(r"json_to_recordset\((\$j[0-9a-f]+\$)", sql).group(1)
    cuerpo = sql.split(tag)[1]
    assert json.loads(cuerpo) == filas
    assert "anulado_at is null" in sql and "'webs'" in sql


def test_guion_sin_nombre_inventado():
    d = {"eslogan": "x", "servicios": ["a", "b", "c"], "sobre": "s", "beneficios": ["a", "b", "c"], "guion": "¡Hola Ana! Soy José Luis."}
    assert llm.validar(d)["guion"] == "¡Hola! Soy José Luis."
