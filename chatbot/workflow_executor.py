"""
Ejecutor dinamico de workflows.
Importa y ejecuta funciones de workflow en un hilo separado con timeout de 30 segundos.
"""

import importlib.util
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from workflow_registry import get_workflow

# Timeout maximo de ejecucion en segundos
_EXECUTION_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Importacion dinamica
# ---------------------------------------------------------------------------

def _import_function(source_file: str, function_name: str):
    """Importa dinamicamente una funcion desde un archivo .py.

    Args:
        source_file: Ruta absoluta al archivo de workflow.
        function_name: Nombre de la funcion a importar.

    Returns:
        La funcion Python importada.

    Raises:
        ImportError: Si el archivo no puede cargarse.
        AttributeError: Si la funcion no existe en el modulo.
    """
    # Nombre de modulo unico basado en el path para evitar colisiones
    module_name = f"_workflow_{hash(source_file) & 0xFFFFFFFF}"

    spec = importlib.util.spec_from_file_location(module_name, source_file)
    if spec is None:
        raise ImportError(f"No se pudo crear spec para '{source_file}'.")

    module = importlib.util.module_from_spec(spec)

    # Registrar en sys.modules para que las importaciones internas del modulo funcionen
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        # Limpiar de sys.modules si falla
        sys.modules.pop(module_name, None)
        raise ImportError(f"Error al cargar '{source_file}': {e}") from e

    func = getattr(module, function_name, None)
    if func is None:
        raise AttributeError(
            f"La funcion '{function_name}' no existe en '{source_file}'."
        )

    return func


# ---------------------------------------------------------------------------
# Normalizacion de parametros
# ---------------------------------------------------------------------------

def _parse_items_string(raw: str) -> list:
    """Intenta parsear una cadena de texto como lista de items de cotizacion.

    Soporta multiples formatos comunes:
    - JSON array: [{"producto": "X", "cantidad": 2, "precio_unitario": 10.0}]
    - Texto simple: "5 sillas a 120, 2 escritorios a 350"
    - Lineas: "producto: silla, cantidad: 5, precio: 120\nproducto: escritorio, cantidad: 2, precio: 350"

    Args:
        raw: String con la representacion de los items.

    Returns:
        Lista de dicts con claves: producto, cantidad, precio_unitario.
        Lista vacia si no puede parsear nada.
    """
    raw = raw.strip()

    # Intento 1: JSON directo
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Intento 2: formato "N producto a PRECIO"
    # Ejemplo: "5 sillas a 120.50, 2 escritorios a 350"
    items = []
    # Dividir por coma o punto y coma o salto de linea
    partes = [p.strip() for p in raw.replace(";", ",").replace("\n", ",").split(",") if p.strip()]

    for parte in partes:
        # Patron: "<cantidad> <producto> a <precio>" o "<producto> x<cantidad> a <precio>"
        import re

        # Patron 1: "5 sillas a 120"
        m = re.match(
            r"^(\d+)\s+(.+?)\s+(?:a|@|x)\s*([\d.,]+)\s*(?:c/?u|cada una?|pesos?|usd|eur)?$",
            parte,
            re.IGNORECASE,
        )
        if m:
            try:
                cantidad = int(m.group(1))
                producto = m.group(2).strip()
                precio = float(m.group(3).replace(",", "."))
                items.append({
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": precio,
                })
                continue
            except (ValueError, TypeError):
                pass

        # Patron 2: "sillas x5 a 120" o "sillas (5) 120"
        m = re.match(
            r"^(.+?)\s+[x(](\d+)[)]?\s+(?:a|@|x)?\s*([\d.,]+)",
            parte,
            re.IGNORECASE,
        )
        if m:
            try:
                producto = m.group(1).strip()
                cantidad = int(m.group(2))
                precio = float(m.group(3).replace(",", "."))
                items.append({
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": precio,
                })
                continue
            except (ValueError, TypeError):
                pass

        # Patron 3: "producto: silla, cantidad: 5, precio: 120"
        prod_m = re.search(r"producto\s*:\s*(.+?)(?:,|$)", parte, re.IGNORECASE)
        cant_m = re.search(r"cantidad\s*:\s*(\d+)", parte, re.IGNORECASE)
        prec_m = re.search(r"precio(?:_unitario)?\s*:\s*([\d.,]+)", parte, re.IGNORECASE)

        if prod_m and cant_m and prec_m:
            try:
                items.append({
                    "producto": prod_m.group(1).strip(),
                    "cantidad": int(cant_m.group(1)),
                    "precio_unitario": float(prec_m.group(1).replace(",", ".")),
                })
                continue
            except (ValueError, TypeError):
                pass

    return items


