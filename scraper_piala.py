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

try:
    from playwright_stealth import stealth_sync
    STEALTH_OK = True
except ImportError:
    STEALTH_OK = False

BASE_URL     = "https://www.piala.com.ar/productos/"
SUPERMERCADO = "piala"
OUTPUT_DIR   = Path("output_piala")

# Categorías de Piala con sus slugs WooCommerce
# Scrapeamos por categoría para asignarla correctamente a cada producto
CATEGORIAS = [
    ("Cortes vacunos",    "cortes-vacunos"),
    ("Pollos y Derivados","pollos-y-derivados"),
    ("Cortes de Cerdo",   "cortes-de-cerdo"),
    ("Elaborados",        "elaborados"),
    ("Embutidos",         "embutidos"),
    ("Menudencias",       "menudencias"),
    ("Envasados al Vacio","envasados-al-vacio"),
    ("Complementos",      "complementos"),
    ("Bichos",            "bichos"),
]

NEXT_SEL  = ".jet-filters-pagination__item.next[data-value='next']"
GRID_SEL  = ".jet-listing-grid--2613 .jet-listing-grid__item"


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


def parsear_pagina(html, categoria, vistos):
    soup = BeautifulSoup(html, "lxml")
    productos = []
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    grid = soup.select_one(".jet-listing-grid--2613")
    if not grid:
        return []

    for item in grid.select(".jet-listing-grid__item"):
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

        unidad   = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"
        link_el  = item.select_one("a[href*='/producto/']")
        url_prod = link_el.get("href", "") if link_el else ""
        img_el   = item.select_one("img")
        imagen   = (img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src") or "") if img_el else ""

        vistos.add(nombre)
        productos.append({
            "supermercado":  SUPERMERCADO,
            "codigo":        "",
            "nombre":        nombre,
            "categoria":     categoria,
            "precio_actual": precio,
            "unidad":        unidad,
            "imagen":        imagen,
            "url":           url_prod,
            "fecha":         fecha,
        })

    return productos


def es_challenge(page):
    try:
        return page.locator("#domain-name").count() > 0
    except Exception:
        return False


def esperar_challenge(page, timeout_ms=45000):
    log.info("  Challenge detectado - esperando resolucion (~30s)...")
    try:
        page.wait_for_selector("#domain-name", state="detached", timeout=timeout_ms)
        log.info("  Challenge resuelto")
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeout:
            page.wait_for_timeout(5000)
        return True
    except PWTimeout:
        log.warning("  Challenge no se resolvio")
        return False


def tiene_next(page):
    try:
        loc = page.locator(NEXT_SEL).first
        return loc.count() > 0 and loc.is_visible()
    except Exception:
        return False


def primer_nombre(page):
    try:
        loc = page.locator(".jet-listing-grid--2613 .p-title .elementor-heading-title").first
        if loc.count() > 0:
            return loc.inner_text(timeout=3000).strip()
    except Exception:
        pass
    return ""


def esperar_cambio(page, nombre_anterior, timeout_s=15):
    for _ in range(timeout_s * 2):
        nombre_actual = primer_nombre(page)
        if nombre_actual and nombre_actual != nombre_anterior:
            return True
        time.sleep(0.5)
    return False


def scrape_categoria(page, categoria, slug, vistos):
    """Scrape todos los productos de una categoría dada."""
    url = f"{BASE_URL}?product_cat={slug}"
    log.info(f"[Piala] Categoria: {categoria} ({url})")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        log.warning(f"  Timeout cargando {categoria}")
        return []

    page.wait_for_timeout(2000)

    if es_challenge(page):
        if not esperar_challenge(page):
            return []

    try:
        page.wait_for_selector(GRID_SEL, timeout=15000)
    except PWTimeout:
        log.warning(f"  Grid no encontrado para {categoria} — categoria vacia o no existe")
        return []

    page.wait_for_timeout(1000)

    todos_cat = []
    num_pagina = 1

    while True:
        html  = page.content()
        prods = parsear_pagina(html, categoria, vistos)
        log.info(f"  Pagina {num_pagina}: {len(prods)} nuevos")
        todos_cat.extend(prods)

        if not tiene_next(page):
            break

        nombre_antes = primer_nombre(page)
        num_pagina += 1

        try:
            page.locator(NEXT_SEL).first.click()
            esperar_cambio(page, nombre_antes, timeout_s=12)
            page.wait_for_timeout(500)
        except PWTimeout:
            log.warning(f"  Timeout paginando {categoria}")
            break

        time.sleep(0.3)

    log.info(f"  Total {categoria}: {len(todos_cat)} productos")
    return todos_cat


def scrape_all():
    if not PLAYWRIGHT_OK:
        log.error("Playwright no instalado.")
        return []

    if not STEALTH_OK:
        log.warning("playwright-stealth no disponible - instalar: pip install playwright-stealth")

    todos  = []
    vistos = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        if STEALTH_OK:
            stealth_sync(page)
            log.info("  Stealth aplicado")

        page.route("**/google-analytics.com/**", lambda r: r.abort())
        page.route("**/googletagmanager.com/**", lambda r: r.abort())
        page.route("**/facebook.com/**",         lambda r: r.abort())
        page.route("**/doubleclick.net/**",      lambda r: r.abort())

        # Carga inicial para resolver challenge una sola vez
        log.info(f"[Piala] Carga inicial para resolver challenge...")
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            log.error("  FALLO carga inicial")
            browser.close()
            return []

        page.wait_for_timeout(3000)
        if es_challenge(page):
            if not esperar_challenge(page):
                browser.close()
                return []

        # Scrapear por categoría
        for categoria, slug in CATEGORIAS:
            prods = scrape_categoria(page, categoria, slug, vistos)
            todos.extend(prods)
            time.sleep(0.5)

        browser.close()

    log.info(f"[Piala] Total: {len(todos)} productos unicos")
    return todos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "piala")
    else:
        log.warning("[Piala] Sin productos obtenidos")
    
