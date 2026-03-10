"""
scraper_chanear.py – Scraper para Carnes El Chañar (carneselchanear.com.ar)

El sitio carga los productos via Vue.js en el cliente, por lo que un simple
requests+BeautifulSoup no alcanza. Usamos Playwright para ejecutar el JS
y obtener el DOM completamente renderizado.

Instalar:
    pip install playwright
    playwright install chromium

Uso:
    python scraper_chanear.py
"""

import sys, re, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from scraper_base import _parse_precio, guardar, log
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False
    log.error("Playwright no instalado. Correr: pip install playwright && playwright install chromium")

BASE_URL     = "https://carneselchanear.com.ar"
SUPERMERCADO = "chanear"
OUTPUT_DIR   = Path("output_chanear")

RUBROS = [
    {"id": 1,  "nombre": "Carnes Vacunas",        "slug": "1-carnes-vacunas"},
    {"id": 4,  "nombre": "Pollo",                 "slug": "2-pollo"},
    {"id": 3,  "nombre": "Cerdo",                 "slug": "3-cerdo"},
    {"id": 2,  "nombre": "Otras Carnes",           "slug": "4-otras-carnes"},
    {"id": 6,  "nombre": "Achuras y Menudencias",  "slug": "5-achuras-y-menudencias"},
    {"id": 11, "nombre": "Embutidos",              "slug": "6-embutidos"},
    {"id": 9,  "nombre": "Elaborados",             "slug": "7-elaborados"},
    {"id": 10, "nombre": "Elaborados Premium",     "slug": "8-elaborados-premium"},
]


def parsear_productos(html, rubro_nombre, rubro_url):
    """
    Extrae productos del HTML ya renderizado por Vue.js.

    La estructura del DOM de El Chañar es:

      <div class="col s6 m4 l3">           <- card de producto
        <img src="...">
        <strong>NOMBRE DEL CORTE</strong>
        Cod:<strong>123</strong>
        <h3>$16.400,00</h3>
        por Kilogramo
      </div>
    """
    soup = BeautifulSoup(html, "lxml")
    productos = []
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Estrategia 1: cards de materialize CSS ────────────────────────────────
    # Selector ampliado: cubre col s6, s12 m6, l3, card, producto, etc.
    cards = soup.select(
        "div.col.s6, div.col.s12.m6, div.col.m4, div.col.l3, "
        "div.card, div.card-content, div.producto, "
        "div[class*='product'], li[class*='product']"
    )
    if not cards:
        # Fallback: cualquier div que contenga un precio visible
        cards = [d for d in soup.find_all("div") if "$" in d.get_text()]

    for card in cards:
        texto = card.get_text(" ", strip=True)

        precio_m = re.search(r"\$\s*([\d.]+,\d{2})", texto)
        if not precio_m:
            continue
        precio = _parse_precio(precio_m.group(1))
        if not precio or precio < 100:
            continue

        cod_m  = re.search(r"Cod[:\s]*(\d+)", texto, re.I)
        codigo = cod_m.group(1) if cod_m else ""

        unidad_m  = re.search(r"por\s+(Kilogramo|Unidad|Fraccion)", texto, re.I)
        unidad_raw = unidad_m.group(1).lower() if unidad_m else "kilogramo"
        unidad    = "kg" if "kilo" in unidad_raw else "unidad"

        # Nombre: primer tag con texto en mayúsculas
        nombre = ""
        for tag in card.find_all(["strong", "b", "span", "p", "h4", "h5", "h6", "div"]):
            t = tag.get_text(strip=True)
            if (t and 3 < len(t) < 80
                    and t == t.upper()
                    and not re.match(r"^[\d\s$.,]+$", t)
                    and "COD" not in t.upper()
                    and "$" not in t
                    and "POR" not in t.upper()):
                nombre = t
                break

        # Fallback: palabras en mayúsculas antes del precio en el texto plano
        if not nombre:
            idx    = texto.find(precio_m.group(0))
            before = texto[:idx].split()
            palabras = []
            for w in reversed(before):
                if w == w.upper() and not re.match(r"^[\d.,\-\$]+$", w) and len(w) > 1:
                    palabras.insert(0, w)
                else:
                    break
            nombre = " ".join(palabras).strip()

        if not nombre or len(nombre) < 3:
            continue

        img_el = card.find("img")
        imagen = ""
        if img_el:
            imagen = img_el.get("src") or img_el.get("data-src", "")
            if imagen and not imagen.startswith("http"):
                imagen = BASE_URL + imagen

        productos.append({
            "supermercado": SUPERMERCADO,
            "codigo":       codigo,
            "nombre":       nombre,
            "categoria":    rubro_nombre,
            "precio_actual": precio,
            "unidad":       unidad,
            "imagen":       imagen,
            "url":          rubro_url,
            "fecha":        fecha,
        })

    if productos:
        log.info(f"  [Estrategia 1 - cards] {rubro_nombre}: {len(productos)} productos")
        return productos

    # ── Estrategia 2: regex sobre texto completo ──────────────────────────────
    # Patrón: NOMBRE EN MAYUSCULAS  Cod:NNN  $PRECIO  por UNIDAD
    patron = re.compile(
        r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\-\/()]{2,}?)"
        r"\s*Cod[:\s]*(\d+)"
        r".*?\$\s*([\d.]+,\d{2})"
        r".*?por\s+(Kilogramo|Unidad|Fraccion)",
        re.DOTALL | re.I
    )
    texto_full = soup.get_text(" ")
    for m in patron.finditer(texto_full):
        nombre   = m.group(1).strip()
        codigo   = m.group(2).strip()
        precio   = _parse_precio(m.group(3))
        unidad_r = m.group(4).lower()
        unidad   = "kg" if "kilo" in unidad_r else "unidad"
        if precio and precio > 100 and nombre:
            productos.append({
                "supermercado": SUPERMERCADO,
                "codigo":       codigo,
                "nombre":       nombre,
                "categoria":    rubro_nombre,
                "precio_actual": precio,
                "unidad":       unidad,
                "imagen":       "",
                "url":          rubro_url,
                "fecha":        fecha,
            })

    if productos:
        log.info(f"  [Estrategia 2 - regex] {rubro_nombre}: {len(productos)} productos")
    else:
        log.warning(f"  Sin productos en {rubro_nombre} — revisar selectores")

    return productos


