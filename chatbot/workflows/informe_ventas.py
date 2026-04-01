"""
Modulo de generacion de informes de ventas para empresa de oficina.
Utiliza el CSV de empleados como fuente de datos base y genera metricas realistas.
"""

import csv
import os
import random
from datetime import datetime, timezone, date, timedelta
from collections import defaultdict


# Ruta al CSV de empleados (fuente de datos base)
_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "datos",
    "empleados.csv",
)

# Productos de oficina para simulacion de ventas
_PRODUCTOS_CATALOGO = [
    {"nombre": "Papel A4 500 hojas", "precio": 5.50, "categoria": "Consumibles"},
    {"nombre": "Boligrafo azul (caja x12)", "precio": 8.90, "categoria": "Escritura"},
    {"nombre": "Carpeta archivadora", "precio": 12.00, "categoria": "Archivo"},
    {"nombre": "Toner impresora laser", "precio": 45.00, "categoria": "Consumibles"},
    {"nombre": "Silla ergonomica", "precio": 220.00, "categoria": "Mobiliario"},
    {"nombre": "Escritorio esquinero", "precio": 380.00, "categoria": "Mobiliario"},
    {"nombre": "Monitor 24 pulgadas", "precio": 290.00, "categoria": "Tecnologia"},
    {"nombre": "Teclado inalambrico", "precio": 55.00, "categoria": "Tecnologia"},
    {"nombre": "Mouse optico", "precio": 25.00, "categoria": "Tecnologia"},
    {"nombre": "Cuaderno A4 100 hojas", "precio": 4.20, "categoria": "Escritura"},
    {"nombre": "Post-it pack x5 colores", "precio": 6.80, "categoria": "Organizacion"},
    {"nombre": "Resaltadores (pack x6)", "precio": 7.50, "categoria": "Escritura"},
    {"nombre": "Perforadora industrial", "precio": 35.00, "categoria": "Archivo"},
    {"nombre": "Grapadora metalica", "precio": 18.00, "categoria": "Archivo"},
    {"nombre": "Lapiz portaminas 0.5", "precio": 3.50, "categoria": "Escritura"},
]

# Semilla determinista por periodo para reproducibilidad
_SEED_BASE = 42


