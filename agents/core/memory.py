"""
Capa de acceso a la base de datos SQLite compartida entre todos los agentes.
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(cfg.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Crea todas las tablas si no existen."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            agent_run_id  TEXT PRIMARY KEY,
            agent_name    TEXT NOT NULL,
            triggered_by  TEXT,
            status        TEXT DEFAULT 'running',
            started_at    TEXT,
            finished_at   TEXT,
            input_context TEXT,
            token_count   INTEGER DEFAULT 0,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS findings (
            finding_id    TEXT PRIMARY KEY,
            agent_run_id  TEXT,
            agent_name    TEXT,
            category      TEXT,
            severity      TEXT,
            title         TEXT,
            detail        TEXT,
            affected_file TEXT,
            affected_table TEXT,
            created_at    TEXT,
            acknowledged  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS reports (
            report_id     TEXT PRIMARY KEY,
            agent_run_id  TEXT,
            agent_name    TEXT,
            report_type   TEXT,
            title         TEXT,
            content       TEXT,
            data_snapshot TEXT,
            created_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS proposals (
            proposal_id       TEXT PRIMARY KEY,
            agent_run_id      TEXT,
            finding_id        TEXT,
            title             TEXT,
            rationale         TEXT,
            implementation    TEXT,
            estimated_effort  TEXT,
            priority          TEXT,
            status            TEXT DEFAULT 'pending',
            created_at        TEXT,
            reviewed_at       TEXT,
            reviewer_notes    TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_messages (
            message_id      TEXT PRIMARY KEY,
            sender_agent    TEXT,
            recipient_agent TEXT,
            message_type    TEXT,
            payload         TEXT,
            sent_at         TEXT,
            read_at         TEXT
        );

        CREATE TABLE IF NOT EXISTS system_metrics (
            metric_id    TEXT PRIMARY KEY,
            agent_run_id TEXT,
            metric_name  TEXT,
            metric_value REAL,
            metric_unit  TEXT,
            context      TEXT,
            recorded_at  TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_findings_agent_date
            ON findings(agent_name, created_at);
        CREATE INDEX IF NOT EXISTS idx_findings_severity
            ON findings(severity);
        CREATE INDEX IF NOT EXISTS idx_runs_agent_date
            ON agent_runs(agent_name, started_at);
        CREATE INDEX IF NOT EXISTS idx_proposals_status
            ON proposals(status, priority);
        CREATE INDEX IF NOT EXISTS idx_messages_recipient
            ON agent_messages(recipient_agent, read_at);
        CREATE INDEX IF NOT EXISTS idx_metrics_name_date
            ON system_metrics(metric_name, recorded_at);
    """)
    conn.commit()
    conn.close()


# ---- Agent Runs ----

def start_run(agent_name, triggered_by="scheduler", context=None):
    run_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO agent_runs VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, agent_name, triggered_by, "running", _now(), None,
         json.dumps(context or {}), 0, None)
    )
    conn.commit()
    conn.close()
    return run_id


def finish_run(run_id, status="completed", token_count=0, error=None):
    conn = get_conn()
    conn.execute(
        "UPDATE agent_runs SET status=?, finished_at=?, token_count=?, error_message=? WHERE agent_run_id=?",
        (status, _now(), token_count, error, run_id)
    )
    conn.commit()
    conn.close()


def get_recent_runs(agent_name=None, limit=20):
    conn = get_conn()
    if agent_name:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE agent_name=? ORDER BY started_at DESC LIMIT ?",
            (agent_name, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Findings ----

def write_finding(agent_run_id, agent_name, category, severity, title,
                  detail, affected_file=None, affected_table=None):
    fid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, agent_run_id, agent_name, category, severity, title,
         detail, affected_file, affected_table, _now(), 0)
    )
    conn.commit()
    conn.close()
    return fid


