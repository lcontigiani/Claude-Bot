"""
Servidor Flask del dashboard de agentes.
Corre en puerto 5051. Sirve la UI y expone la API para el frontend.
"""

import json
import time
import sys
import os
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, Response, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core import memory

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)


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


def run_dashboard():
    """Inicia el servidor del dashboard (llamado desde run_agents.py en un thread)."""
    app.run(host="127.0.0.1", port=cfg.DASHBOARD_PORT, debug=False, use_reloader=False)
