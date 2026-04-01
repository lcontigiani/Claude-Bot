"""
Registro central de workflows disponibles en el sistema.
Mapea tipos de proyecto a sus archivos fuente, funciones y metadatos de presentacion.
"""

import os

# Directorio donde residen los archivos de workflow
_WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "workflows")


# ---------------------------------------------------------------------------
# Registro principal
# ---------------------------------------------------------------------------
# Estructura de cada entrada:
#   source_file:      Ruta absoluta al archivo .py del workflow
#   function_name:    Nombre de la funcion a ejecutar
#   display_name:     Nombre amigable para mostrar al usuario
#   cancel_keywords:  Lista de palabras/frases que cancela el flujo activo
# ---------------------------------------------------------------------------

WORKFLOW_REGISTRY: dict[str, dict] = {
    "cotizacion": {
        "source_file": os.path.join(_WORKFLOWS_DIR, "cotizacion.py"),
        "function_name": "generar_cotizacion",
        "display_name": "Generacion de Cotizacion",
        "cancel_keywords": [
            "cancelar", "cancel", "salir", "exit", "abandoner",
            "no quiero", "detener", "parar", "stop", "abort",
            "olvidalo", "olvida", "dejalo", "deja eso",
        ],
    },
    "informe_ventas": {
        "source_file": os.path.join(_WORKFLOWS_DIR, "informe_ventas.py"),
        "function_name": "generar_informe_ventas",
        "display_name": "Informe de Ventas",
        "cancel_keywords": [
            "cancelar", "cancel", "salir", "exit", "abandoner",
            "no quiero", "detener", "parar", "stop", "abort",
            "olvidalo", "olvida", "dejalo", "deja eso",
        ],
    },
}


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def get_workflow(project_type: str) -> dict | None:
    """Retorna la entrada del registro para un tipo de proyecto.

    Args:
        project_type: Clave del tipo de proyecto (ej: "cotizacion", "informe_ventas").

    Returns:
        Diccionario con {source_file, function_name, display_name, cancel_keywords}
        o None si el tipo no esta registrado.

    Example:
        >>> wf = get_workflow("cotizacion")
        >>> wf["function_name"]
        "generar_cotizacion"
    """
    return WORKFLOW_REGISTRY.get(project_type)


def list_workflows() -> list[dict]:
    """Lista todos los workflows registrados con sus metadatos publicos.

    Returns:
        Lista de dicts con {project_type, display_name, source_file, function_name}.
        Ordenada alfabeticamente por project_type.

    Example:
        >>> workflows = list_workflows()
        >>> [w["project_type"] for w in workflows]
        ["cotizacion", "informe_ventas"]
    """
    result = []
    for project_type, meta in sorted(WORKFLOW_REGISTRY.items()):
        result.append({
            "project_type": project_type,
            "display_name": meta["display_name"],
            "source_file": meta["source_file"],
            "function_name": meta["function_name"],
        })
    return result


def is_cancel_message(project_type: str, message: str) -> bool:
    """Determina si un mensaje es una solicitud de cancelacion para el workflow activo.

    Args:
        project_type: Tipo del proyecto activo.
        message: Texto del mensaje del usuario.

    Returns:
        True si el mensaje coincide con alguna keyword de cancelacion, False si no.

    Example:
        >>> is_cancel_message("cotizacion", "quiero cancelar esto")
        True
        >>> is_cancel_message("cotizacion", "Juan Perez")
        False
    """
    wf = get_workflow(project_type)
    if not wf:
        return False

    texto = message.lower().strip()
    for keyword in wf["cancel_keywords"]:
        if keyword in texto:
            return True
    return False
