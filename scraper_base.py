"""
scraper_base.py – Motor genérico de scraping para carnicerías
Soporta: Piala (WooCommerce) y El Chañar (API custom)
Requiere: requests, beautifulsoup4, lxml
"""

import json, csv, time, logging, re
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path
from datetime import datetime
import ssl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*",
    "Accept-Language": "es-AR,es;q=0.9",
}

CAMPOS = [
    "supermercado", "codigo", "nombre", "categoria",
    "precio_actual", "unidad", "imagen", "url", "fecha",
]


def get_html(url, retries=4, espera=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as r:
                return r.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError) as e:
            log.warning(f"  intento {i+1}/{retries}: {e}  url={url[:80]}")
            time.sleep(espera * (i + 1))
    log.error(f"  FALLO DEFINITIVO: {url[:80]}")
    return None


def get_json_url(url, retries=4, espera=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={**HEADERS, "Accept": "application/json"})
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as r:
                return json.loads(r.read())
        except (HTTPError, URLError, json.JSONDecodeError) as e:
            log.warning(f"  intento {i+1}/{retries}: {e}  url={url[:80]}")
            time.sleep(espera * (i + 1))
    return None


def _parse_precio(texto):
    """Convierte '$16.400,00' → 16400.0"""
    if not texto:
        return None
    clean = re.sub(r"[^\d,.]", "", str(texto))
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def guardar(todos, output_dir: Path, nombre_archivo: str):
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    ruta_csv  = output_dir / f"{nombre_archivo}_{ts}.csv"
    ruta_json = output_dir / f"{nombre_archivo}_{ts}.json"

    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(todos)

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

    log.info(f"OK CSV  → {ruta_csv}  ({len(todos)} prods)")
    log.info(f"OK JSON → {ruta_json}")
    return ruta_csv