def get_findings(severity_filter=None, hours_back=24, agent_name=None, unacknowledged_only=False):
    conn = get_conn()
    q = "SELECT * FROM findings WHERE 1=1"
    params = []
    if severity_filter:
        q += " AND severity=?"
        params.append(severity_filter)
    if hours_back:
        q += " AND created_at >= datetime('now', ?)"
        params.append(f"-{hours_back} hours")
    if agent_name:
        q += " AND agent_name=?"
        params.append(agent_name)
    if unacknowledged_only:
        q += " AND acknowledged=0"
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def acknowledge_finding(finding_id, reason=""):
    conn = get_conn()
    conn.execute(
        "UPDATE findings SET acknowledged=1, detail=detail||? WHERE finding_id=?",
        (f"\n\n[Acknowledged: {reason}]", finding_id)
    )
    conn.commit()
    conn.close()


# ---- Reports ----

def write_report(agent_run_id, agent_name, report_type, title, content, data_snapshot=None):
    rid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?)",
        (rid, agent_run_id, agent_name, report_type, title, content,
         json.dumps(data_snapshot or {}), _now())
    )
    conn.commit()
    conn.close()
    return rid


def get_reports(agent_name=None, limit=10):
    conn = get_conn()
    if agent_name:
        rows = conn.execute(
            "SELECT * FROM reports WHERE agent_name=? ORDER BY created_at DESC LIMIT ?",
            (agent_name, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Proposals ----

def write_proposal(agent_run_id, title, rationale, implementation,
                   estimated_effort, priority, finding_id=None):
    pid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid, agent_run_id, finding_id, title, rationale, implementation,
         estimated_effort, priority, "pending", _now(), None, None)
    )
    conn.commit()
    conn.close()
    return pid


def update_proposal_status(proposal_id, status, notes=""):
    conn = get_conn()
    conn.execute(
        "UPDATE proposals SET status=?, reviewed_at=?, reviewer_notes=? WHERE proposal_id=?",
        (status, _now(), notes, proposal_id)
    )
    conn.commit()
    conn.close()


def get_proposals(status_filter=None, limit=50):
    conn = get_conn()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM proposals WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status_filter, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Agent Messages ----

def send_message(sender, recipient, message_type, payload):
    mid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO agent_messages VALUES (?,?,?,?,?,?,?)",
        (mid, sender, recipient, message_type,
         json.dumps(payload), _now(), None)
    )
    conn.commit()
    conn.close()
    return mid


def read_messages(recipient, mark_read=True):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_messages WHERE recipient_agent=? AND read_at IS NULL ORDER BY sent_at ASC",
        (recipient,)
    ).fetchall()
    if mark_read and rows:
        ids = [r["message_id"] for r in rows]
        conn.execute(
            f"UPDATE agent_messages SET read_at=? WHERE message_id IN ({','.join('?'*len(ids))})",
            [_now()] + ids
        )
        conn.commit()
    conn.close()
    return [dict(r) for r in rows]


def get_all_messages(limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_messages ORDER BY sent_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- System Metrics ----

def write_metric(agent_run_id, metric_name, metric_value, metric_unit, context=None):
    mid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO system_metrics VALUES (?,?,?,?,?,?,?)",
        (mid, agent_run_id, metric_name, metric_value,
         metric_unit, json.dumps(context or {}), _now())
    )
    conn.commit()
    conn.close()


def get_metrics(metric_name, hours_back=1, limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM system_metrics WHERE metric_name=? AND recorded_at >= datetime('now',?) ORDER BY recorded_at ASC LIMIT ?",
        (metric_name, f"-{hours_back} hours", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_recent_data(since_iso):
    """Retorna todos los datos nuevos desde una fecha ISO para el dashboard SSE."""
    conn = get_conn()
    result = {}
    for table, date_col in [
        ("agent_runs",     "started_at"),
        ("findings",       "created_at"),
        ("reports",        "created_at"),
        ("proposals",      "created_at"),
        ("system_metrics", "recorded_at"),
        ("agent_messages", "sent_at"),
    ]:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {date_col} > ? ORDER BY {date_col} ASC",
            (since_iso,)
        ).fetchall()
        result[table] = [dict(r) for r in rows]
    conn.close()
    return result
