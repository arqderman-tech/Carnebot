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

# ─────────────────────────────────────────────
# DIAGNÓSTICO DEL SITIO
#
# El sitio usa JetEngine + JetSmartFilters + Elementor.
# Los productos están en div.jet-listing-grid__item (NO en li.product).
#
# PROBLEMA DE PAGINACIÓN:
#   La paginación JetSmartFilters solo renderiza botones hasta el nro 4
#   en el HTML inicial. Los botones 5,6,7 aparecen recién cuando navegás
#   a páginas avanzadas. Por eso get_total_pages() detectaba 4 y el loop
#   nunca llegaba a las últimas páginas.
#
# SOLUCIÓN: usar el botón "→" (next, data-value="next") en loop
#   hasta que desaparezca (última página).
#
# Estructura de cada item:
#   Nombre:  .p-title .elementor-heading-title
#   Precio:  .woocommerce-Price-amount → parent .elementor-heading-title
#   Imagen:  primer <img>
#   URL:     a[href*="/producto/"]
# ─────────────────────────────────────────────

NEXT_SELECTOR = ".jet-filters-pagination__item.next[data-value='next']"
GRID_ITEM     = ".jet-listing-grid--2613 .jet-listing-grid__item"


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


def parsear_pagina(html, vistos):
    soup = BeautifulSoup(html, "lxml")
    productos = []

    grid = soup.select_one(".jet-listing-grid--2613")
    items = grid.select(".jet-listing-grid__item") if grid else []

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    for item in items:
        nombre_el = item.select_one(".p-title .elementor-heading-title")
        if not nombre_el:
            nombre_el = item.select_one("h3.elementor-heading-title")
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)
        if not nombre or nombre in vistos:
            continue

        precio_container = item.select_one(".woocommerce-Price-amount")
        if precio_container:
            heading = precio_container.find_parent(class_="elementor-heading-title")
            precio_raw = heading.get_text(" ", strip=True) if heading else precio_container.get_text(" ", strip=True)
        else:
            precio_raw = ""
            for span in item.select(".elementor-heading-title"):
                txt = span.get_text(strip=True)
                if "$" in txt:
                    precio_raw = txt
                    break

        precio = parse_precio(precio_raw)
        if not precio:
            continue

        unidad = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"

        link_el  = item.select_one("a[href*='/producto/']")
        url_prod = link_el.get("href", "") if link_el else ""

        img_el = item.select_one("img")
        imagen = ""
        if img_el:
            imagen = (img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src") or "")

        vistos.add(nombre)
        productos.append({
            "supermercado":  SUPERMERCADO,
            "codigo":        "",
            "nombre":        nombre,
            "categoria":     "Carnes",
            "precio_actual": precio,
            "unidad":        unidad,
            "imagen":        imagen,
            "url":           url_prod,
            "fecha":         fecha,
        })

    return productos


def tiene_next(page):
    """Devuelve True si el botón → (next) existe y es visible."""
    try:
        loc = page.locator(NEXT_SELECTOR).first
        return loc.count() > 0 and loc.is_visible()
    except Exception:
        return False


def scrape_all():
    if not PLAYWRIGHT_OK:
        log.error("Playwright no instalado. Correr: pip install playwright && playwright install chromium")
        return []

    todos  = []
    vistos = set()

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
        page.route("**/google-analytics.com/**",   lambda r: r.abort())
        page.route("**/googletagmanager.com/**",   lambda r: r.abort())
        page.route("**/facebook.com/**",           lambda r: r.abort())
        page.route("**/doubleclick.net/**",        lambda r: r.abort())

        # ── Cargar página 1 ──────────────────────────────────
        log.info(f"[Piala] Cargando: {BASE_URL}")
        try:
            page.goto(BASE_URL, wait_until="networkidle", timeout=45000)
        except PWTimeout:
            try:
                page.goto(BASE_URL, wait_until="load", timeout=30000)
                page.wait_for_timeout(4000)
            except PWTimeout:
                log.error("  FALLO al cargar la página principal")
                browser.close()
                return []

        try:
            page.wait_for_selector(GRID_ITEM, timeout=15000)
        except PWTimeout:
            log.warning("  Timeout esperando el grid principal")

        page.wait_for_timeout(1500)

        num_pagina = 1
        while True:
            html  = page.content()
            prods = parsear_pagina(html, vistos)
            log.info(f"  Página {num_pagina} → {len(prods)} productos nuevos")
            todos.extend(prods)

            # ¿Hay botón siguiente?
            if not tiene_next(page):
                log.info("  Sin botón siguiente — fin de paginación")
                break

            num_pagina += 1
            log.info(f"[Piala] Clickeando → hacia página {num_pagina}...")

            try:
                page.locator(NEXT_SELECTOR).first.click()

                # Esperar que el grid actualice: primero desaparece, luego vuelve
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except PWTimeout:
                    page.wait_for_timeout(3000)

                page.wait_for_selector(GRID_ITEM, timeout=10000)
                page.wait_for_timeout(800)

            except PWTimeout:
                log.warning(f"  Timeout navegando a página {num_pagina}, abortando")
                break

            time.sleep(0.3)

        browser.close()

    log.info(f"[Piala] Total: {len(todos)} productos")
    return todos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "piala")
    else:
        log.warning("[Piala] Sin productos obtenidos")
