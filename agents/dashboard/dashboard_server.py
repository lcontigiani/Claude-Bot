"""
Servidor Flask del dashboard de agentes.
Corre en puerto 5051. Sirve la UI y expone la API para el frontend.
Incluye controles de pausa/reanudacion/shutdown del scheduler.
"""

import json
import time
import sys
import os
import threading
import signal
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, Response, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core import memory

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# ---- Referencias al scheduler y agentes (inyectadas por run_agents.py) ----
_scheduler = None
_agents = {}


def set_scheduler_ref(scheduler):
    global _scheduler
    _scheduler = scheduler


def set_agents_ref(agents):
    global _agents
    _agents = agents


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---- Paginas ----

@app.route("/")
def index():
    return render_template("dashboard.html")


# ---- API REST ----

@app.route("/api/summary")
def summary():
    """Snapshot completo del estado actual."""
    runs = memory.get_recent_runs(limit=30)
    # Ultimo run y estado por agente
    agent_status = {}
    for r in runs:
        an = r["agent_name"]
        if an not in agent_status:
            agent_status[an] = {
                "last_run":    r["started_at"],
                "status":      r["status"],
                "tokens":      r["token_count"],
                "error":       r["error_message"],
            }

    return jsonify({
        "agent_status":   agent_status,
        "findings":       memory.get_findings(hours_back=48),
        "reports":        memory.get_reports(limit=10),
        "proposals":      memory.get_proposals(),
        "messages":       memory.get_all_messages(limit=50),
        "metrics":        memory.get_metrics("api_response_ms", hours_back=2),
    })


@app.route("/api/stream")
def stream():
    """Server-Sent Events: emite nuevos datos cada 3 segundos."""
    def generate():
        last_check = _now_iso()
        # Emitir snapshot inicial
        data = memory.get_all_recent_data("2000-01-01T00:00:00+00:00")
        yield f"event: snapshot\ndata: {json.dumps(data, default=str)}\n\n"

        while True:
            time.sleep(3)
            new_data = memory.get_all_recent_data(last_check)
            last_check = _now_iso()
            has_data = any(len(v) > 0 for v in new_data.values())
            if has_data:
                yield f"event: update\ndata: {json.dumps(new_data, default=str)}\n\n"
            else:
                yield f"event: ping\ndata: {{}}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/proposals/<proposal_id>/status", methods=["POST"])
def update_proposal(proposal_id):
    data = request.get_json()
    status = data.get("status")
    notes = data.get("notes", "")
    if status not in ("accepted", "rejected", "in_progress", "done"):
        return jsonify({"error": "Status invalido"}), 400
    memory.update_proposal_status(proposal_id, status, notes)
    return jsonify({"ok": True})


@app.route("/api/findings/<finding_id>/acknowledge", methods=["POST"])
def acknowledge(finding_id):
    data = request.get_json() or {}
    memory.acknowledge_finding(finding_id, data.get("reason", "Acknowledged desde dashboard"))
    return jsonify({"ok": True})


@app.route("/api/runs")
def runs():
    agent = request.args.get("agent")
    limit = int(request.args.get("limit", 50))
    return jsonify(memory.get_recent_runs(agent_name=agent, limit=limit))


# ---- Control del Scheduler ----

@app.route("/api/control/status")
def control_status():
    """Estado actual del scheduler y cada agente."""
    if not _scheduler:
        return jsonify({"error": "Scheduler no inicializado"}), 503

    running = _scheduler.running
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id":           job.id,
            "name":         job.name,
            "next_run":     str(job.next_run_time) if job.next_run_time else None,
            "paused":       job.next_run_time is None,
        })

    return jsonify({
        "scheduler_running": running,
        "jobs": jobs,
    })


@app.route("/api/control/pause-all", methods=["POST"])
def pause_all():
    """Pausa TODOS los agentes. No consumen API hasta reanudar."""
    if not _scheduler:
        return jsonify({"error": "Scheduler no inicializado"}), 503
    _scheduler.pause()
    return jsonify({"ok": True, "message": "Todos los agentes pausados. No se consumira API."})


@app.route("/api/control/resume-all", methods=["POST"])
def resume_all():
    """Reanuda TODOS los agentes."""
    if not _scheduler:
        return jsonify({"error": "Scheduler no inicializado"}), 503
    _scheduler.resume()
    return jsonify({"ok": True, "message": "Todos los agentes reanudados."})


@app.route("/api/control/pause/<agent_id>", methods=["POST"])
def pause_agent(agent_id):
    """Pausa un agente individual por su ID."""
    if not _scheduler:
        return jsonify({"error": "Scheduler no inicializado"}), 503
    try:
        _scheduler.pause_job(agent_id)
        return jsonify({"ok": True, "message": f"Agente '{agent_id}' pausado."})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/control/resume/<agent_id>", methods=["POST"])
def resume_agent(agent_id):
    """Reanuda un agente individual por su ID."""
    if not _scheduler:
        return jsonify({"error": "Scheduler no inicializado"}), 503
    try:
        _scheduler.resume_job(agent_id)
        return jsonify({"ok": True, "message": f"Agente '{agent_id}' reanudado."})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/control/run/<agent_id>", methods=["POST"])
def run_agent_now(agent_id):
    """Ejecuta un agente manualmente una sola vez (aun si esta pausado)."""
    if agent_id not in _agents:
        return jsonify({"error": f"Agente '{agent_id}' no encontrado"}), 404
    agent = _agents[agent_id]
    t = threading.Thread(
        target=agent.run,
        kwargs={"triggered_by": "manual_dashboard"},
        daemon=True,
    )
    t.start()
    return jsonify({"ok": True, "message": f"Agente '{agent_id}' ejecutandose en background."})


@app.route("/api/control/shutdown", methods=["POST"])
def shutdown_system():
    """Detiene completamente el scheduler y termina el proceso."""
    if _scheduler:
        _scheduler.shutdown(wait=False)
    # Dar tiempo a que responda antes de morir
    def _kill():
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_kill, daemon=True).start()
    return jsonify({"ok": True, "message": "Sistema detenido. El proceso terminara en 1 segundo."})


def run_dashboard():
    """Inicia el servidor del dashboard (llamado desde run_agents.py en un thread)."""
    app.run(host="127.0.0.1", port=cfg.DASHBOARD_PORT, debug=False, use_reloader=False)