def _navegar_con_reintentos(page, url, rubro_nombre):
    """
    Navega a una URL probando distintas estrategias de espera.
    Retorna True si la navegación fue exitosa (aunque sea parcialmente).
    """
    # Intento 1: networkidle (ideal, pero Vue.js mantiene conexiones abiertas)
    try:
        page.goto(url, wait_until="networkidle", timeout=25_000)
        return True
    except PWTimeout:
        log.warning(f"  Timeout networkidle en {rubro_nombre}, reintentando con load...")

    # Intento 2: wait_until="load" + espera extra para que Vue termine de montar
    try:
        page.goto(url, wait_until="load", timeout=20_000)
        page.wait_for_timeout(4_000)
        return True
    except PWTimeout:
        log.warning(f"  Timeout load en {rubro_nombre}, reintentando con commit...")

    # Intento 3: wait_until="commit" (sólo espera primer byte) + espera larga
    try:
        page.goto(url, wait_until="commit", timeout=15_000)
        page.wait_for_timeout(8_000)
        return True
    except PWTimeout:
        log.error(f"  FALLO definitivo: {url}")
        return False


def scrape_rubro_playwright(page, rubro):
    """Navega a un rubro y espera que Vue.js renderice los productos."""
    url = f"{BASE_URL}/shop/rubros/{rubro['id']}/{rubro['slug']}"

    if not _navegar_con_reintentos(page, url, rubro["nombre"]):
        return []

    # Esperar selector de precio — más robusto que esperar sólo h3
    # El sitio puede usar h3, span, div, p con el símbolo $
    try:
        page.wait_for_selector(
            "h3, [class*='precio'], [class*='price'], span:has-text('$')",
            timeout=10_000
        )
    except PWTimeout:
        log.warning(f"  No se encontró selector de precio en {rubro['nombre']}, continuando...")

    # Scroll para activar lazy-loading
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1_000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

    html = page.content()
    return parsear_productos(html, rubro["nombre"], url)


def scrape_all():
    if not PLAYWRIGHT_OK:
        log.error("Playwright no disponible.")
        log.error("Instalar con: pip install playwright && playwright install chromium")
        return []

    todos = []

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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # Bloquear recursos pesados — NO bloquear JS/XHR porque Vue los necesita
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
            lambda r: r.abort()
        )
        page.route("**/google-analytics.com/**", lambda r: r.abort())
        page.route("**/googletagmanager.com/**", lambda r: r.abort())
        page.route("**/facebook.com/**",         lambda r: r.abort())
        page.route("**/hotjar.com/**",           lambda r: r.abort())
        page.route("**/clarity.ms/**",           lambda r: r.abort())

        for rubro in RUBROS:
            log.info(f"[Chanear] Rubro: {rubro['nombre']}")
            prods = scrape_rubro_playwright(page, rubro)
            todos.extend(prods)
            time.sleep(0.5)

        browser.close()

    # Deduplicar por código
    vistos = set()
    unicos = []
    for p in todos:
        key = p["codigo"] if p["codigo"] else p["nombre"].upper()
        if key not in vistos:
            vistos.add(key)
            unicos.append(p)

    log.info(f"[Chanear] Total: {len(unicos)} productos unicos ({len(todos)} con posibles duplicados)")
    return unicos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "chanear")
    else:
        log.warning("[Chanear] Sin productos obtenidos")
        
