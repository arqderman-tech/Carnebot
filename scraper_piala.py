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
# DIAGNÓSTICO DEL SITIO (piala_debug.html)
#
# El sitio usa JetEngine + JetSmartFilters + Elementor.
# NO es WooCommerce estándar — los productos se renderizan en
#   div.jet-listing-grid__item  (NO en li.product)
#
# Hay 105 productos en 7 páginas (15 por página).
# La paginación es 100% JavaScript: no hay URLs de tipo /page/N/.
# Para navegar hay que clickear  div.jet-filters-pagination__item[data-value="N"]
# y esperar a que el grid se actualice.
#
# Estructura de cada item:
#   Nombre:  .p-title .elementor-heading-title  (h3 con link)
#   Precio:  .woocommerce-Price-amount  → subir al elementor-heading-title padre
#            (para capturar también el texto "/kg")
#   Imagen:  primer <img>
#   URL:     a[href*="/producto/"]
# ─────────────────────────────────────────────


def parse_precio(texto):
    """Convierte '$ 9000.00 /kg' o '$ 13.332,00' → float"""
    if not texto:
        return None
    m = re.search(r'\$\s*([\d.,]+)', texto)
    if not m:
        return None
    raw = m.group(1)
    # Punto decimal anglosajón: 9000.00
    if re.match(r'^\d+\.\d{1,2}$', raw):
        return float(raw)
    # Punto de miles + coma decimal: 13.332,00
    return float(raw.replace(".", "").replace(",", "."))


def parsear_pagina(html, vistos):
    """
    Extrae productos del HTML renderizado.
    vistos: set de nombres ya procesados (para deduplicar entre páginas).
    Devuelve lista de productos nuevos.
    """
    soup = BeautifulSoup(html, "lxml")
    productos = []

    # Usar solo el grid principal (listing-id=2613), ignorar el 1068 (destacados)
    grid = soup.select_one(".jet-listing-grid--2613")
    items = grid.select(".jet-listing-grid__item") if grid else soup.select(".jet-listing-grid__item")

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    for item in items:
        # ── Nombre ──────────────────────────────────────────
        nombre_el = item.select_one(".p-title .elementor-heading-title")
        if not nombre_el:
            nombre_el = item.select_one("h3.elementor-heading-title")
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)
        if not nombre or nombre in vistos:
            continue

        # ── Precio ───────────────────────────────────────────
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

        # ── Unidad ───────────────────────────────────────────
        unidad = "kg" if re.search(r'/kg', precio_raw, re.I) else "unidad"

        # ── URL ──────────────────────────────────────────────
        link_el  = item.select_one("a[href*='/producto/']")
        url_prod = link_el.get("href", "") if link_el else ""

        # ── Imagen ───────────────────────────────────────────
        img_el = item.select_one("img")
        imagen = ""
        if img_el:
            imagen = (img_el.get("src") or
                      img_el.get("data-src") or
                      img_el.get("data-lazy-src") or "")

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


def get_total_pages(html):
    """Lee el número de páginas desde la paginación de JetSmartFilters."""
    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".jet-filters-pagination__item[data-value]")
    paginas = []
    for item in items:
        val = item.get("data-value", "")
        if val.isdigit():
            paginas.append(int(val))
    return max(paginas) if paginas else 1


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

        # Bloquear recursos pesados que no afectan el contenido
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}", lambda r: r.abort())
        page.route("**/google-analytics.com/**", lambda r: r.abort())
        page.route("**/googletagmanager.com/**", lambda r: r.abort())
        page.route("**/facebook.com/**", lambda r: r.abort())
        page.route("**/doubleclick.net/**", lambda r: r.abort())

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

        # Esperar a que JetEngine renderice el grid
        try:
            page.wait_for_selector(".jet-listing-grid--2613 .jet-listing-grid__item", timeout=15000)
        except PWTimeout:
            log.warning("  Timeout esperando el grid principal")

        page.wait_for_timeout(1500)

        html = page.content()
        total_paginas = get_total_pages(html)
        log.info(f"[Piala] Páginas detectadas: {total_paginas}")

        prods = parsear_pagina(html, vistos)
        log.info(f"  Página 1 → {len(prods)} productos")
        todos.extend(prods)

        # ── Paginar haciendo click en cada número ────────────
        for num_pagina in range(2, total_paginas + 1):
            log.info(f"[Piala] Navegando a página {num_pagina}...")

            try:
                # Clickear el item de paginación con data-value=N
                selector = f".jet-filters-pagination__item[data-value='{num_pagina}']"
                page.wait_for_selector(selector, timeout=8000)
                page.click(selector)

                # Esperar a que el grid se actualice (networkidle o timeout)
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except PWTimeout:
                    page.wait_for_timeout(3000)

                # Esperar que aparezcan items nuevos
                page.wait_for_selector(".jet-listing-grid--2613 .jet-listing-grid__item", timeout=10000)
                page.wait_for_timeout(1000)

            except PWTimeout:
                log.warning(f"  Timeout en página {num_pagina}, saltando")
                continue

            html = page.content()
            prods = parsear_pagina(html, vistos)
            log.info(f"  Página {num_pagina} → {len(prods)} productos nuevos")
            todos.extend(prods)

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
        
