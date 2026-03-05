"""
generar_datos_muestra.py
Genera CSVs de muestra con datos reales observados en las páginas.
Útil para testing local y para inicializar el repositorio.
"""
import json, csv
from pathlib import Path
from datetime import datetime, timedelta
import random

# Datos REALES de piala.com.ar (scrapeados manualmente)
PIALA_PRODUCTOS = [
    {"nombre": "Picada común",                    "precio": 9000,  "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Brazuelo con hueso",               "precio": 12000, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Pata de ternera 7kg",              "precio": 13332, "unidad": "unidad","categoria": "Carnes"},
    {"nombre": "Lomo",                             "precio": 26200, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Falda",                            "precio": 11800, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Entrecot común / Roast beef",      "precio": 13000, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Entraña fina",                     "precio": 29500, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Cuadril",                          "precio": 19300, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Costeleta grande",                 "precio": 12400, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Costeleta chica",                  "precio": 16800, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Colita de cuadril / Punta de vacío","precio": 22700,"unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Cima de ternera",                  "precio": 16500, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Cabeza de lomo / Bola de lomo",    "precio": 16700, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Brazuelo sin hueso",               "precio": 16300, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Vacío",                            "precio": 17500, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Nalga",                            "precio": 18200, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Tapa de asado",                    "precio": 14900, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Asado",                            "precio": 15600, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Matambre",                         "precio": 21000, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Peceto",                           "precio": 20500, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Osobuco",                          "precio": 10800, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Tortuguita",                       "precio": 19800, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Tapa de nalga",                    "precio": 19100, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Paleta",                           "precio": 14200, "unidad": "kg",    "categoria": "Carnes"},
    {"nombre": "Garrón",                           "precio": 8500,  "unidad": "kg",    "categoria": "Carnes"},
]

# Datos REALES de carneselchanear.com.ar (scrapeados manualmente)
CHANEAR_PRODUCTOS = [
    # Carnes Vacunas
    {"codigo": "128", "nombre": "Azotillo",                         "precio": 8300,  "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "124", "nombre": "Bife a 7 costillas",               "precio": 16400, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "175", "nombre": "Bife de entrecot especial madurado","precio": 28000, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "101", "nombre": "Bola de lomo",                     "precio": 16700, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "111", "nombre": "Brazuelo con hueso",               "precio": 13700, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "100", "nombre": "Brazuelo por pieza entera",        "precio": 11800, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "112", "nombre": "Brazuelo sin hueso",               "precio": 15800, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "125", "nombre": "Costeleta con lomo o T-Bone",      "precio": 18500, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "130", "nombre": "Costeleta del medio",              "precio": 16500, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "123", "nombre": "Costeletas grandes",               "precio": 12900, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "132", "nombre": "Costilla de TH",                   "precio": 23200, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "104", "nombre": "Cuadril",                          "precio": 19300, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "109", "nombre": "Cuadril con punta",                "precio": 19600, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "139", "nombre": "Entraña fina",                     "precio": 30500, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "120", "nombre": "Entrecot común",                   "precio": 13900, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "122", "nombre": "Entrecot especial",                "precio": 23900, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "116", "nombre": "Falda",                            "precio": 10900, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "103", "nombre": "Lomo",                             "precio": 27800, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "102", "nombre": "Nalga",                            "precio": 18500, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "117", "nombre": "Paleta",                           "precio": 14100, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "106", "nombre": "Peceto",                           "precio": 21000, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "118", "nombre": "Picada común",                     "precio": 9200,  "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "105", "nombre": "Tapa de asado",                    "precio": 15400, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "108", "nombre": "Tapa de nalga",                    "precio": 19800, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "107", "nombre": "Vacío",                            "precio": 18200, "unidad": "kg", "categoria": "Carnes Vacunas"},
    {"codigo": "114", "nombre": "Matambre",                         "precio": 21500, "unidad": "kg", "categoria": "Carnes Vacunas"},
    # Pollo
    {"codigo": "201", "nombre": "Pollo entero",                     "precio": 6800,  "unidad": "kg", "categoria": "Pollo"},
    {"codigo": "202", "nombre": "Pechuga de pollo",                 "precio": 9500,  "unidad": "kg", "categoria": "Pollo"},
    {"codigo": "203", "nombre": "Muslo y contramuslo",              "precio": 7200,  "unidad": "kg", "categoria": "Pollo"},
    {"codigo": "204", "nombre": "Alitas de pollo",                  "precio": 6500,  "unidad": "kg", "categoria": "Pollo"},
    # Cerdo
    {"codigo": "301", "nombre": "Bondiola de cerdo",                "precio": 12800, "unidad": "kg", "categoria": "Cerdo"},
    {"codigo": "302", "nombre": "Paleta de cerdo",                  "precio": 10500, "unidad": "kg", "categoria": "Cerdo"},
    {"codigo": "303", "nombre": "Costillas de cerdo",               "precio": 11200, "unidad": "kg", "categoria": "Cerdo"},
    # Embutidos
    {"codigo": "601", "nombre": "Chorizo parrillero",               "precio": 14500, "unidad": "kg", "categoria": "Embutidos"},
    {"codigo": "602", "nombre": "Morcilla",                         "precio": 9800,  "unidad": "kg", "categoria": "Embutidos"},
    {"codigo": "603", "nombre": "Salchicha parrillera",             "precio": 12000, "unidad": "kg", "categoria": "Embutidos"},
    # Achuras
    {"codigo": "501", "nombre": "Chinchulines",                     "precio": 9200,  "unidad": "kg", "categoria": "Achuras y Menudencias"},
    {"codigo": "502", "nombre": "Mollejas",                         "precio": 18000, "unidad": "kg", "categoria": "Achuras y Menudencias"},
    {"codigo": "503", "nombre": "Riñones",                          "precio": 7500,  "unidad": "kg", "categoria": "Achuras y Menudencias"},
    {"codigo": "504", "nombre": "Corazón",                          "precio": 8800,  "unidad": "kg", "categoria": "Achuras y Menudencias"},
    # Elaborados
    {"codigo": "701", "nombre": "Milanesa de nalga",                "precio": 22000, "unidad": "kg", "categoria": "Elaborados"},
    {"codigo": "702", "nombre": "Hamburguesa casera",               "precio": 16500, "unidad": "kg", "categoria": "Elaborados"},
    {"codigo": "801", "nombre": "Bife de chorizo premium madurado", "precio": 32000, "unidad": "kg", "categoria": "Elaborados Premium"},
]

CAMPOS = ["supermercado", "codigo", "nombre", "categoria", "precio_actual", "unidad", "imagen", "url", "fecha"]

def generar_csv(productos, supermercado, output_dir, nombre_archivo, fecha_str, variacion=0.0):
    output_dir.mkdir(parents=True, exist_ok=True)
    ruta = output_dir / f"{nombre_archivo}_{fecha_str}.csv"
    rows = []
    for p in productos:
        precio_mod = p["precio"] * (1 + variacion + random.uniform(-0.005, 0.005))
        rows.append({
            "supermercado": supermercado,
            "codigo":       p.get("codigo", ""),
            "nombre":       p["nombre"],
            "categoria":    p["categoria"],
            "precio_actual": round(precio_mod, 2),
            "unidad":       p["unidad"],
            "imagen":       "",
            "url":          "",
            "fecha":        fecha_str.replace("_", "") + " 08:00",
        })
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Generado: {ruta} ({len(rows)} prods)")
    return ruta

def main():
    random.seed(42)
    hoy = datetime.now()
    
    # Generar historial de 35 días (para poder mostrar gráficos de 30d)
    for dias_atras in range(35, -1, -1):
        fecha = hoy - timedelta(days=dias_atras)
        fecha_str = fecha.strftime("%Y%m%d_%H%M")
        fecha_data = fecha.strftime("%Y%m%d")
        
        # Variación acumulada simulada (inflación gradual ~2% mensual)
        variacion_base = dias_atras * -0.0007  # más reciente = más alto
        
        generar_csv(
            PIALA_PRODUCTOS, "piala",
            Path("outputs/output_piala"), "piala",
            fecha_str, variacion_base + random.uniform(-0.003, 0.003)
        )
        generar_csv(
            CHANEAR_PRODUCTOS, "chanear",
            Path("outputs/output_chanear"), "chanear",
            fecha_str, variacion_base + random.uniform(-0.003, 0.003)
        )
    
    print(f"\n✅ Datos de muestra generados para {36} días.")

if __name__ == "__main__":
    main()
