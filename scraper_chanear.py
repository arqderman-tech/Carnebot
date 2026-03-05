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
    cards = soup.select("div.col.s6, div.col.s12.m6, div.card, div.producto")

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
        for tag in card.find_all(["strong", "b", "span", "p", "div"]):
            t = tag.get_text(strip=True)
            if (t and len(t) > 3 and t == t.upper()
                    and not re.match(r"^[\d\s$.,]+$", t)
                    and "COD" not in t.upper()
                    and "$" not in t):
                nombre = t
                break

        # Fallback: palabras en mayúsculas antes del precio en el texto
        if not nombre:
            idx    = texto.find(precio_m.group(0))
            before = texto[:idx].split()
            palabras = []
            for w in reversed(before):
                if w == w.upper() and not re.match(r"^[\d.,]+$", w):
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


def scrape_rubro_playwright(page, rubro):
    """Navega a un rubro y espera que Vue.js renderice los productos."""
    url = f"{BASE_URL}/shop/rubros/{rubro['id']}/{rubro['slug']}"

    try:
        page.goto(url, wait_until="networkidle", timeout=30_000)
    except PWTimeout:
        log.warning(f"  Timeout networkidle en {rubro['nombre']}, reintentando con load...")
        try:
            page.goto(url, wait_until="load", timeout=20_000)
            page.wait_for_timeout(3000)
        except PWTimeout:
            log.error(f"  FALLO definitivo: {url}")
            return []

    # Esperar que Vue monte los componentes
    try:
        page.wait_for_selector("h3", timeout=8_000)
    except PWTimeout:
        log.warning(f"  No se encontró h3 en {rubro['nombre']}")

    # Scroll para lazy-loading
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(800)

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
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            locale="es-AR",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # Bloquear recursos pesados para acelerar la carga
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
            lambda r: r.abort()
        )
        page.route("**/google-analytics.com/**", lambda r: r.abort())
        page.route("**/googletagmanager.com/**", lambda r: r.abort())
        page.route("**/facebook.com/**",         lambda r: r.abort())

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
