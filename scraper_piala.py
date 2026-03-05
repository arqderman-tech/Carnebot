import sys, re, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from scraper_base import guardar, log
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
import urllib.request, ssl

BASE_URL     = "https://www.piala.com.ar/productos/"
SUPERMERCADO = "piala"
OUTPUT_DIR   = Path("output_piala")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}


def get_html(url, retries=4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            log.warning(f"  intento {i+1}/{retries}: {e}")
            time.sleep(3 * (i + 1))
    return None


def parse_precio(texto):
    if not texto:
        return None
    m = re.search(r'\$\s*([\d.,]+)', texto)
    if not m:
        return None
    raw = m.group(1)
    if re.match(r'^\d+\.\d{1,2}$', raw):
        return float(raw)
    return float(raw.replace(".", "").replace(",", "."))


def parsear_pagina(html, url_pagina):
    soup = BeautifulSoup(html, "lxml")
    productos = []
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    vistos = set()

    items = soup.select("li.product")
    for item in items:
        nombre_el = item.select_one(
            "h2.woocommerce-loop-product__title,"
            "h3.woocommerce-loop-product__title,"
            ".woocommerce-loop-product__title"
        )
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)
        if not nombre or nombre in vistos:
            continue

        precio_el  = item.select_one("span.price, .woocommerce-Price-amount")
        precio_raw = precio_el.get_text(" ", strip=True) if precio_el else ""
        precio     = parse_precio(precio_raw)

        link_el  = item.select_one("a")
        url_prod = link_el.get("href", "") if link_el else ""

        img_el = item.select_one("img")
        imagen = ""
        if img_el:
            imagen = (img_el.get("src") or
                      img_el.get("data-src") or
                      img_el.get("data-lazy-src") or "")

        unidad = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"

        if precio:
            vistos.add(nombre)
            productos.append({
                "supermercado": SUPERMERCADO,
                "codigo":       "",
                "nombre":       nombre,
                "categoria":    "Carnes",
                "precio_actual": precio,
                "unidad":       unidad,
                "imagen":       imagen,
                "url":          url_prod,
                "fecha":        fecha,
            })

    if productos:
        log.info(f"  [Estrategia 1 - li.product] {len(productos)} productos")
        return productos, get_next_url(soup)

    for h3 in soup.find_all("h3"):
        link = h3.find("a")
        if not link:
            continue
        nombre = link.get_text(strip=True)
        if not nombre or nombre in vistos:
            continue
        url_prod = link.get("href", "")

        precio_raw = ""
        for sib in h3.next_siblings:
            if hasattr(sib, 'name'):
                if sib.name == "a":
                    precio_raw = sib.get_text(strip=True)
                    break
                elif sib.name == "h3":
                    break

        precio = parse_precio(precio_raw)
        unidad = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"

        imagen = ""
        for sib in h3.previous_siblings:
            if hasattr(sib, 'name') and sib.name == "a":
                img = sib.find("img")
                if img:
                    imagen = img.get("src") or img.get("data-src", "")
                break

        if precio:
            vistos.add(nombre)
            productos.append({
                "supermercado": SUPERMERCADO,
                "codigo":       "",
                "nombre":       nombre,
                "categoria":    "Carnes",
                "precio_actual": precio,
                "unidad":       unidad,
                "imagen":       imagen,
                "url":          url_prod,
                "fecha":        fecha,
            })

    if productos:
        log.info(f"  [Estrategia 2 - h3] {len(productos)} productos")

    return productos, get_next_url(soup)


def get_next_url(soup):
    next_el = soup.select_one(
        "a.next.page-numbers,"
        ".woocommerce-pagination a.next,"
        "a[aria-label='Next']"
    )
    return next_el.get("href") if next_el else None


def scrape_all():
    todos = []
    url = BASE_URL
    pagina = 1

    while url:
        log.info(f"[Piala] Pagina {pagina}: {url}")
        html = get_html(url)
        if not html:
            log.error(f"  FALLO descargando pagina {pagina}")
            break

        prods, next_url = parsear_pagina(html, url)
        log.info(f"  -> {len(prods)} productos")
        todos.extend(prods)

        if not next_url or next_url == url:
            break
        url = next_url
        pagina += 1
        time.sleep(1)

    log.info(f"[Piala] Total: {len(todos)} productos")
    return todos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "piala")
    else:
        log.warning("[Piala] Sin productos obtenidos")
