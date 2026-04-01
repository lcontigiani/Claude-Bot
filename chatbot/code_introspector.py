"""
Introspector de codigo Python usando solo el modulo ast (sin importar ni ejecutar los archivos).
Extrae parametros, tipos, valores por defecto y docstrings de funciones especificas.
"""

import ast
import re
from typing import Any


# ---------------------------------------------------------------------------
# Tipos Python comunes como strings para mostrar al usuario
# ---------------------------------------------------------------------------

_TYPE_NAMES = {
    "str": "str",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "list": "list",
    "dict": "dict",
    "tuple": "tuple",
    "None": "None",
    "Optional": "Optional",
}


def _ast_annotation_to_str(node) -> str | None:
    """Convierte un nodo AST de anotacion de tipo a string legible."""
    if node is None:
        return None
    try:
        # Python 3.8+ tiene ast.unparse
        return ast.unparse(node)
    except AttributeError:
        # Fallback para versiones mas antiguas
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_ast_annotation_to_str(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            return f"{_ast_annotation_to_str(node.value)}[{_ast_annotation_to_str(node.slice)}]"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        return "Any"


def _ast_default_to_value(node) -> Any:
    """Convierte un nodo AST de valor por defecto a un valor Python."""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        # Para constantes complejas, retornar su representacion string
        try:
            return ast.unparse(node)
        except AttributeError:
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                return node.id
            return "<complex_default>"


def _parse_google_docstring(docstring: str) -> dict:
    """Parsea un docstring en estilo Google para extraer descripciones de parametros.

    Detecta la seccion 'Args:' y extrae los parametros con sus descripciones.
    Soporta descripciones multilinea (indentadas).

    Args:
        docstring: String del docstring completo de la funcion.

    Returns:
        Diccionario {nombre_param: descripcion_param}.
        Si no hay seccion Args, retorna dict vacio.

    Example:
        Input:
            '''Hace algo.
            Args:
                nombre: El nombre del usuario.
                edad: La edad. Debe ser positiva.
            Returns:
                str: El resultado.
            '''
        Output:
            {"nombre": "El nombre del usuario.", "edad": "La edad. Debe ser positiva."}
    """
    if not docstring:
        return {}

    param_descriptions = {}

    # Encontrar la seccion Args/Arguments/Parameters
    # Soporta tanto 'Args:' como 'Arguments:' y 'Parameters:'
    args_section_match = re.search(
        r"^\s*(Args|Arguments|Parameters)\s*:\s*$",
        docstring,
        re.MULTILINE | re.IGNORECASE,
    )
    if not args_section_match:
        return {}

    # Extraer el contenido despues de la seccion Args hasta la siguiente seccion o fin
    args_start = args_section_match.end()
    # La siguiente seccion empieza con una palabra seguida de ':'
    next_section_match = re.search(
        r"^\s*[A-Za-z][A-Za-z\s]*:\s*$",
        docstring[args_start:],
        re.MULTILINE,
    )
    if next_section_match:
        args_content = docstring[args_start: args_start + next_section_match.start()]
    else:
        args_content = docstring[args_start:]

    # Parsear cada parametro: "    nombre: descripcion"
    # Con soporte para descripcion multilinea (lineas con mayor indentacion)
    lines = args_content.split("\n")

    current_param = None
    current_desc_lines = []

    # Detectar indentacion base de los parametros (primera linea con contenido)
    base_indent = None
    for line in lines:
        stripped = line.rstrip()
        if stripped and stripped.lstrip():
            # Calcular indentacion
            indent = len(stripped) - len(stripped.lstrip())
            if base_indent is None:
                base_indent = indent
            break

    if base_indent is None:
        return {}

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            # Linea vacia: puede ser separador o fin de descripcion
            if current_param:
                current_desc_lines.append("")
            continue

        content = stripped.lstrip()
        indent = len(stripped) - len(content)

        if indent == base_indent:
            # Guardar parametro anterior si existe
            if current_param:
                param_descriptions[current_param] = " ".join(
                    part for part in current_desc_lines if part
                ).strip()

            # Nuevo parametro: "nombre (tipo): descripcion" o "nombre: descripcion"
            param_match = re.match(r"^(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)", content)
            if param_match:
                current_param = param_match.group(1)
                first_desc = param_match.group(2).strip()
                current_desc_lines = [first_desc] if first_desc else []
            else:
                current_param = None
                current_desc_lines = []

        elif indent > base_indent and current_param:
            # Continuacion de descripcion multilinea
            current_desc_lines.append(content)

    # Guardar el ultimo parametro
    if current_param:
        param_descriptions[current_param] = " ".join(
            part for part in current_desc_lines if part
        ).strip()

    return param_descriptions


def introspect_function(file_path: str, function_name: str) -> dict:
    """Extrae metadatos de una funcion Python usando solo analisis AST.

    No importa ni ejecuta el archivo objetivo. Parsea el codigo fuente
    estaticamente para extraer parametros, tipos, defaults y docstring.
    Soporta docstrings en estilo Google para extraer descripciones de parametros.

    Args:
        file_path: Ruta absoluta al archivo .py que contiene la funcion.
        function_name: Nombre exacto de la funcion a inspeccionar.

    Returns:
        Diccionario con la siguiente estructura:
        {
            "function_name": str,
            "docstring": str | None,
            "required_params": [
                {
                    "name": str,
                    "type": str | None,
                    "required": True,
                    "default": None,
                    "description": str
                }
            ],
            "optional_params": [
                {
                    "name": str,
                    "type": str | None,
                    "required": False,
                    "default": Any,
                    "description": str
                }
            ],
            "all_params": list  # required_params + optional_params en orden
        }

    Raises:
        FileNotFoundError: Si el archivo no existe en la ruta indicada.
        ValueError: Si la funcion no se encuentra en el archivo.
        SyntaxError: Si el archivo tiene errores de sintaxis Python.

    Example:
        >>> info = introspect_function("/path/to/cotizacion.py", "generar_cotizacion")
        >>> info["required_params"][0]["name"]
        "cliente_nombre"
    """
    # --- Leer y parsear el archivo ---
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        raise SyntaxError(f"Error de sintaxis en {file_path}: {e}") from e

    # --- Buscar la funcion en el AST ---
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                target_func = node
                break

    if target_func is None:
        raise ValueError(
            f"Funcion '{function_name}' no encontrada en '{file_path}'."
        )

    # --- Extraer docstring ---
    docstring = ast.get_docstring(target_func)

    # --- Parsear descripciones del docstring ---
    param_descriptions = _parse_google_docstring(docstring or "")

    # --- Analizar argumentos ---
    args = target_func.args

    # Todos los argumentos posicionales y keyword (excluir 'self' y 'cls')
    all_arg_nodes = args.args + args.kwonlyargs

    # Calcular los defaults para args.args
    # Los defaults estan al final de la lista; calcular offset
    num_args = len(args.args)
    num_defaults = len(args.defaults)
    # Los primeros (num_args - num_defaults) argumentos son requeridos
    args_required_until = num_args - num_defaults

    required_params = []
    optional_params = []

    for idx, arg in enumerate(args.args):
        # Ignorar self/cls
        if arg.arg in ("self", "cls"):
            continue

        name = arg.arg
        type_str = _ast_annotation_to_str(arg.annotation)
        description = param_descriptions.get(name, "")

        if idx < args_required_until:
            # Parametro requerido
            required_params.append({
                "name": name,
                "type": type_str,
                "required": True,
                "default": None,
                "description": description,
            })
        else:
            # Parametro opcional: calcular el default
            default_idx = idx - args_required_until
            default_node = args.defaults[default_idx] if default_idx < len(args.defaults) else None
            default_value = _ast_default_to_value(default_node)
            optional_params.append({
                "name": name,
                "type": type_str,
                "required": False,
                "default": default_value,
                "description": description,
            })

    # Procesar kwonlyargs (argumentos keyword-only despues de *)
    for idx, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        type_str = _ast_annotation_to_str(arg.annotation)
        description = param_descriptions.get(name, "")

        kw_default = args.kw_defaults[idx] if idx < len(args.kw_defaults) else None
        if kw_default is None:
            # Keyword-only sin default: requerido
            required_params.append({
                "name": name,
                "type": type_str,
                "required": True,
                "default": None,
                "description": description,
            })
        else:
            optional_params.append({
                "name": name,
                "type": type_str,
                "required": False,
                "default": _ast_default_to_value(kw_default),
                "description": description,
            })

    # Orden original: requeridos primero, opcionales despues
    all_params = required_params + optional_params

    return {
        "function_name": function_name,
        "docstring": docstring,
        "required_params": required_params,
        "optional_params": optional_params,
        "all_params": all_params,
    }
