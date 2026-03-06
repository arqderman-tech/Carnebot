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
    def comparativas_rows(comps):
        if not comps:
            return '<tr><td colspan="5" style="text-align:center;color:#666;padding:20px">Sin cortes en común para comparar aún</td></tr>'
        rows = ""
        for i, c in enumerate(comps):
            mas_barato = c.get("mas_barato", "")
            oculto = ' class="comp-extra" style="display:none"' if i >= 10 else ''
            rows += f"""
            <tr{oculto}>
                <td class="nombre-prod">{c.get('nombre','')}</td>
                <td class="precio">{fmt_precio(c.get('precio_1'))}<br><small style="color:#888">{c.get('supermercado_1','')}</small></td>
                <td class="precio">{fmt_precio(c.get('precio_2'))}<br><small style="color:#888">{c.get('supermercado_2','')}</small></td>
                <td style="color:{'#2ecc71' if c.get('diff_pct',0)<0 else '#e74c3c'};font-weight:700">{fmt_pct(c.get('diff_pct'))}</td>
                <td><span class="badge badge-{'piala' if mas_barato=='piala' else 'chanear'}">{mas_barato.title()} 🏆</span></td>
            </tr>"""
        extra = len(comps) - 10
        if extra > 0:
            rows += f'<tr id="comp-ver-mas-row"><td colspan="5" style="text-align:center;padding:12px"><button onclick="verMasComp()" style="background:none;border:1px solid #555;color:#ccc;padding:8px 20px;border-radius:6px;cursor:pointer;font-size:14px">Ver {extra} más ▼</button></td></tr>'
        return rows

    # Lista completa de precios por local
    def lista_precios_html(productos):
        if not productos:
            return "", ""

        NOMBRE_LOCAL = {
            "piala":   ("Piala de Patria", "badge-piala"),
            "chanear": ("El Chañar",        "badge-chanear"),
        }

        # Quedarse solo con el precio más reciente por (supermercado, nombre)
        # precios_compacto tiene múltiples fechas — deduplicar
        from collections import defaultdict
        ultimos = {}  # clave (sup, nombre) → fila con fecha más alta
        for p in productos:
            key = (p["supermercado"], p["nombre"])
            fecha = p.get("fecha", "")
            if key not in ultimos or fecha > ultimos[key].get("fecha", ""):
                ultimos[key] = p
        productos = list(ultimos.values())

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

// ── Ver más comparativa ──────────────────────────────────────────
function verMasComp() {
  document.querySelectorAll('.comp-extra').forEach(tr => tr.style.display = '');
  const btn = document.getElementById('comp-ver-mas-row');
  if (btn) btn.style.display = 'none';
}

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
    <div class="kpi-card">
      <div class="kpi-valor kpi-neu">{total_prods}</div>
      <div class="kpi-label">Cortes monitoreados</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-valor {'kpi-up' if (var_dia or 0) > 0 else 'kpi-down' if (var_dia or 0) < 0 else 'kpi-neu'}">{fmt_pct(var_dia, arrow=False)}</div>
      <div class="kpi-label">Var. hoy vs ayer</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-valor {'kpi-up' if (var_7d or 0) > 0 else 'kpi-down' if (var_7d or 0) < 0 else 'kpi-neu'}">{fmt_pct(var_7d, arrow=False)}</div>
      <div class="kpi-label">Var. 7 días</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-valor" style="color:#e74c3c">{subieron}</div>
      <div class="kpi-label">Subieron hoy</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-valor" style="color:#2ecc71">{bajaron}</div>
      <div class="kpi-label">Bajaron hoy</div>
    </div>
  </div>
</section>

<main class="main">

  <!-- SUPERMERCADOS -->
  <section class="section">
    <h2 class="section-title">📍 Carnicerías</h2>
    <div class="sup-grid">
      {sup_cards()}
    </div>
  </section>

  <!-- GRÁFICOS -->
  <section class="section">
    <h2 class="section-title">📈 Evolución de precios</h2>
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('tab-7d', this)">7 días</button>
      <button class="tab-btn" onclick="switchTab('tab-30d', this)">30 días</button>
    </div>
    <div id="tab-7d" class="tab-content active">
      <div class="chart-wrapper"><canvas id="chart7d"></canvas></div>
    </div>
    <div id="tab-30d" class="tab-content">
      <div class="chart-wrapper"><canvas id="chart30d"></canvas></div>
    </div>
  </section>

  <!-- RANKINGS HOY -->
  <section class="section">
    <h2 class="section-title">🔥 Movimientos de hoy</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;" class="ranking-grid">
      <div>
        <h3 style="font-family:'Bebas Neue';letter-spacing:2px;color:#e74c3c;margin-bottom:12px;font-size:1.1rem">▲ MÁS SUBIERON</h3>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Producto</th><th>Carnicería</th><th>Antes</th><th>Ahora</th><th>Var.</th>
            </tr></thead>
            <tbody>{ranking_rows((ranking_dia or {{}}).get('subidas', []), 10)}</tbody>
          </table>
        </div>
      </div>
      <div>
        <h3 style="font-family:'Bebas Neue';letter-spacing:2px;color:#2ecc71;margin-bottom:12px;font-size:1.1rem">▼ MÁS BAJARON</h3>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Producto</th><th>Carnicería</th><th>Antes</th><th>Ahora</th><th>Var.</th>
            </tr></thead>
            <tbody>{ranking_rows((ranking_dia or {{}}).get('bajadas', []), 10)}</tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- COMPARATIVA -->
  <section class="section">
    <h2 class="section-title">⚖️ Comparativa entre carnicerías</h2>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Corte</th>
          <th>Piala</th>
          <th>El Chañar</th>
          <th>Diferencia</th>
          <th>Más barato</th>
        </tr></thead>
        <tbody>{comparativas_rows(comparativas)}</tbody>
      </table>
    </div>
  </section>

  <!-- RANKING 7D -->
  <section class="section">
    <h2 class="section-title">📊 Top subidas · últimos 7 días</h2>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Producto</th><th>Carnicería</th><th>Precio hace 7d</th><th>Precio actual</th><th>Var. 7d</th>
        </tr></thead>
        <tbody>{ranking_rows(ranking_7d or [], 15)}</tbody>
      </table>
    </div>
  </section>

