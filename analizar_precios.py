"""
analizar_precios.py
===================
Lee los CSVs de los scrapers y genera los JSONs para la web.

ALMACENAMIENTO:
  data/precios_compacto.csv
    → Una fila por producto por día
    → Columnas: supermercado, codigo, nombre, categoria,
                precio_actual, unidad, fecha

RANKINGS:
    - Subidas de precio vs día anterior
    - Bajadas de precio vs día anterior
    - Comparaciones por supermercado (mismo corte de carne)
"""

import json, glob, re, csv
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DIR_DATA         = Path("data")
PRECIOS_COMPACTO = DIR_DATA / "precios_compacto.csv"

ORDEN_CATS = [
    "Carnes Vacunas", "Pollo", "Cerdo",
    "Otras Carnes", "Achuras y Menudencias",
    "Embutidos", "Elaborados", "Elaborados Premium", "Carnes",
]

PERIODOS = {"7d": 7, "30d": 30, "6m": 180, "1y": 365}


# ── CARGA ────────────────────────────────────────────────────────────────────
def cargar_csvs_hoy():
    hoy = datetime.now().strftime("%Y%m%d")
    patrones = [
        f"outputs/output_piala/piala_{hoy}*.csv",
        f"outputs/output_chanear/chanear_{hoy}*.csv",
    ]
    dfs = []
    for patron in patrones:
        for archivo in glob.glob(patron):
            try:
                df = pd.read_csv(archivo, encoding="utf-8-sig")
                dfs.append(df)
                print(f"  Cargado: {archivo} ({len(df)} prods)")
            except Exception as e:
                print(f"  ERROR cargando {archivo}: {e}")
    if not dfs:
        print("AVISO: No se encontraron CSVs de hoy. Usando últimos disponibles...")
        # Intentar con cualquier CSV disponible
        for patron_base in ["outputs/output_piala/piala_*.csv", "outputs/output_chanear/chanear_*.csv"]:
            archivos = sorted(glob.glob(patron_base))
            if archivos:
                try:
                    df = pd.read_csv(archivos[-1], encoding="utf-8-sig")
                    dfs.append(df)
                    print(f"  Cargado: {archivos[-1]} ({len(df)} prods)")
                except Exception:
                    pass
    if not dfs:
        return None
    df = pd.concat(dfs, ignore_index=True)
    print(f"  Total productos: {len(df)}")
    return df


def preparar_df_dia(df_raw, fecha_str):
    cols = ["supermercado", "codigo", "nombre", "categoria", "precio_actual", "unidad"]
    cols = [c for c in cols if c in df_raw.columns]
    df = df_raw[cols].copy()
    df["precio_actual"] = pd.to_numeric(df["precio_actual"], errors="coerce")
    df = df.dropna(subset=["precio_actual"])
    df = df[df["precio_actual"] > 0]
    df["codigo"] = df["codigo"].astype(str)
    df["clave"]  = df["supermercado"] + "_" + df["codigo"].str.strip() + "_" + df["nombre"].str.strip().str.lower()
    df = df.drop_duplicates(subset=["clave"], keep="first")
    df["fecha"] = fecha_str
    return df


# ── ALMACENAMIENTO ───────────────────────────────────────────────────────────
def guardar_compacto(df_dia, fecha_str):
    DIR_DATA.mkdir(parents=True, exist_ok=True)
    cols_guardar = ["supermercado", "codigo", "nombre", "categoria", "precio_actual", "unidad", "fecha", "clave"]
    df_guardar = df_dia[[c for c in cols_guardar if c in df_dia.columns]].copy()

    if PRECIOS_COMPACTO.exists():
        df_hist = pd.read_csv(PRECIOS_COMPACTO, dtype={"codigo": str, "fecha": str})
        if "clave" not in df_hist.columns:
            df_hist["clave"] = df_hist["supermercado"] + "_" + df_hist["codigo"].str.strip() + "_" + df_hist["nombre"].str.strip().str.lower()
        df_hist = df_hist[df_hist["fecha"] != fecha_str]
        df_nuevo = pd.concat([df_hist, df_guardar], ignore_index=True)
    else:
        df_nuevo = df_guardar

    df_nuevo.to_csv(PRECIOS_COMPACTO, index=False)
    kb = PRECIOS_COMPACTO.stat().st_size / 1024
    print(f"  precios_compacto.csv: {len(df_nuevo)} filas | {kb:.0f} KB")
    return df_nuevo


