import sys, re, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from scraper_base import guardar, log
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

BASE_URL     = "https://www.piala.com.ar/productos/"
SUPERMERCADO = "piala"
OUTPUT_DIR   = Path("output_piala")


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


def parsear_pagina(html):
    soup = BeautifulSoup(html, "lxml")
    productos = []
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    vistos = set()

    for item in soup.select("li.product"):
        nombre_el = item.select_one(".woocommerce-loop-product__title")
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)
        if not nombre or nombre in vistos:
            continue

        precio_el  = item.select_one("span.price, .woocommerce-Price-amount")
        precio_raw = precio_el.get_text(" ", strip=True) if precio_el else ""
        precio     = parse_precio(precio_raw)
        if not precio:
            continue

        link_el  = item.select_one("a")
        url_prod = link_el.get("href", "") if link_el else ""

        img_el = item.select_one("img")
        imagen = ""
        if img_el:
            imagen = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src") or ""

        unidad = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"

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
        log.info(f"  [li.product] {len(productos)} productos")
        return productos

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
        if not precio:
            continue

        unidad = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"

        imagen = ""
        for sib in h3.previous_siblings:
            if hasattr(sib, 'name') and sib.name == "a":
                img = sib.find("img")
                if img:
                    imagen = img.get("src") or img.get("data-src", "")
                break

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
        log.info(f"  [h3 fallback] {len(productos)} productos")

    return productos


def get_next_url(html):
    soup = BeautifulSoup(html, "lxml")
    next_el = soup.select_one("a.next.page-numbers, .woocommerce-pagination a.next")
    return next_el.get("href") if next_el else None


def scrape_all():
    if not PLAYWRIGHT_OK:
        log.error("Playwright no instalado. Correr: pip install playwright && playwright install chromium")
        return []

    todos = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}", lambda r: r.abort())
        page.route("**/google-analytics.com/**", lambda r: r.abort())
        page.route("**/googletagmanager.com/**", lambda r: r.abort())
        page.route("**/facebook.com/**", lambda r: r.abort())

        url = BASE_URL
        pagina = 1

        while url:
            log.info(f"[Piala] Pagina {pagina}: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except PWTimeout:
                try:
                    page.goto(url, wait_until="load", timeout=20000)
                    page.wait_for_timeout(3000)
                except PWTimeout:
                    log.error(f"  FALLO en pagina {pagina}")
                    break

            try:
                page.wait_for_selector("li.product, h3", timeout=8000)
            except PWTimeout:
                pass

            html = page.content()
            prods = parsear_pagina(html)
            log.info(f"  -> {len(prods)} productos")
            todos.extend(prods)

            next_url = get_next_url(html)
            if not next_url or next_url == url:
                break
            url = next_url
            pagina += 1
            time.sleep(0.5)

        browser.close()

    log.info(f"[Piala] Total: {len(todos)} productos")
    return todos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "piala")
    else:
        log.warning("[Piala] Sin productos obtenidos")
