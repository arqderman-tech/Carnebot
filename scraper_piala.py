"""
scraper_piala.py – Scraper para Piala de Patria (piala.com.ar)
Sitio: WooCommerce – scraping HTML página a página.
Uso: python scraper_piala.py
"""

import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from scraper_base import get_html, _parse_precio, guardar, log, HEADERS
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime

BASE_URL   = "https://www.piala.com.ar/productos/"
SUPERMERCADO = "piala"
OUTPUT_DIR = Path("output_piala")


def scrape_pagina(url):
    """Extrae todos los productos de una página de listado WooCommerce."""
    html = get_html(url)
    if not html:
        return [], None

    soup = BeautifulSoup(html, "lxml")
    productos = []

    for item in soup.select("li.product, div.product"):
        nombre_el = item.select_one("h2.woocommerce-loop-product__title, h3.woocommerce-loop-product__title, .woocommerce-loop-product__title")
        precio_el = item.select_one("span.price, .price")
        img_el    = item.select_one("img")
        link_el   = item.select_one("a.woocommerce-loop-product__link, a")

        if not nombre_el:
            continue

        nombre = nombre_el.get_text(strip=True)

        # Precio: puede ser "$9000.00 /kg" o rango
        precio_raw = precio_el.get_text(strip=True) if precio_el else ""
        # Extraer unidad si está en el precio o en el nombre
        unidad = "kg"
        if "/kg" in precio_raw.lower() or "/kg" in nombre.lower():
            unidad = "kg"
        elif "unidad" in precio_raw.lower() or "unidad" in nombre.lower():
            unidad = "unidad"
        
        precio = _parse_precio(precio_raw)

        imagen = img_el.get("src") or img_el.get("data-src", "") if img_el else ""
        url_prod = link_el.get("href", "") if link_el else ""

        # Intentar obtener categoría del breadcrumb o de la URL
        categoria = "Carnes"

        productos.append({
            "supermercado": SUPERMERCADO,
            "codigo":       "",
            "nombre":       nombre,
            "categoria":    categoria,
            "precio_actual": precio,
            "unidad":       unidad,
            "imagen":       imagen,
            "url":          url_prod,
            "fecha":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    # Siguiente página (paginación WooCommerce)
    next_page = soup.select_one("a.next.page-numbers, .woocommerce-pagination a.next")
    next_url = next_page.get("href") if next_page else None

    log.info(f"  Página {url[:80]} → {len(productos)} productos")
    return productos, next_url


def scrape_all():
    todos = []
    url = BASE_URL
    pagina = 1

    while url:
        log.info(f"[Piala] Scrapeando página {pagina}: {url}")
        prods, next_url = scrape_pagina(url)
        todos.extend(prods)
        if not next_url or next_url == url:
            break
        url = next_url
        pagina += 1
        import time; time.sleep(1)  # cortesía

    log.info(f"[Piala] Total: {len(todos)} productos")
    return todos


if __name__ == "__main__":
    productos = scrape_all()
    if productos:
        guardar(productos, OUTPUT_DIR, "piala")
    else:
        log.warning("[Piala] Sin productos obtenidos")
