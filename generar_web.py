"""
generar_web.py
==============
Lee los JSONs de data/ y genera docs/index.html para GitHub Pages.
Estilo: carnicería argentina, diseño oscuro tipo pizarrón con acentos rojo-sangre.
"""

import json
import csv
from pathlib import Path
from datetime import datetime

DIR_DATA = Path("data")
DIR_DOCS = Path("docs")


def leer_json(nombre, default=None):
    ruta = DIR_DATA / nombre
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return default


def leer_csv(nombre):
    ruta = DIR_DATA / nombre
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt_precio(p):
    if p is None:
        return "—"
    return f"${p:,.0f}".replace(",", ".")


def fmt_pct(p, arrow=True):
    if p is None:
        return "—"
    sign = "+" if p > 0 else ""
    emoji = "▲" if p > 0 else ("▼" if p < 0 else "–")
    if arrow:
        return f'{emoji} {sign}{p:.2f}%'
    return f"{sign}{p:.2f}%"


def color_pct(p):
    if p is None:
        return "#888"
    if p > 0:
        return "#e74c3c"
    if p < 0:
        return "#2ecc71"
    return "#888"


def generar_html(resumen, graficos, ranking_dia, ranking_7d, precios_todos=None):
    fecha_str = resumen.get("fecha", "")
    try:
        fecha_fmt = datetime.strptime(fecha_str, "%Y%m%d").strftime("%d/%m/%Y")
    except Exception:
        fecha_fmt = fecha_str

    total_prods   = resumen.get("total_productos", 0)
    var_dia       = resumen.get("variacion_dia")
    var_7d        = resumen.get("variacion_7d")
    subieron      = resumen.get("productos_subieron_dia", 0)
    bajaron       = resumen.get("productos_bajaron_dia", 0)
    sin_cambio    = resumen.get("productos_sin_cambio_dia", 0)
    comparativas  = resumen.get("comparativa_supermercados", [])
    res_sups      = resumen.get("resumen_supermercados", [])

    # Preparar datos de gráficos
    grafico_7d  = graficos.get("7d", {}) if graficos else {}
    grafico_30d = graficos.get("30d", {}) if graficos else {}

    def serie_to_js(serie):
        if not serie:
            return "[]", "[]"
        labels = json.dumps([p["fecha"] for p in serie])
        values = json.dumps([p["pct"] for p in serie])
        return labels, values

    labels_7d,  vals_7d_total   = serie_to_js(grafico_7d.get("total", []))
    labels_30d, vals_30d_total  = serie_to_js(grafico_30d.get("total", []))
    vals_7d_piala   = json.dumps([p["pct"] for p in grafico_7d.get("supermercados", {}).get("piala", [])])
    vals_7d_chanear = json.dumps([p["pct"] for p in grafico_7d.get("supermercados", {}).get("chanear", [])])
    vals_30d_piala   = json.dumps([p["pct"] for p in grafico_30d.get("supermercados", {}).get("piala", [])])
    vals_30d_chanear = json.dumps([p["pct"] for p in grafico_30d.get("supermercados", {}).get("chanear", [])])

    # Rankings HTML
    def ranking_rows(prods, limit=15):
        if not prods:
            return '<tr><td colspan="5" style="text-align:center;color:#666;padding:20px">Sin datos disponibles</td></tr>'
        rows = ""
        for p in prods[:limit]:
            dp = p.get("diff_pct", 0)
            color = color_pct(dp)
            sup_badge = {
                "piala":   '<span class="badge badge-piala">Piala</span>',
                "chanear": '<span class="badge badge-chanear">El Chañar</span>',
            }.get(p.get("supermercado", ""), p.get("supermercado", ""))
            rows += f"""
            <tr>
                <td class="nombre-prod">{p.get('nombre','')}</td>
                <td>{sup_badge}</td>
                <td class="precio">{fmt_precio(p.get('precio_antes'))}</td>
                <td class="precio">{fmt_precio(p.get('precio_hoy'))}</td>
                <td style="color:{color};font-weight:700">{fmt_pct(dp)}</td>
            </tr>"""
        return rows

    # Comparativas
    def comparativas_rows(comps, limit=10):
        if not comps:
            return '<tr><td colspan="5" style="text-align:center;color:#666;padding:20px">Sin cortes en común para comparar aún</td></tr>'
        rows = ""
        for c in comps[:limit]:
            mas_barato = c.get("mas_barato", "")
            rows += f"""
            <tr>
                <td class="nombre-prod">{c.get('nombre','')}</td>
                <td class="precio">{fmt_precio(c.get('precio_1'))}<br><small style="color:#888">{c.get('supermercado_1','')}</small></td>
                <td class="precio">{fmt_precio(c.get('precio_2'))}<br><small style="color:#888">{c.get('supermercado_2','')}</small></td>
                <td style="color:{'#2ecc71' if c.get('diff_pct',0)<0 else '#e74c3c'};font-weight:700">{fmt_pct(c.get('diff_pct'))}</td>
                <td><span class="badge badge-{'piala' if mas_barato=='piala' else 'chanear'}">{mas_barato.title()} 🏆</span></td>
            </tr>"""
        return rows

    # Lista completa de precios por local
    def lista_precios_html(productos):
        if not productos:
            return "", ""

        NOMBRE_LOCAL = {
            "piala":   ("Piala de Patria", "badge-piala"),
            "chanear": ("El Chañar",        "badge-chanear"),
        }

        # Agrupar por supermercado, ordenado por categoría y nombre
        from collections import defaultdict
        por_sup = defaultdict(list)
        for p in productos:
            por_sup[p["supermercado"]].append(p)

        # Obtener categorías únicas para el filtro JS
        cats = sorted({p["categoria"] for p in productos})
        sups = sorted(por_sup.keys())

        # Opciones de filtro supermercado
        sup_opts = '<option value="">Todos los locales</option>' + "".join(
            f'<option value="{s}">{NOMBRE_LOCAL.get(s, (s.title(),))[0]}</option>'
            for s in sups
        )
        cat_opts = '<option value="">Todas las categorías</option>' + "".join(
            f'<option value="{c}">{c}</option>' for c in cats
        )

        # Filas de la tabla (todas, el filtrado lo hace JS)
        filas = ""
        for p in sorted(productos, key=lambda x: (x["supermercado"], x["categoria"], x["nombre"])):
            nombre_sup, badge_cls = NOMBRE_LOCAL.get(p["supermercado"], (p["supermercado"].title(), ""))
            try:
                precio_val = float(p["precio_actual"])
                precio_fmt = fmt_precio(precio_val)
            except (ValueError, TypeError):
                precio_fmt = "—"
            unidad = p.get("unidad", "")
            unidad_txt = f"/{unidad}" if unidad else ""
            filas += (
                f'<tr data-sup="{p["supermercado"]}" data-cat="{p["categoria"]}">'
                f'<td class="nombre-prod">{p["nombre"].title()}</td>'
                f'<td><span class="badge {badge_cls}">{nombre_sup}</span></td>'
                f'<td>{p["categoria"]}</td>'
                f'<td class="precio">{precio_fmt}{unidad_txt}</td>'
                f'</tr>\n'
            )

        html_seccion = f"""
  <!-- LISTA COMPLETA DE PRECIOS -->
  <section class="section" id="lista-precios">
    <h2 class="section-title">🗒️ Lista completa de precios</h2>
    <div class="lista-controls">
      <input type="text" id="lista-buscar" placeholder="Buscar producto..." class="lista-input">
      <select id="lista-sup" class="lista-select">{sup_opts}</select>
      <select id="lista-cat" class="lista-select">{cat_opts}</select>
      <span id="lista-count" class="lista-count"></span>
    </div>
    <div class="table-wrap">
      <table id="tabla-precios">
        <thead><tr>
          <th>Producto</th><th>Local</th><th>Categoría</th><th>Precio</th>
        </tr></thead>
        <tbody id="lista-tbody">
{filas}        </tbody>
      </table>
    </div>
  </section>"""

        js_filtro = """
// ── Lista completa de precios ────────────────────────────────────────────
(function() {
  const tbody  = document.getElementById('lista-tbody');
  const buscar = document.getElementById('lista-buscar');
  const selSup = document.getElementById('lista-sup');
  const selCat = document.getElementById('lista-cat');
  const count  = document.getElementById('lista-count');
  if (!tbody) return;

  const rows = Array.from(tbody.querySelectorAll('tr'));

  function filtrar() {
    const q   = buscar.value.toLowerCase();
    const sup = selSup.value;
    const cat = selCat.value;
    let visible = 0;
    rows.forEach(tr => {
      const nombre = tr.querySelector('td').textContent.toLowerCase();
      const trSup  = tr.dataset.sup;
      const trCat  = tr.dataset.cat;
      const ok = (!q || nombre.includes(q)) &&
                 (!sup || trSup === sup) &&
                 (!cat || trCat === cat);
      tr.style.display = ok ? '' : 'none';
      if (ok) visible++;
    });
    count.textContent = visible + ' producto' + (visible !== 1 ? 's' : '');
  }

  buscar.addEventListener('input', filtrar);
  selSup.addEventListener('change', filtrar);
  selCat.addEventListener('change', filtrar);
  filtrar();
})();
"""
        return html_seccion, js_filtro

    lista_html, lista_js = lista_precios_html(precios_todos or [])

    def sup_cards():
        cards = ""
        for sup in res_sups:
            nombre = sup.get("supermercado", "").title()
            total  = sup.get("total_productos", 0)
            cats   = sup.get("categorias", [])
            # Precio promedio general
            if cats:
                avg = sum(c.get("precio_promedio",0)*c.get("cantidad",0) for c in cats)
                cnt = sum(c.get("cantidad",1) for c in cats)
                avg_total = avg / cnt if cnt else 0
            else:
                avg_total = 0
            
            badge_class = "badge-piala" if sup.get("supermercado") == "piala" else "badge-chanear"
            sup_url = {
                "piala":   "https://www.piala.com.ar/productos/",
                "chanear": "https://carneselchanear.com.ar/shop",
            }.get(sup.get("supermercado",""), "#")
            
            cat_rows = ""
            for cat in sorted(cats, key=lambda x: -x.get("cantidad",0))[:6]:
                cat_rows += f"""
                <div class="cat-row">
                    <span class="cat-nombre">{cat['categoria']}</span>
                    <span class="cat-precio">{fmt_precio(cat.get('precio_promedio'))} prom · {cat.get('cantidad',0)} cortes</span>
                </div>"""
            
            cards += f"""
            <div class="sup-card">
                <div class="sup-card-header">
                    <span class="badge {badge_class}">{nombre}</span>
                    <a href="{sup_url}" target="_blank" class="sup-link">Ver tienda →</a>
                </div>
                <div class="sup-stats">
                    <div class="sup-stat">
                        <div class="sup-stat-valor">{total}</div>
                        <div class="sup-stat-label">Cortes</div>
                    </div>
                    <div class="sup-stat">
                        <div class="sup-stat-valor">{fmt_precio(avg_total)}</div>
                        <div class="sup-stat-label">Precio prom/kg</div>
                    </div>
                </div>
                <div class="cat-list">{cat_rows}</div>
            </div>"""
        return cards

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CarneBot 🥩 – Monitor de precios de carnicerías</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg:        #0d0d0d;
  --surface:   #161616;
  --surface2:  #1e1e1e;
  --border:    #2a2a2a;
  --red:       #c0392b;
  --red-light: #e74c3c;
  --green:     #27ae60;
  --green-light:#2ecc71;
  --text:      #e8e8e8;
  --text-dim:  #888;
  --gold:      #d4ac0d;
  --piala:     #c0392b;
  --chanear:   #2980b9;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'IBM Plex Sans', sans-serif;
  min-height: 100vh;
}}

