"""
scraper_piala.py – Scraper para Piala de Patria (piala.com.ar)
Usa Playwright para manejar contenido dinámico (WooCommerce + JS).

Instalar:
    pip install playwright
    playwright install chromium

Uso:
    python scraper_piala.py
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

BASE_URL     = "https://www.piala.com.ar/productos/"
SUPERMERCADO = "piala"
OUTPUT_DIR   = Path("output_piala")


def parsear_productos(html, url_pagina):
    soup = BeautifulSoup(html, "lxml")
    productos = []
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    items = soup.select("li.product, ul.products li")

    for item in items:
        nombre_el = item.select_one(
            ".woocommerce-loop-product__title, "
            "h2.woocommerce-loop-product__title, "
            "h3.woocommerce-loop-product__title"
        )
        if not nombre_el:
            continue
        nombre = nombre_el.get_text(strip=True)

        precio_el = item.select_one("span.price")
        precio_raw = precio_el.get_text(" ", strip=True) if precio_el else ""

        precio_m = re.search(r"\$\s*([\d.]+,\d{2}|\d+)", precio_raw)
        precio = _parse_precio(precio_m.group(1)) if precio_m else None

        texto_lower = (precio_raw + " " + nombre).lower()
        if "/kg" in texto_lower or "por kg" in texto_lower or "kilo" in texto_lower:
            unidad = "kg"
        else:
            unidad = "unidad"

        img_el = item.select_one("img")
        imagen = ""
        if img_el:
            imagen = (img_el.get("src") or
                      img_el.get("data-src") or
                      img_el.get("data-lazy-src") or "")

        link_el = item.select_one("a.woocommerce-loop-product__link, a")
        url_prod = link_el.get("href", "") if link_el else ""

        cat_el = item.select_one(".product-category, .posted_in a")
        categoria = cat_el.get_text(strip=True) if cat_el else "Carnes"

        if nombre and precio:
            productos.append({
                "supermercado": SUPERMERCADO,
                "codigo":       "",
                "nombre":       nombre,
                "categoria":    categoria,
                "precio_actual": precio,
                "unidad":       unidad,
                "imagen":       imagen,
                "url":          url_prod,
                "fecha":        fecha,
            })

    return productos


def get_next_url(html):
    soup = BeautifulSoup(html, "lxml")
    next_el = soup.select_one("a.next.page-numbers, .woocommerce-pagination a.next")
    return next_el.get("href") if next_el else None


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

        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
            lambda r: r.abort()
        )
        page.route("**/google-analytics.com/**", lambda r: r.abort())
        page.route("**/googletagmanager.com/**", lambda r: r.abort())
        page.route("**/facebook.com/**",         lambda r: r.abort())

        url = BASE_URL
        pagina = 1

        while url:
            log.info(f"[Piala] Página {pagina}: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
            except PWTimeout:
                log.warning(f"  Timeout networkidle, reintentando con load...")
                try:
                    page.goto(url, wait_until="load", timeout=20_000)
                    page.wait_for_timeout(2000)
                except PWTimeout:
                    log.error(f"  FALLO en página {pagina}, abortando.")
                    break

            try:
                page.wait_for_selector("li.product", timeout=8_000)
            except PWTimeout:
                log.warning(f"  No se encontraron li.product en página {pagina}")

            html = page.content()
            prods = parsear_productos(html, url)
            log.info(f"  → {len(prods)} productos")
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