# ── COMPARACIÓN ──────────────────────────────────────────────────────────────
def snapshot_anterior(df_hist, fecha_hoy):
    fechas = sorted(df_hist["fecha"].unique(), reverse=True)
    for f in fechas:
        if f < fecha_hoy:
            df = df_hist[df_hist["fecha"] == f].copy()
            print(f"  Snapshot anterior: {f} ({len(df)} prods)")
            return df
    return None


def snapshot_en_fecha(df_hist, fecha_objetivo):
    fechas = sorted(df_hist["fecha"].unique())
    candidato = None
    for f in fechas:
        if f <= fecha_objetivo:
            candidato = f
    if candidato is None:
        return None
    return df_hist[df_hist["fecha"] == candidato].copy()


def calcular_variacion(df_hoy, df_antes):
    df_h = df_hoy[["clave", "nombre", "supermercado", "categoria", "precio_actual"]].copy()
    df_h = df_h.rename(columns={"precio_actual": "precio_hoy"})
    df_a = df_antes[["clave", "precio_actual"]].rename(columns={"precio_actual": "precio_antes"})
    df = pd.merge(df_h, df_a, on="clave", how="inner")
    df = df.dropna(subset=["precio_hoy", "precio_antes"])
    df = df[df["precio_antes"] > 0]
    df["diff_abs"] = (df["precio_hoy"] - df["precio_antes"]).round(2)
    df["diff_pct"] = ((df["diff_abs"] / df["precio_antes"]) * 100).round(2)
    return df


def top_productos(df_var, n=20, ascendente=False):
    df = df_var.sort_values("diff_pct", ascending=ascendente).head(n)
    return df[["clave", "nombre", "supermercado", "categoria",
               "precio_antes", "precio_hoy", "diff_abs", "diff_pct"]].to_dict("records")


# ── COMPARATIVA ENTRE SUPERMERCADOS ──────────────────────────────────────────
def comparar_supermercados(df_dia):
    """
    Encuentra productos con nombres similares entre diferentes supermercados
    y compara sus precios.
    """
    comparativas = []
    
    # Normalizar nombres para comparar
    df = df_dia.copy()
    df["nombre_norm"] = df["nombre"].str.upper().str.strip()
    df["nombre_norm"] = df["nombre_norm"].str.replace(r"\s+", " ", regex=True)
    
    supermercados = df["supermercado"].unique()
    if len(supermercados) < 2:
        return comparativas
    
    # Buscar nombres exactos o muy similares entre supermercados
    for _, row1 in df[df["supermercado"] == supermercados[0]].iterrows():
        for _, row2 in df[df["supermercado"] == supermercados[1]].iterrows():
            nombre1 = row1["nombre_norm"]
            nombre2 = row2["nombre_norm"]
            
            # Match exacto o si uno contiene al otro
            if nombre1 == nombre2 or nombre1 in nombre2 or nombre2 in nombre1:
                if row1["precio_actual"] and row2["precio_actual"]:
                    diff = row2["precio_actual"] - row1["precio_actual"]
                    diff_pct = (diff / row1["precio_actual"]) * 100
                    comparativas.append({
                        "nombre": row1["nombre"],
                        "supermercado_1": row1["supermercado"],
                        "precio_1": row1["precio_actual"],
                        "supermercado_2": row2["supermercado"],
                        "precio_2": row2["precio_actual"],
                        "diff_abs": round(diff, 2),
                        "diff_pct": round(diff_pct, 2),
                        "mas_barato": row1["supermercado"] if row1["precio_actual"] < row2["precio_actual"] else row2["supermercado"],
                    })
    
    # Ordenar por diferencia absoluta (más interesantes primero)
    comparativas.sort(key=lambda x: abs(x["diff_abs"]), reverse=True)
    return comparativas[:20]