/* HEADER */
.header {{
  background: var(--surface);
  border-bottom: 3px solid var(--red);
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
}}

.logo {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: 2rem;
  letter-spacing: 3px;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 8px;
}}

.logo span {{ color: var(--red-light); }}
.header-fecha {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; color: var(--text-dim); }}

/* HERO */
.hero {{
  background: linear-gradient(135deg, #1a0000 0%, #0d0d0d 60%);
  border-bottom: 1px solid var(--border);
  padding: 48px 24px 40px;
  text-align: center;
}}

.hero h1 {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: clamp(2.5rem, 6vw, 5rem);
  letter-spacing: 4px;
  line-height: 1;
  margin-bottom: 12px;
}}

.hero h1 em {{
  color: var(--red-light);
  font-style: normal;
}}

.hero-sub {{
  font-size: 1rem;
  color: var(--text-dim);
  margin-bottom: 32px;
}}

/* KPI CARDS */
.kpi-row {{
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
}}

.kpi-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px 28px;
  min-width: 160px;
  text-align: center;
  transition: border-color .2s;
}}

.kpi-card:hover {{ border-color: var(--red); }}
.kpi-valor {{ font-family: 'Bebas Neue', sans-serif; font-size: 2.4rem; line-height: 1; }}
.kpi-label {{ font-size: 0.75rem; color: var(--text-dim); margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }}

