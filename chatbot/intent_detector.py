"""
Detector de intenciones para el sistema de workflows del chatbot.
Identifica si un mensaje del usuario solicita un flujo de trabajo especifico.
"""

import re


# ---------------------------------------------------------------------------
# Patrones de keywords por tipo de proyecto
# Cada entrada es una lista de patrones regex (sin importar mayusculas).
# El orden importa: se evaluan en orden y se retorna el primero que coincida.
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = [
    # --- Cotizacion / Presupuesto ---
    # Cubre: cotizacion, cotizaciones, cotizar, presupuesto, presupuestar,
    #        quote, quoting, propuesta economica, oferta comercial
    (
        "cotizacion",
        [
            r"\bcoti[sz]a[cr]",           # cotizar, cotizacion, cotizaci
            r"\bpresupuest",              # presupuesto, presupuestar
            r"\bquote\b",                 # quote (ingles)
            r"\bpropuesta\s+econom",      # propuesta economica
            r"\boferta\s+comercial",      # oferta comercial
            r"\boferta\s+de\s+precio",    # oferta de precio
            r"\bprecio\s+de\s+venta",     # precio de venta
            r"\blistado\s+de\s+precio",   # listado de precios
            r"\bfactura\s+proforma",      # factura proforma
            r"\bproforma",               # proforma
        ],
    ),

    # --- Informe de ventas / Reporte / Analisis ---
    # Cubre: informe, reporte, analisis, estadistica, ventas, resultados
    (
        "informe_ventas",
        [
            r"\binforme\s+de\s+venta",    # informe de ventas
            r"\breporte\s+de\s+venta",    # reporte de ventas
            r"\binforme\s+de\s+resultado", # informe de resultados
            r"\binforme\s+mensual",       # informe mensual
            r"\binforme\s+trimestral",    # informe trimestral
            r"\binforme\s+anual",         # informe anual
            r"\breporte\s+mensual",       # reporte mensual
            r"\breporte\s+trimestral",    # reporte trimestral
            r"\banalisis\s+de\s+venta",   # analisis de ventas
            r"\bestadistica",             # estadisticas
            r"\bkpi",                     # KPIs
            r"\bmetrica",                 # metricas
            r"\binforme\b",              # informe (generico, baja prioridad)
            r"\breporte\b",              # reporte (generico, baja prioridad)
            r"\banalisis\b",             # analisis (generico, baja prioridad)
        ],
    ),
]

# Palabras de contexto que refuerzan la deteccion (boost heuristico)
# Si al menos una aparece junto al patron, aumenta la certeza.
_CONTEXT_BOOSTERS = {
    "cotizacion": [
        r"\bcliente\b", r"\bproducto\b", r"\bservicio\b",
        r"\bcantidad\b", r"\bprecio\b", r"\bitem\b",
    ],
    "informe_ventas": [
        r"\bdepartamento\b", r"\btrimestre\b", r"\bmes\b",
        r"\bvendedor\b", r"\bperiodo\b", r"\bresultado\b",
    ],
}


def detect_project_intent(message: str) -> dict | None:
    """Detecta si un mensaje del usuario solicita un workflow especifico.

    Analiza el texto usando coincidencia de keywords en espanol (e ingles
    basico) para determinar si el usuario quiere generar una cotizacion o
    un informe de ventas. Retorna None si no se detecta ninguna intencion
    de workflow conocida.

    Args:
        message: Texto del mensaje del usuario en lenguaje natural.

    Returns:
        Diccionario con la intencion detectada, por ejemplo:
            {"project_type": "cotizacion"}
            {"project_type": "informe_ventas"}
        O None si no se detecta ningun workflow.

    Example:
        >>> detect_project_intent("Necesito una cotizacion para 10 sillas")
        {"project_type": "cotizacion"}
        >>> detect_project_intent("Hola, como estas?")
        None
    """
    if not message or not isinstance(message, str):
        return None

    # Normalizar: minusculas, remover acentos comunes para comparacion robusta
    texto = message.lower().strip()
    texto_normalizado = _normalizar(texto)

    # Evaluar cada intent en orden de prioridad
    for project_type, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, texto_normalizado, re.IGNORECASE):
                return {"project_type": project_type}

    return None


def _normalizar(texto: str) -> str:
    """Normaliza texto removiendo acentos y caracteres especiales del espanol."""
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
        "ä": "a", "ë": "e", "ï": "i", "ö": "o", "ü": "u",
        "â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u",
        "ñ": "n",
    }
    for acento, plain in reemplazos.items():
        texto = texto.replace(acento, plain)
    return texto
