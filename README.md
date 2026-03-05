# 🥩 CarneBot – Monitor de precios de carnicerías

> Seguimiento diario automatizado de precios en **Piala de Patria** y **Carnes El Chañar** (Rosario, Argentina).

**[Ver sitio web →](https://TU_USUARIO.github.io/carnebot)**

---

## ¿Qué hace?

- **Scrapea** precios cada día (8:30 AM hora Argentina)
- **Compara** precios entre las dos carnicerías para los mismos cortes
- **Rastrea** evolución histórica: variación diaria, semanal y mensual
- **Genera** automáticamente una página web en GitHub Pages con gráficos y rankings

## Estructura

```
carnebot/
├── scraper_piala.py        # Scraper de piala.com.ar (WooCommerce)
├── scraper_chanear.py      # Scraper de carneselchanear.com.ar
├── scraper_base.py         # Utilidades compartidas
├── analizar_precios.py     # Análisis de variaciones y rankings
├── generar_web.py          # Generador del sitio web estático
├── generar_datos_muestra.py# Genera datos de prueba locales
├── requirements.txt
├── data/
│   ├── precios_compacto.csv  # Historial completo (1 fila/producto/día)
│   ├── resumen.json          # Resumen del día
│   ├── graficos.json         # Series temporales para gráficos
│   └── ranking_dia.json      # Rankings de subidas/bajadas
├── docs/
│   └── index.html            # Sitio web (GitHub Pages)
├── outputs/
│   ├── output_piala/         # CSVs/JSONs scrapeados de Piala
│   └── output_chanear/       # CSVs/JSONs scrapeados de El Chañar
└── .github/workflows/
    ├── scraper_diario.yml    # Corre todos los días a las 8:30 AM
    └── regenerar_web.yml     # Regenera el sitio manualmente
```

## Setup

### 1. Clonar y configurar

```bash
git clone https://github.com/TU_USUARIO/carnebot
cd carnebot
pip install -r requirements.txt
```

### 2. Activar GitHub Pages

En el repositorio: **Settings → Pages → Source: Deploy from branch → main → /docs**

### 3. Probar localmente

```bash
# Generar datos de muestra (sin necesidad de acceso a internet)
python generar_datos_muestra.py

# Analizar y generar web
python analizar_precios.py
python generar_web.py

# Ver resultado
open docs/index.html
```

### 4. Correr scrapers

```bash
python scraper_piala.py
python scraper_chanear.py
```

## GitHub Actions

El workflow `scraper_diario.yml` se ejecuta automáticamente cada día.  
También podés lanzarlo manualmente desde la pestaña **Actions** → **Scraper Diario**.

## Agregar más carnicerías

1. Crear `scraper_NOMBRE.py` siguiendo el patrón de los existentes
2. Agregar el paso en `.github/workflows/scraper_diario.yml`
3. Actualizar `analizar_precios.py` para incluir los nuevos outputs

## Datos

Los CSVs tienen las columnas:
`supermercado, codigo, nombre, categoria, precio_actual, unidad, imagen, url, fecha`

---

*Inspirado en [COTOBOT](https://github.com/). Datos de referencia; verificar en cada local.*
