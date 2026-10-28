# Requisitos

## Requisitos funcionales

| ID | Requisito |
|---|---|
| RF-01 | `buscar` descarga de OpenStreetMap los comercios de Murcia sin web y que no son de cadenas. |
| RF-02 | `lote` elige N comercios de un sector (opcionalmente cerca de un punto y en un radio) y hace todo seguido: textos, demo, publicación, dossier y ruta. |
| RF-03 | Cada demo se adapta al sector con colores, icono, llamadas a la acción, horario y botón de llamar o de WhatsApp si el número es un móvil. |
| RF-04 | El dossier es un PDF A4 con capturas de la demo, un QR que lleva a ella y la oferta de web más placa NFC. |
| RF-05 | La hoja de ruta ordena las visitas por cercanía e incluye un guion y un QR de Google Maps. |
| RF-06 | `anotar` guarda el resultado de cada visita con una nota. |
| RF-07 | `importar-nfc` pasa los visitados, interesados y clientes al panel NFC sin duplicarlos. |
| RF-08 | `limpiar` retira las demos de más de 30 días de quien no está interesado. |
| RF-09 | `borrar` elimina un comercio y su demo (derecho de supresión). |

## Requisitos no funcionales

| ID | Categoría | Requisito |
|---|---|---|
| RNF-01 | Legal | No se envía ninguna comunicación comercial automática (LSSI). |
| RNF-02 | Privacidad | Solo se usan datos públicos de OSM. Las URL de las demos no se pueden adivinar y las demos no se indexan. |
| RNF-03 | Seguridad | Los textos generados se escapan en la plantilla (sin XSS). Está probado en los tests. |
| RNF-04 | Fiabilidad | Overpass con reintentos y servidores espejo. La IA tiene textos de respaldo. |
| RNF-05 | Coste | Sin servicios de pago: OSM, IA local y Cloudflare Pages gratis. |
| RNF-06 | Configuración | Precios, nombre y teléfono del dossier en `config.toml` (no se versiona). |