.kpi-up   {{ color: var(--red-light); }}
.kpi-down {{ color: var(--green-light); }}
.kpi-neu  {{ color: var(--text); }}

/* MAIN CONTENT */
.main {{ max-width: 1200px; margin: 0 auto; padding: 40px 24px; }}

.section {{ margin-bottom: 48px; }}

.section-title {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: 1.6rem;
  letter-spacing: 3px;
  color: var(--text);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}}

.section-title::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}

/* TABS */
.tabs {{
  display: flex;
  gap: 0;
  border-bottom: 2px solid var(--border);
  margin-bottom: 24px;
}}

.tab-btn {{
  background: none;
  border: none;
  color: var(--text-dim);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.8rem;
  padding: 10px 20px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all .2s;
  text-transform: uppercase;
  letter-spacing: 1px;
}}

.tab-btn:hover {{ color: var(--text); }}
.tab-btn.active {{ color: var(--red-light); border-bottom-color: var(--red-light); }}

.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* CHART WRAPPER */
.chart-wrapper {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
  position: relative;
  height: 300px;
}}

/* TABLES */
.table-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  overflow-x: auto;
}}

table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}}

thead th {{
  background: var(--surface2);
  color: var(--text-dim);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}}

tbody tr {{
  border-bottom: 1px solid var(--border);
  transition: background .1s;
}}