{lista_html}

</main>

<footer>
  <p>CarneBot · Monitor de precios de carnicerías en Rosario, Argentina</p>
  <p style="margin-top:8px">
    <a href="https://www.piala.com.ar/productos/" target="_blank">Piala de Patria</a> ·
    <a href="https://carneselchanear.com.ar/shop" target="_blank">Carnes El Chañar</a> ·
    Datos actualizados diariamente via GitHub Actions
  </p>
  <p style="margin-top:8px;color:#555;font-size:0.7rem">Los precios son de referencia. Verificar en cada local.</p>
</footer>

<script>
// ── Tabs ─────────────────────────────────────────────────────────────────
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}

// ── Chart helper ────────────────────────────────────────────────────────
const CHART_DEFAULTS = {{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{
    legend: {{
      labels: {{ color: '#aaa', font: {{ family: 'IBM Plex Mono', size: 11 }} }}
    }},
    tooltip: {{
      backgroundColor: '#1e1e1e',
      titleColor: '#e8e8e8',
      bodyColor: '#aaa',
      borderColor: '#333',
      borderWidth: 1,
      callbacks: {{
        label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y > 0 ? '+' : ''}}${{ctx.parsed.y.toFixed(2)}}%`
      }}
    }}
  }},
  scales: {{
    x: {{
      ticks: {{ color: '#666', font: {{ family: 'IBM Plex Mono', size: 10 }} }},
      grid:  {{ color: '#1e1e1e' }}
    }},
    y: {{
      ticks: {{
        color: '#666',
        font: {{ family: 'IBM Plex Mono', size: 10 }},
        callback: v => (v>0?'+':'')+v.toFixed(1)+'%'
      }},
      grid: {{ color: '#1e1e1e' }},
    }}
  }}
}};

function makeChart(canvasId, labels, datasets) {{
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  new Chart(ctx, {{
    type: 'line',
    data: {{ labels, datasets }},
    options: CHART_DEFAULTS
  }});
}}

// ── 7d Chart ────────────────────────────────────────────────────────────
makeChart('chart7d', {labels_7d}, [
  {{
    label: 'Total',
    data: {vals_7d_total},
    borderColor: '#e74c3c',
    backgroundColor: 'rgba(231,76,60,.08)',
    borderWidth: 2.5,
    pointRadius: 4,
    pointBackgroundColor: '#e74c3c',
    fill: true,
    tension: 0.3,
  }},
  {{
    label: 'Piala',
    data: {vals_7d_piala},
    borderColor: '#c0392b',
    borderWidth: 1.5,
    borderDash: [4,3],
    pointRadius: 3,
    pointBackgroundColor: '#c0392b',
    fill: false,
    tension: 0.3,
  }},
  {{
    label: 'El Chañar',
    data: {vals_7d_chanear},
    borderColor: '#2980b9',
    borderWidth: 1.5,
    borderDash: [4,3],
    pointRadius: 3,
    pointBackgroundColor: '#2980b9',
    fill: false,
    tension: 0.3,
  }},
]);

// ── 30d Chart ────────────────────────────────────────────────────────────
makeChart('chart30d', {labels_30d}, [
  {{
    label: 'Total',
    data: {vals_30d_total},
    borderColor: '#e74c3c',
    backgroundColor: 'rgba(231,76,60,.08)',
    borderWidth: 2.5,
    pointRadius: 3,
    pointBackgroundColor: '#e74c3c',
    fill: true,
    tension: 0.4,
  }},
  {{
    label: 'Piala',
    data: {vals_30d_piala},
    borderColor: '#c0392b',
    borderWidth: 1.5,
    borderDash: [4,3],
    pointRadius: 2,
    pointBackgroundColor: '#c0392b',
    fill: false,
    tension: 0.4,
  }},
  {{
    label: 'El Chañar',
    data: {vals_30d_chanear},
    borderColor: '#2980b9',
    borderWidth: 1.5,
    borderDash: [4,3],
    pointRadius: 2,
    pointBackgroundColor: '#2980b9',
    fill: false,
    tension: 0.4,
  }},
]);
{lista_js}
</script>
</body>
</html>"""


def main():
    DIR_DOCS.mkdir(exist_ok=True)

    resumen        = leer_json("resumen.json", {})
    graficos       = leer_json("graficos.json", {})
    ranking_d      = leer_json("ranking_dia.json", {})
    ranking_7d     = leer_json("ranking_7d.json", [])
    precios_todos  = leer_csv("precios_compacto.csv")

    html = generar_html(resumen, graficos, ranking_d, ranking_7d, precios_todos)
    out = DIR_DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ Web generada → {out}")


if __name__ == "__main__":
    main()