# ── RESUMEN POR SUPERMERCADO ──────────────────────────────────────────────────
def resumen_por_supermercado(df_dia):
    resumen = []
    for sup, grp in df_dia.groupby("supermercado"):
        por_cat = grp.groupby("categoria")["precio_actual"].agg(["mean", "min", "max", "count"]).reset_index()
        por_cat.columns = ["categoria", "precio_promedio", "precio_min", "precio_max", "cantidad"]
        por_cat["precio_promedio"] = por_cat["precio_promedio"].round(2)
        resumen.append({
            "supermercado": sup,
            "total_productos": len(grp),
            "categorias": por_cat.to_dict("records"),
        })
    return resumen


# ── GRÁFICOS ──────────────────────────────────────────────────────────────────
def generar_graficos_data(df_hist):
    if df_hist.empty:
        return {}

    df_hist = df_hist.copy()
    # Normalizar fecha a YYYYMMDD si viene en otro formato
    df_hist["fecha_dt"] = pd.to_datetime(df_hist["fecha"], format="%Y%m%d", errors="coerce")
    df_hist = df_hist.dropna(subset=["fecha_dt"])
    df_hist = df_hist.sort_values(["fecha_dt", "clave"])

    hoy = pd.Timestamp.now().normalize()
    resultado = {}

    for periodo, dias in PERIODOS.items():
        fecha_inicio = hoy - timedelta(days=dias)
        df_p = df_hist[df_hist["fecha_dt"] >= fecha_inicio].copy()
        fechas = sorted(df_p["fecha_dt"].unique())

        if not fechas:
            resultado[periodo] = {"total": [], "supermercados": {}}
            continue

        fecha_str_0 = fechas[0].strftime("%Y-%m-%d")
        serie_total = [{"fecha": fecha_str_0, "pct": 0.0}]
        acum = 0.0

        for i in range(1, len(fechas)):
            dv = calcular_variacion(
                df_p[df_p["fecha_dt"] == fechas[i]],
                df_p[df_p["fecha_dt"] == fechas[i - 1]]
            )
            var = float(dv["diff_pct"].mean()) if not dv.empty else 0.0
            acum = round(acum + var, 2)
            serie_total.append({"fecha": fechas[i].strftime("%Y-%m-%d"), "pct": acum})

        series_sups = {}
        for sup in df_p["supermercado"].unique():
            df_sup = df_p[df_p["supermercado"] == sup]
            serie = [{"fecha": fecha_str_0, "pct": 0.0}]
            acum_s = 0.0
            for i in range(1, len(fechas)):
                dv = calcular_variacion(
                    df_sup[df_sup["fecha_dt"] == fechas[i]],
                    df_sup[df_sup["fecha_dt"] == fechas[i - 1]]
                )
                var = float(dv["diff_pct"].mean()) if not dv.empty else 0.0
                acum_s = round(acum_s + var, 2)
                serie.append({"fecha": fechas[i].strftime("%Y-%m-%d"), "pct": acum_s})
            series_sups[sup] = serie

        resultado[periodo] = {"total": serie_total, "supermercados": series_sups}

    return resultado


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    import sys
    solo_graficos = "--solo-graficos" in sys.argv

    print(f"\n{'='*60}")
    print(f"  ANÁLISIS CARNEBOT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    fecha_hoy = datetime.now().strftime("%Y%m%d")
    DIR_DATA.mkdir(parents=True, exist_ok=True)

    if solo_graficos:
        if not PRECIOS_COMPACTO.exists():
            print("ERROR: No existe precios_compacto.csv")
            return
        df_hist = pd.read_csv(PRECIOS_COMPACTO, dtype={"codigo": str, "fecha": str})
        if "clave" not in df_hist.columns:
            df_hist["clave"] = df_hist["supermercado"] + "_" + df_hist["codigo"].str.strip() + "_" + df_hist["nombre"].str.strip().str.lower()
        fecha_hoy = sorted(df_hist["fecha"].unique())[-1]
        df_dia = df_hist[df_hist["fecha"] == fecha_hoy].copy()
        print(f"  Usando fecha más reciente: {fecha_hoy} ({len(df_dia)} prods)")
    else:
        print("[1/5] Cargando CSVs ...")
        df_raw = cargar_csvs_hoy()
        if df_raw is None:
            print("ERROR: No se encontraron archivos de datos.")
            return
        df_dia = preparar_df_dia(df_raw, fecha_hoy)
        print(f"\n[2/5] Guardando precios_compacto ({len(df_dia)} productos) ...")
        df_hist = guardar_compacto(df_dia, fecha_hoy)

    print("\n[3/5] Calculando variaciones y rankings ...")

    resumen = {
        "fecha":             fecha_hoy,
        "total_productos":   len(df_dia),
        "variacion_dia":     None,
        "variacion_7d":      None,
        "variacion_mes":     None,
        "productos_subieron_dia": 0,
        "productos_bajaron_dia":  0,
        "productos_sin_cambio_dia": 0,
        "ranking_subida_dia":  [],
        "ranking_baja_dia":    [],
        "comparativa_supermercados": [],
        "resumen_supermercados": [],
    }

    # Día anterior
    df_ayer = snapshot_anterior(df_hist, fecha_hoy)
    if df_ayer is not None:
        dv = calcular_variacion(df_dia, df_ayer)
        if not dv.empty:
            resumen["variacion_dia"]            = round(float(dv["diff_pct"].mean()), 2)
            resumen["productos_subieron_dia"]   = int((dv["diff_pct"] > 0).sum())
            resumen["productos_bajaron_dia"]    = int((dv["diff_pct"] < 0).sum())
            resumen["productos_sin_cambio_dia"] = int((dv["diff_pct"] == 0).sum())
            resumen["ranking_subida_dia"]       = top_productos(dv, 20, False)
            resumen["ranking_baja_dia"]         = top_productos(dv, 20, True)
            print(f"  Variación día: {resumen['variacion_dia']}%")

    # 7 días
    f7 = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    df_7d = snapshot_en_fecha(df_hist, f7)
    if df_7d is not None:
        dv = calcular_variacion(df_dia, df_7d)
        if not dv.empty:
            resumen["variacion_7d"] = round(float(dv["diff_pct"].mean()), 2)
            with open(DIR_DATA / "ranking_7d.json", "w", encoding="utf-8") as f:
                json.dump(top_productos(dv, 30, False), f, ensure_ascii=False, indent=2)

    # Comparativa supermercados
    resumen["comparativa_supermercados"] = comparar_supermercados(df_dia)
    resumen["resumen_supermercados"]     = resumen_por_supermercado(df_dia)

    print("\n[4/5] Guardando resumen.json ...")
    with open(DIR_DATA / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    # Rankings separados
    with open(DIR_DATA / "ranking_dia.json", "w", encoding="utf-8") as f:
        json.dump({
            "subidas": resumen["ranking_subida_dia"],
            "bajadas": resumen["ranking_baja_dia"],
        }, f, ensure_ascii=False, indent=2)

    print("\n[5/5] Generando graficos.json ...")
    graficos = generar_graficos_data(df_hist)
    with open(DIR_DATA / "graficos.json", "w", encoding="utf-8") as f:
        json.dump(graficos, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  LISTO — {resumen['total_productos']} productos")
    if resumen["variacion_dia"] is not None:
        emoji = "📈" if resumen["variacion_dia"] > 0 else "📉"
        print(f"  Día: {emoji} {resumen['variacion_dia']}%")
    if resumen["variacion_7d"] is not None:
        emoji = "📈" if resumen["variacion_7d"] > 0 else "📉"
        print(f"  7d:  {emoji} {resumen['variacion_7d']}%")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
