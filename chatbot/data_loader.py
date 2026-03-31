"""
Modulo para cargar y consultar archivos CSV y JSON del directorio de datos.
"""

import os
import json
import pandas as pd
from config import DATA_DIR


def listar_archivos():
    """Devuelve lista de archivos CSV y JSON disponibles."""
    if not os.path.isdir(DATA_DIR):
        return []
    archivos = []
    for f in os.listdir(DATA_DIR):
        if f.endswith((".csv", ".json")):
            ruta = os.path.join(DATA_DIR, f)
            tamano = os.path.getsize(ruta)
            archivos.append({"nombre": f, "tamano_kb": round(tamano / 1024, 1)})
    return archivos


def leer_csv(nombre_archivo, filtros=None, limite=50):
    """Lee un CSV y opcionalmente aplica filtros. Devuelve dict con datos."""
    ruta = os.path.join(DATA_DIR, nombre_archivo)
    if not os.path.isfile(ruta) or not nombre_archivo.endswith(".csv"):
        return {"error": f"Archivo '{nombre_archivo}' no encontrado o no es CSV."}

    df = pd.read_csv(ruta, encoding="utf-8-sig")

    if filtros:
        for columna, valor in filtros.items():
            if columna in df.columns:
                df = df[df[columna].astype(str).str.contains(str(valor), case=False, na=False)]

    total = len(df)
    df = df.head(limite)

    return {
        "archivo": nombre_archivo,
        "columnas": list(df.columns),
        "total_filas": total,
        "filas_mostradas": len(df),
        "datos": df.to_dict(orient="records"),
    }


def leer_json(nombre_archivo):
    """Lee un archivo JSON y devuelve su contenido."""
    ruta = os.path.join(DATA_DIR, nombre_archivo)
    if not os.path.isfile(ruta) or not nombre_archivo.endswith(".json"):
        return {"error": f"Archivo '{nombre_archivo}' no encontrado o no es JSON."}

    with open(ruta, "r", encoding="utf-8") as f:
        datos = json.load(f)

    resumen = {}
    if isinstance(datos, list):
        resumen = {"tipo": "lista", "total_elementos": len(datos), "muestra": datos[:20]}
    elif isinstance(datos, dict):
        resumen = {"tipo": "diccionario", "claves": list(datos.keys())[:30]}
        # Incluir valores si no son demasiado grandes
        preview = {}
        for k, v in list(datos.items())[:20]:
            if isinstance(v, (str, int, float, bool)):
                preview[k] = v
            elif isinstance(v, list):
                preview[k] = f"[lista de {len(v)} elementos]"
            elif isinstance(v, dict):
                preview[k] = f"{{dict con {len(v)} claves}}"
        resumen["preview"] = preview

    return {"archivo": nombre_archivo, "contenido": resumen}


def resumen_datos():
    """Genera un resumen de todos los archivos de datos disponibles."""
    archivos = listar_archivos()
    resumen = []
    for arch in archivos:
        nombre = arch["nombre"]
        if nombre.endswith(".csv"):
            try:
                ruta = os.path.join(DATA_DIR, nombre)
                df = pd.read_csv(ruta, encoding="utf-8-sig", nrows=5)
                resumen.append({
                    "archivo": nombre,
                    "tipo": "CSV",
                    "columnas": list(df.columns),
                    "tamano_kb": arch["tamano_kb"],
                })
            except Exception:
                resumen.append({"archivo": nombre, "tipo": "CSV", "error": "No se pudo leer"})
        elif nombre.endswith(".json"):
            resumen.append({
                "archivo": nombre,
                "tipo": "JSON",
                "tamano_kb": arch["tamano_kb"],
            })
    return resumen
