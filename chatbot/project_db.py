"""
Capa de acceso a la base de datos SQLite para el sistema de proyectos/workflows.
Gestiona el ciclo de vida de proyectos, preguntas de intake y especificaciones
de workflow generadas por el ProjectAgent.
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
import os

# Ruta de la base de datos
_DB_PATH = os.path.join(os.path.dirname(__file__), "project_memory.db")


def _now() -> str:
    """Retorna timestamp UTC en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _get_conn() -> sqlite3.Connection:
    """Crea y retorna una conexion SQLite con row_factory configurado."""
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Inicializacion
# ---------------------------------------------------------------------------

def init_project_db():
    """Crea todas las tablas necesarias si no existen.

    Debe llamarse una sola vez al iniciar el servidor.
    Es seguro llamarla multiples veces (idempotente).
    """
    conn = _get_conn()
    c = conn.cursor()

    c.executescript("""
        -- Tabla principal de proyectos/sesiones de workflow
        CREATE TABLE IF NOT EXISTS projects (
            project_id      TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL,
            project_type    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'intake',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            finished_at     TEXT,
            error_message   TEXT
        );

        -- Tabla de preguntas del intake (una fila por parametro a recopilar)
        CREATE TABLE IF NOT EXISTS project_intake (
            intake_id       TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL REFERENCES projects(project_id),
            field_name      TEXT NOT NULL,
            question_asked  TEXT,
            raw_answer      TEXT,
            parsed_value    TEXT,
            answered_at     TEXT,
            order_index     INTEGER NOT NULL DEFAULT 0
        );

        -- Tabla de especificaciones finales del workflow (parametros listos para ejecutar)
        CREATE TABLE IF NOT EXISTS project_workflow_specs (
            spec_id         TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL REFERENCES projects(project_id),
            params_json     TEXT NOT NULL,
            result_json     TEXT,
            created_at      TEXT NOT NULL,
            executed_at     TEXT
        );

        -- Indices para consultas frecuentes
        CREATE INDEX IF NOT EXISTS idx_projects_session
            ON projects(session_id, status);

        CREATE INDEX IF NOT EXISTS idx_intake_project
            ON project_intake(project_id, answered_at);

        CREATE INDEX IF NOT EXISTS idx_specs_project
            ON project_workflow_specs(project_id);
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Proyectos
# ---------------------------------------------------------------------------

def create_project(session_id: str, project_type: str) -> str:
    """Crea un nuevo proyecto y retorna su project_id.

    Args:
        session_id: Identificador unico de la sesion del usuario.
        project_type: Tipo de workflow ("cotizacion", "informe_ventas", etc.).

    Returns:
        project_id: UUID del proyecto recien creado.
    """
    project_id = str(uuid.uuid4())
    now = _now()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO projects (project_id, session_id, project_type, status, created_at, updated_at) "
        "VALUES (?, ?, ?, 'intake', ?, ?)",
        (project_id, session_id, project_type, now, now),
    )
    conn.commit()
    conn.close()
    return project_id


def get_active_project(session_id: str) -> dict | None:
    """Retorna el proyecto activo (no finalizado) de una sesion, o None.

    Un proyecto esta activo si su status es 'intake' o 'executing'.

    Args:
        session_id: Identificador de la sesion del usuario.

    Returns:
        Diccionario con los datos del proyecto o None si no hay ninguno activo.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM projects WHERE session_id=? AND status IN ('intake', 'executing') "
        "ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_project_by_id(project_id: str) -> dict | None:
    """Retorna un proyecto por su ID, o None si no existe.

    Args:
        project_id: UUID del proyecto.

    Returns:
        Diccionario con los datos del proyecto o None.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM projects WHERE project_id=?",
        (project_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_project_status(project_id: str, status: str, error_message: str = None):
    """Actualiza el estado de un proyecto.

    Args:
        project_id: UUID del proyecto a actualizar.
        status: Nuevo estado. Valores validos: 'intake', 'executing', 'completed', 'cancelled', 'error'.
        error_message: Mensaje de error opcional, solo para status='error'.
    """
    now = _now()
    finished_at = now if status in ("completed", "cancelled", "error") else None
    conn = _get_conn()
    conn.execute(
        "UPDATE projects SET status=?, updated_at=?, finished_at=?, error_message=? WHERE project_id=?",
        (status, now, finished_at, error_message, project_id),
    )
    conn.commit()
    conn.close()


def list_projects_for_session(session_id: str, limit: int = 10) -> list:
    """Lista los proyectos mas recientes de una sesion.

    Args:
        session_id: Identificador de la sesion del usuario.
        limit: Numero maximo de proyectos a retornar.

    Returns:
        Lista de diccionarios con datos de cada proyecto, ordenados por fecha desc.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM projects WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Intake (recopilacion de datos)
# ---------------------------------------------------------------------------

def add_intake_question(project_id: str, field_name: str, question_asked: str, order_index: int = 0):
    """Registra una pregunta del intake para un campo de parametro.

    Args:
        project_id: UUID del proyecto al que pertenece.
        field_name: Nombre del parametro (ej: "cliente_nombre", "items").
        question_asked: Texto de la pregunta formulada al usuario.
        order_index: Posicion relativa en el flujo de preguntas (0-based).
    """
    intake_id = str(uuid.uuid4())
    conn = _get_conn()
    conn.execute(
        "INSERT INTO project_intake (intake_id, project_id, field_name, question_asked, order_index) "
        "VALUES (?, ?, ?, ?, ?)",
        (intake_id, project_id, field_name, question_asked, order_index),
    )
    conn.commit()
    conn.close()
    return intake_id


def record_intake_answer(project_id: str, field_name: str, raw_answer: str, parsed_value):
    """Registra la respuesta del usuario para un campo del intake.

    Args:
        project_id: UUID del proyecto.
        field_name: Nombre del parametro respondido.
        raw_answer: Texto literal del usuario.
        parsed_value: Valor procesado y validado (cualquier tipo serializable a JSON).
    """
    now = _now()
    conn = _get_conn()
    conn.execute(
        "UPDATE project_intake "
        "SET raw_answer=?, parsed_value=?, answered_at=? "
        "WHERE project_id=? AND field_name=? AND answered_at IS NULL",
        (raw_answer, json.dumps(parsed_value, ensure_ascii=False, default=str), now, project_id, field_name),
    )
    # Actualizar also updated_at del proyecto
    conn.execute(
        "UPDATE projects SET updated_at=? WHERE project_id=?",
        (now, project_id),
    )
    conn.commit()
    conn.close()


def get_intake_state(project_id: str) -> list:
    """Retorna el estado completo del intake de un proyecto.

    Args:
        project_id: UUID del proyecto.

    Returns:
        Lista de dicts con todos los campos del intake, en orden.
        Cada dict incluye: intake_id, field_name, question_asked,
        raw_answer, parsed_value, answered_at, order_index.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM project_intake WHERE project_id=? ORDER BY order_index ASC",
        (project_id,),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        # Deserializar parsed_value si existe
        if d.get("parsed_value"):
            try:
                d["parsed_value"] = json.loads(d["parsed_value"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(d)
    return result


def get_unanswered_question(project_id: str) -> dict | None:
    """Retorna la primera pregunta sin responder del intake, en orden.

    Args:
        project_id: UUID del proyecto.

    Returns:
        Dict con datos del campo sin responder, o None si todos estan respondidos.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM project_intake "
        "WHERE project_id=? AND answered_at IS NULL "
        "ORDER BY order_index ASC LIMIT 1",
        (project_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_answered_fields(project_id: str) -> dict:
    """Retorna un diccionario {field_name: parsed_value} de todos los campos respondidos.

    Args:
        project_id: UUID del proyecto.

    Returns:
        Diccionario mapeando nombre de campo a su valor parseado.
        Los campos sin respuesta no aparecen en el resultado.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT field_name, parsed_value FROM project_intake "
        "WHERE project_id=? AND answered_at IS NOT NULL",
        (project_id,),
    ).fetchall()
    conn.close()

    result = {}
    for row in rows:
        field = row["field_name"]
        raw = row["parsed_value"]
        try:
            result[field] = json.loads(raw) if raw else None
        except (json.JSONDecodeError, TypeError):
            result[field] = raw
    return result


# ---------------------------------------------------------------------------
# Especificaciones de workflow
# ---------------------------------------------------------------------------

def save_workflow_spec(project_id: str, params: dict) -> str:
    """Guarda los parametros finales listos para ejecutar el workflow.

    Args:
        project_id: UUID del proyecto.
        params: Diccionario de parametros validados para llamar a la funcion del workflow.

    Returns:
        spec_id: UUID de la especificacion guardada.
    """
    spec_id = str(uuid.uuid4())
    now = _now()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO project_workflow_specs (spec_id, project_id, params_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (spec_id, project_id, json.dumps(params, ensure_ascii=False, default=str), now),
    )
    conn.commit()
    conn.close()
    return spec_id


def get_workflow_spec(project_id: str) -> dict | None:
    """Retorna la especificacion de workflow mas reciente de un proyecto.

    Args:
        project_id: UUID del proyecto.

    Returns:
        Dict con spec_id, project_id, params_json (como dict), result_json,
        created_at y executed_at. O None si no hay especificacion.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM project_workflow_specs WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    d = dict(row)
    try:
        d["params"] = json.loads(d["params_json"])
    except (json.JSONDecodeError, TypeError):
        d["params"] = {}
    try:
        d["result"] = json.loads(d["result_json"]) if d.get("result_json") else None
    except (json.JSONDecodeError, TypeError):
        d["result"] = None
    return d


def save_workflow_result(project_id: str, result: dict):
    """Guarda el resultado de la ejecucion del workflow en la especificacion.

    Args:
        project_id: UUID del proyecto.
        result: Diccionario con el resultado retornado por el workflow.
    """
    now = _now()
    conn = _get_conn()
    conn.execute(
        "UPDATE project_workflow_specs SET result_json=?, executed_at=? WHERE project_id=? "
        "AND spec_id=(SELECT spec_id FROM project_workflow_specs WHERE project_id=? ORDER BY created_at DESC LIMIT 1)",
        (json.dumps(result, ensure_ascii=False, default=str), now, project_id, project_id),
    )
    conn.commit()
    conn.close()
