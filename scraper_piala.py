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
# Hay DOS grids en la página:
#   - listing-id=2613 → grid principal de productos (15 por página)
#   - listing-id=1068 → grid de "destacados" (3 fijos, se repite en cada página)
#
# El scraper original mezclaba ambos grids y el set "vistos" no alcanzaba
# porque parsear_pagina usaba soup.select() global en lugar de filtrar por grid.
# Resultado: 90 filas en el CSV pero solo ~15 únicos tras deduplicar.
#
# FIX: filtrar SIEMPRE por .jet-listing-grid--2613 (grid principal).
#
# PAGINACIÓN:
#   La paginación JetSmartFilters solo renderiza botones numéricos cercanos
#   a la página actual (ej: en pág 1 muestra [1,2,3,4,…,→]).
#   Los botones 5,6,7 no aparecen hasta navegar más adelante.
#   Solución: loop por botón "→" (data-value="next") hasta que desaparezca.
# ─────────────────────────────────────────────

NEXT_SELECTOR = ".jet-filters-pagination__item.next[data-value='next']"
GRID_SELECTOR = ".jet-listing-grid--2613 .jet-listing-grid__item"


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
    """
    Extrae productos del grid principal (listing-id=2613).
    vistos: set de nombres ya procesados entre páginas.
    """
    soup = BeautifulSoup(html, "lxml")
    productos = []
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    # SOLO el grid 2613 — ignorar el 1068 (destacados que se repiten en todas las páginas)
    grid = soup.select_one(".jet-listing-grid--2613")
    if not grid:
        log.warning("  Grid 2613 no encontrado en el HTML")
        return []

    items = grid.select(".jet-listing-grid__item")

    for item in items:
        # Nombre
        nombre_el = item.select_one(".p-title .elementor-heading-title")
        if not nombre_el:
            nombre_el = item.select_one("h3.elementor-heading-title")
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)
        if not nombre or nombre in vistos:
            continue

        # Precio — buscar .woocommerce-Price-amount y subir al heading para capturar "/kg"
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
        imagen   = ""
        if img_el:
            imagen = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy-src") or ""

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
    """Devuelve True si el botón → existe y es visible."""
    try:
        loc = page.locator(NEXT_SELECTOR).first
        return loc.count() > 0 and loc.is_visible()
    except Exception:
        return False


def scrape_all():
    if not PLAYWRIGHT_OK:
        log.error("Playwright no instalado.")
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
        page.route("**/google-analytics.com/**",  lambda r: r.abort())
        page.route("**/googletagmanager.com/**",  lambda r: r.abort())
        page.route("**/facebook.com/**",          lambda r: r.abort())
        page.route("**/doubleclick.net/**",       lambda r: r.abort())

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
            page.wait_for_selector(GRID_SELECTOR, timeout=15000)
        except PWTimeout:
            log.warning("  Timeout esperando el grid 2613")

        page.wait_for_timeout(1500)

        num_pagina = 1
        while True:
            html  = page.content()
            prods = parsear_pagina(html, vistos)
            log.info(f"  Página {num_pagina} → {len(prods)} productos nuevos (total: {len(todos) + len(prods)})")
            todos.extend(prods)

            if not tiene_next(page):
                log.info("  Sin botón → — fin de paginación")
                break

            num_pagina += 1
            log.info(f"[Piala] Clickeando → hacia página {num_pagina}...")

            try:
                page.locator(NEXT_SELECTOR).first.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except PWTimeout:
                    page.wait_for_timeout(3000)
                page.wait_for_selector(GRID_SELECTOR, timeout=10000)
                page.wait_for_timeout(800)
            except PWTimeout:
                log.warning(f"  Timeout en página {num_pagina}, abortando")
                break

            time.sleep(0.3)

        browser.close()

    log.info(f"[Piala] Total: {len(todos)} productos únicos")
    return todos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "piala")
    else:
        log.warning("[Piala] Sin productos obtenidos")