def _leer_empleados() -> list:
    """Lee el CSV de empleados y devuelve lista de dicts."""
    empleados = []
    try:
        with open(_CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                empleados.append(dict(row))
    except FileNotFoundError:
        # Fallback si el CSV no existe
        empleados = [
            {"id": "1", "nombre": "Vendedor Demo", "departamento": "Ventas",
             "cargo": "Ejecutivo de Ventas", "estado": "Activo", "fecha_ingreso": "2023-01-01"},
        ]
    return empleados


def _periodo_a_rango_fechas(periodo: str) -> tuple:
    """
    Convierte un string de periodo a rango de fechas (inicio, fin).
    Soporta: 'enero', 'febrero', ..., 'Q1', 'Q2', 'Q3', 'Q4',
             '2024', 'ultimo_mes', 'ultimo_trimestre', 'anual'.
    """
    hoy = date.today()

    meses_map = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    p = periodo.lower().strip()

    if p in meses_map:
        mes = meses_map[p]
        anio = hoy.year if mes <= hoy.month else hoy.year - 1
        inicio = date(anio, mes, 1)
        if mes == 12:
            fin = date(anio + 1, 1, 1) - timedelta(days=1)
        else:
            fin = date(anio, mes + 1, 1) - timedelta(days=1)
        return inicio, fin

    if p in ("q1", "primer trimestre"):
        anio = hoy.year if hoy.month > 3 else hoy.year - 1
        return date(anio, 1, 1), date(anio, 3, 31)
    if p in ("q2", "segundo trimestre"):
        anio = hoy.year if hoy.month > 6 else hoy.year - 1
        return date(anio, 4, 1), date(anio, 6, 30)
    if p in ("q3", "tercer trimestre"):
        anio = hoy.year if hoy.month > 9 else hoy.year - 1
        return date(anio, 7, 1), date(anio, 9, 30)
    if p in ("q4", "cuarto trimestre"):
        anio = hoy.year - 1
        return date(anio, 10, 1), date(anio, 12, 31)

    if p in ("ultimo_mes", "ultimo mes", "mes anterior"):
        primer_dia_este_mes = hoy.replace(day=1)
        fin = primer_dia_este_mes - timedelta(days=1)
        inicio = fin.replace(day=1)
        return inicio, fin

    if p in ("ultimo_trimestre", "ultimo trimestre", "trimestre anterior"):
        # Trimestre calendario anterior
        mes_actual = hoy.month
        if mes_actual <= 3:
            return date(hoy.year - 1, 10, 1), date(hoy.year - 1, 12, 31)
        elif mes_actual <= 6:
            return date(hoy.year, 1, 1), date(hoy.year, 3, 31)
        elif mes_actual <= 9:
            return date(hoy.year, 4, 1), date(hoy.year, 6, 30)
        else:
            return date(hoy.year, 7, 1), date(hoy.year, 9, 30)

    if p in ("anual", "año completo", "ano completo", str(hoy.year), str(hoy.year - 1)):
        try:
            anio = int(p) if p.isdigit() else hoy.year - 1
        except ValueError:
            anio = hoy.year - 1
        return date(anio, 1, 1), date(anio, 12, 31)

    # Por defecto: mes actual hasta hoy
    return hoy.replace(day=1), hoy


def _simular_ventas_empleado(empleado: dict, inicio: date, fin: date, rng: random.Random) -> dict:
    """Genera ventas simuladas para un empleado en el rango de fechas."""
    # Solo empleados activos y de ciertos departamentos generan ventas
    if empleado.get("estado", "Activo") != "Activo":
        return None

    dept = empleado.get("departamento", "").lower()
    # Multiplicador de ventas por departamento
    mult_dept = {
        "finanzas": 1.4,
        "ingenieria": 0.8,
        "it": 0.7,
        "rrhh": 0.5,
        "legal": 0.6,
        "ventas": 2.0,
        "comercial": 1.8,
    }.get(dept, 1.0)

    # Dias laborables en el rango
    dias = max(1, (fin - inicio).days + 1)
    dias_laborables = int(dias * 5 / 7)

    # Numero de transacciones simuladas
    num_transacciones = max(1, int(rng.gauss(dias_laborables * 0.6, dias_laborables * 0.2) * mult_dept))
    num_transacciones = min(num_transacciones, 150)

    transacciones = []
    total_vendido = 0.0
    productos_vendidos = defaultdict(int)
    categorias_vendidas = defaultdict(float)

    for _ in range(num_transacciones):
        producto = rng.choice(_PRODUCTOS_CATALOGO)
        cantidad = rng.randint(1, 20)
        precio = producto["precio"] * rng.uniform(0.85, 1.15)  # variacion de precio
        monto = round(cantidad * precio, 2)
        total_vendido += monto
        productos_vendidos[producto["nombre"]] += cantidad
        categorias_vendidas[producto["categoria"]] += monto

    total_vendido = round(total_vendido, 2)

    # Top productos
    top_productos = sorted(
        [{"producto": k, "unidades": v} for k, v in productos_vendidos.items()],
        key=lambda x: x["unidades"],
        reverse=True,
    )[:3]

    return {
        "empleado_id": empleado.get("id"),
        "nombre": empleado.get("nombre"),
        "departamento": empleado.get("departamento"),
        "cargo": empleado.get("cargo"),
        "num_transacciones": num_transacciones,
        "total_vendido": total_vendido,
        "ticket_promedio": round(total_vendido / num_transacciones, 2),
        "top_productos": top_productos,
        "ventas_por_categoria": dict(
            sorted(categorias_vendidas.items(), key=lambda x: x[1], reverse=True)
        ),
    }


def generar_informe_ventas(
    periodo: str,
    departamento: str = "todos",
    formato: str = "resumen",
) -> dict:
    """Genera un informe de ventas para el periodo y departamento indicados.

    Utiliza el archivo de empleados como base de datos de vendedores y simula
    transacciones de productos de oficina de forma determinista (misma entrada,
    mismo resultado). El informe incluye metricas agregadas, ranking de
    vendedores y distribucion por categoria de producto.

    Args:
        periodo: Periodo de tiempo a analizar. Valores aceptados:
            - Nombre de mes en espanol: "enero", "febrero", ..., "diciembre"
            - Trimestre: "Q1", "Q2", "Q3", "Q4"
            - Relativo: "ultimo_mes", "ultimo_trimestre"
            - Anual: "anual" o un ano especifico como "2024"
            Ejemplo: "marzo" analiza el mes de marzo del ano corriente/anterior.
        departamento: Filtra los resultados a un departamento especifico.
            Usar "todos" (valor por defecto) para incluir toda la empresa.
            El filtro es insensible a mayusculas/minusculas.
            Ejemplo: "Finanzas" muestra solo vendedores de Finanzas.
        formato: Nivel de detalle del informe. Valores validos:
            - "resumen": Metricas principales y ranking top-5 (por defecto).
            - "detallado": Incluye desglose completo por vendedor y categoria.
            - "ejecutivo": Solo KPIs clave en formato muy compacto.
            Ejemplo: "detallado" incluye datos de cada vendedor individual.

    Returns:
        Diccionario con el informe de ventas:
        {
            "periodo": str,                     # Periodo analizado
            "fecha_inicio": str,                # Fecha de inicio ISO
            "fecha_fin": str,                   # Fecha de fin ISO
            "departamento_filtro": str,         # Departamento filtrado
            "formato": str,                     # Nivel de detalle
            "generado_en": str,                 # Timestamp de generacion
            "kpis": {
                "total_ventas": float,          # Suma total en USD
                "num_transacciones": int,       # Total de operaciones
                "ticket_promedio": float,       # Promedio por transaccion
                "num_vendedores_activos": int,  # Vendedores con ventas
                "mejor_vendedor": str,          # Nombre del top performer
                "categoria_top": str            # Categoria mas vendida
            },
            "ranking_vendedores": list,         # Top vendedores (hasta 5 en resumen)
            "ventas_por_categoria": dict,       # Totales por categoria
            "detalle_vendedores": list          # Solo en formato "detallado"
        }

    Raises:
        ValueError: Si el formato indicado no es valido.

    Example:
        >>> informe = generar_informe_ventas("Q1", departamento="Finanzas", formato="resumen")
        >>> print(informe["kpis"]["total_ventas"])
        45820.5
    """
    formatos_validos = {"resumen", "detallado", "ejecutivo"}
    if formato.lower() not in formatos_validos:
        raise ValueError(
            f"Formato '{formato}' no valido. Usar: {', '.join(sorted(formatos_validos))}"
        )

    formato = formato.lower()
    departamento_filtro = departamento.strip()

    # Rango de fechas
    fecha_inicio, fecha_fin = _periodo_a_rango_fechas(periodo)

    # Semilla determinista: periodo + departamento
    seed = _SEED_BASE + sum(ord(c) for c in (periodo + departamento_filtro).lower())
    rng = random.Random(seed)

    # Leer empleados
    empleados = _leer_empleados()

    # Filtrar por departamento si aplica
    if departamento_filtro.lower() != "todos":
        empleados = [
            e for e in empleados
            if e.get("departamento", "").lower() == departamento_filtro.lower()
        ]

    # Generar ventas por empleado
    resultados = []
    for emp in empleados:
        datos = _simular_ventas_empleado(emp, fecha_inicio, fecha_fin, rng)
        if datos:
            resultados.append(datos)

    # Agregar metricas globales
    total_ventas = round(sum(r["total_vendido"] for r in resultados), 2)
    total_transacciones = sum(r["num_transacciones"] for r in resultados)
    ticket_promedio = round(total_ventas / total_transacciones, 2) if total_transacciones > 0 else 0.0

    # Ranking vendedores
    ranking = sorted(resultados, key=lambda x: x["total_vendido"], reverse=True)

    # Ventas por categoria global
    categorias_global = defaultdict(float)
    for r in resultados:
        for cat, monto in r.get("ventas_por_categoria", {}).items():
            categorias_global[cat] += monto
    categorias_global = {
        k: round(v, 2)
        for k, v in sorted(categorias_global.items(), key=lambda x: x[1], reverse=True)
    }

    mejor_vendedor = ranking[0]["nombre"] if ranking else "N/A"
    categoria_top = next(iter(categorias_global), "N/A") if categorias_global else "N/A"

    kpis = {
        "total_ventas": total_ventas,
        "num_transacciones": total_transacciones,
        "ticket_promedio": ticket_promedio,
        "num_vendedores_activos": len(resultados),
        "mejor_vendedor": mejor_vendedor,
        "categoria_top": categoria_top,
    }

    # Construir salida segun formato
    num_top = 5 if formato == "resumen" else len(ranking)
    ranking_salida = [
        {
            "posicion": idx + 1,
            "nombre": r["nombre"],
            "departamento": r["departamento"],
            "total_vendido": r["total_vendido"],
            "num_transacciones": r["num_transacciones"],
            "ticket_promedio": r["ticket_promedio"],
        }
        for idx, r in enumerate(ranking[:num_top])
    ]

    informe = {
        "periodo": periodo,
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "departamento_filtro": departamento_filtro,
        "formato": formato,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "kpis": kpis,
        "ranking_vendedores": ranking_salida,
        "ventas_por_categoria": categorias_global,
    }

    # En formato detallado, incluir datos completos por vendedor
    if formato == "detallado":
        informe["detalle_vendedores"] = resultados

    return informe