def _normalize_params(params: dict, function_name: str) -> dict:
    """Normaliza y convierte los parametros al tipo correcto segun el workflow.

    Maneja especialmente el parametro 'items' para cotizacion: si es un string,
    lo parsea como lista de productos. Convierte tipos basicos (str -> float, etc.)
    segun el contexto.

    Args:
        params: Diccionario de parametros crudos (posiblemente strings).
        function_name: Nombre de la funcion para aplicar logica especifica.

    Returns:
        Diccionario de parametros normalizados.
    """
    normalized = {}

    for key, value in params.items():
        # Parametro especial: items (lista de productos para cotizacion)
        if key == "items":
            if isinstance(value, str):
                parsed = _parse_items_string(value)
                normalized[key] = parsed if parsed else []
            elif isinstance(value, list):
                normalized[key] = value
            else:
                normalized[key] = []
            continue

        # Parametros numericos conocidos
        if key in ("descuento_pct",):
            try:
                normalized[key] = float(str(value).replace(",", ".").replace("%", "").strip())
            except (ValueError, TypeError):
                normalized[key] = 0.0
            continue

        # Booleanos
        if isinstance(value, str) and value.lower() in ("true", "false", "si", "no"):
            normalized[key] = value.lower() in ("true", "si")
            continue

        # Por defecto: dejar el valor tal cual
        normalized[key] = value

    return normalized


# ---------------------------------------------------------------------------
# Executor principal
# ---------------------------------------------------------------------------

def execute_workflow(project_type: str, params: dict) -> dict:
    """Ejecuta un workflow de forma dinamica con timeout de 30 segundos.

    Importa el archivo de workflow registrado, normaliza los parametros
    y ejecuta la funcion en un ThreadPoolExecutor para poder aplicar timeout.

    Args:
        project_type: Tipo de workflow a ejecutar (ej: "cotizacion", "informe_ventas").
        params: Diccionario de parametros a pasar a la funcion del workflow.

    Returns:
        Diccionario con el resultado de la ejecucion:
        {
            "status": "ok" | "error" | "timeout",
            "result": dict | None,   # Resultado del workflow si status=="ok"
            "error": str | None,     # Descripcion del error si status != "ok"
        }

    Example:
        >>> result = execute_workflow("cotizacion", {
        ...     "cliente_nombre": "Ana Lopez",
        ...     "cliente_empresa": "Tech Corp",
        ...     "items": [{"producto": "Silla", "cantidad": 5, "precio_unitario": 120}]
        ... })
        >>> result["status"]
        "ok"
        >>> result["result"]["numero_cotizacion"]
        "COT-202601-4823"
    """
    # Validar que el workflow existe en el registro
    wf_meta = get_workflow(project_type)
    if not wf_meta:
        return {
            "status": "error",
            "result": None,
            "error": f"Workflow '{project_type}' no encontrado en el registro.",
        }

    source_file = wf_meta["source_file"]
    function_name = wf_meta["function_name"]

    # Normalizar parametros
    normalized_params = _normalize_params(params, function_name)

    def _run():
        """Funcion interna que importa y ejecuta el workflow."""
        func = _import_function(source_file, function_name)
        return func(**normalized_params)

    # Ejecutar con timeout en ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            result = future.result(timeout=_EXECUTION_TIMEOUT)
            return {
                "status": "ok",
                "result": result,
                "error": None,
            }
        except FuturesTimeoutError:
            return {
                "status": "timeout",
                "result": None,
                "error": f"El workflow '{project_type}' excedio el tiempo limite de {_EXECUTION_TIMEOUT} segundos.",
            }
        except TypeError as e:
            # Parametros incorrectos
            return {
                "status": "error",
                "result": None,
                "error": f"Parametros invalidos para '{function_name}': {e}",
            }
        except ValueError as e:
            # Errores de validacion del workflow
            return {
                "status": "error",
                "result": None,
                "error": f"Error de validacion en '{project_type}': {e}",
            }
        except Exception as e:
            # Error inesperado
            tb = traceback.format_exc()
            return {
                "status": "error",
                "result": None,
                "error": f"Error inesperado en '{project_type}': {e}\n{tb}",
            }