tbody tr:last-child {{ border-bottom: none; }}
tbody tr:hover {{ background: var(--surface2); }}

td {{
  padding: 10px 16px;
  color: var(--text);
}}

.nombre-prod {{ font-weight: 500; }}
.precio {{ font-family: 'IBM Plex Mono', monospace; }}

/* BADGES */
.badge {{
  display: inline-block;
  padding: 3px 10px;
  border-radius: 3px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}}

.badge-piala   {{ background: rgba(192,57,43,.2); color: #e74c3c; border: 1px solid #c0392b; }}
.badge-chanear {{ background: rgba(41,128,185,.2); color: #5dade2; border: 1px solid #2980b9; }}

/* SUP CARDS */
.sup-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
}}

.sup-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
  transition: border-color .2s;
}}

.sup-card:hover {{ border-color: var(--red); }}

.sup-card-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}}

.sup-link {{
  color: var(--text-dim);
  font-size: 0.8rem;
  text-decoration: none;
  font-family: 'IBM Plex Mono', monospace;
}}

.sup-link:hover {{ color: var(--red-light); }}

.sup-stats {{
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}}

.sup-stat-valor {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: 1.8rem;
  line-height: 1;
}}

.sup-stat-label {{
  font-size: 0.7rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-top: 2px;
}}

.cat-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.85rem;
}}

.cat-row:last-child {{ border-bottom: none; }}
.cat-nombre {{ color: var(--text); }}
.cat-precio {{ color: var(--text-dim); font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }}

/* MINI STATS ROW */
.mini-stats {{
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}}

.mini-stat {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 20px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.85rem;
}}

.mini-stat strong {{ font-size: 1.1rem; }}

/* FOOTER */
footer {{
  background: var(--surface);
  border-top: 1px solid var(--border);
  text-align: center;
  padding: 32px;
  color: var(--text-dim);
  font-size: 0.8rem;
}}

footer a {{ color: var(--red-light); text-decoration: none; }}

@media (max-width: 600px) {{
  .kpi-card {{ min-width: 130px; padding: 16px 20px; }}
  .hero h1 {{ font-size: 2.5rem; }}
  .sup-grid {{ grid-template-columns: 1fr; }}
}}

/* LISTA COMPLETA DE PRECIOS */
.lista-controls {{
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
}}

.lista-input {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.85rem;
  padding: 8px 14px;
  outline: none;
  flex: 1;
  min-width: 180px;
  transition: border-color .2s;
}}

.lista-input:focus {{ border-color: var(--red); }}

.lista-select {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.8rem;
  padding: 8px 12px;
  outline: none;
  cursor: pointer;
  transition: border-color .2s;
}}

.lista-select:focus {{ border-color: var(--red); }}

.lista-count {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-dim);
  white-space: nowrap;
}}
</style>
</head>
<body>

<header class="header">
  <div class="logo">🥩 <span>Carne</span>Bot</div>
  <div class="header-fecha">Actualizado: {fecha_fmt}</div>
</header>

<section class="hero">
  <h1>Monitor de <em>Precios</em><br>de Carnicerías</h1>
  <p class="hero-sub">Seguimiento diario de precios en Piala de Patria &amp; El Chañar · Rosario, Argentina</p>
  <div class="kpi-row">
    
