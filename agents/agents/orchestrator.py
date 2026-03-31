"""
OrchestratorAgent: El cerebro coordinador del sistema.
Usa Claude para razonar sobre el estado del sistema y decidir que hacer.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core.base_agent import BaseAgent
from core import memory
from core.event_bus import bus

SYSTEM_PROMPT = """Eres el orquestador de un sistema multi-agente de IA.
Tu trabajo es revisar el estado del sistema, entender lo que otros agentes han encontrado,
y decidir las acciones necesarias.

Puedes:
- Revisar findings, reportes y propuestas
- Disparar otros agentes cuando sea necesario
- Generar reportes de estado del sistema
- Priorizar problemas criticos

Actua como un tech lead: mira el panorama completo, prioriza inteligentemente,
y asegurate de que nada critico quede sin atender.
Si todo esta bien, simplemente registralo como estado saludable."""

TOOLS = [
    {
        "name": "get_system_overview",
        "description": "Obtiene un panorama completo del sistema: runs recientes, findings sin resolver, propuestas pendientes.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_findings_summary",
        "description": "Obtiene findings recientes agrupados por severidad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_back": {"type": "integer"}
            },
            "required": []
        }
    },
    {
        "name": "get_pending_proposals",
        "description": "Obtiene propuestas pendientes de revision.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "trigger_agent",
        "description": "Dispara la ejecucion de un agente especifico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "enum": ["code_analyst", "data_reporter", "improvement_proposer", "system_monitor"]},
                "reason":     {"type": "string"}
            },
            "required": ["agent_name", "reason"]
        }
    },
    {
        "name": "write_status_report",
        "description": "Genera un reporte de estado general del sistema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":   {"type": "string"},
                "content": {"type": "string"},
                "metrics": {"type": "object"}
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "read_inbox",
        "description": "Lee mensajes pendientes de otros agentes.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
]


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"
    system_prompt = SYSTEM_PROMPT
    tools = TOOLS

    def __init__(self, agent_registry=None):
        super().__init__()
        self._current_run_id = None
        self._agent_registry = agent_registry or {}

    def set_registry(self, registry):
        """Registra los agentes disponibles para poder dispararlos."""
        self._agent_registry = registry

    def _build_task_message(self, context):
        return (
            "Revisa el estado completo del sistema multi-agente.\n"
            "1. Usa read_inbox para ver mensajes de otros agentes.\n"
            "2. Usa get_system_overview para el panorama general.\n"
            "3. Usa get_findings_summary (hours_back=24) para ver problemas recientes.\n"
            "4. Analiza si algun agente necesita correr urgentemente.\n"
            "5. Si hay findings criticos sin propuesta, dispara improvement_proposer.\n"
            "6. Si no hay reporte de datos reciente (>2 horas), dispara data_reporter.\n"
            "7. Genera un write_status_report con el estado actual del sistema.\n"
            "Sé decisivo pero no dispares agentes innecesariamente."
        )

    def _get_tool_executor(self):
        def executor(name, args):
            if name == "get_system_overview":
                return self._get_overview()
            elif name == "get_findings_summary":
                findings = memory.get_findings(hours_back=args.get("hours_back", 24))
                summary = {"critical": [], "warning": [], "info": []}
                for f in findings:
                    sev = f.get("severity", "info")
                    if sev in summary:
                        summary[sev].append({
                            "title": f["title"],
                            "agent": f["agent_name"],
                            "acknowledged": f["acknowledged"]
                        })
                return summary
            elif name == "get_pending_proposals":
                return memory.get_proposals(status_filter="pending")
            elif name == "trigger_agent":
                agent_name = args["agent_name"]
                reason = args.get("reason", "")
                self.logger.info(f"Disparando {agent_name}: {reason}")
                memory.send_message(
                    self.name, agent_name, "trigger",
                    {"reason": reason, "triggered_by": "orchestrator"}
                )
                # Disparar directamente si el agente esta en el registry
                if agent_name in self._agent_registry:
                    import threading
                    agent = self._agent_registry[agent_name]
                    t = threading.Thread(
                        target=agent.run,
                        kwargs={"context": {"reason": reason}, "triggered_by": "orchestrator"},
                        daemon=True
                    )
                    t.start()
                    return {"ok": True, "message": f"{agent_name} disparado en background"}
                return {"ok": True, "message": f"Mensaje enviado a {agent_name}"}
            elif name == "write_status_report":
                return self.write_report(
                    self._current_run_id,
                    "system_status", args["title"], args["content"],
                    args.get("metrics")
                )
            elif name == "read_inbox":
                return memory.read_messages(self.name)
            return {"error": f"Herramienta desconocida: {name}"}
        return executor

    def _get_overview(self):
        runs = memory.get_recent_runs(limit=20)
        # Ultimo run por agente
        last_run = {}
        for r in runs:
            an = r["agent_name"]
            if an not in last_run:
                last_run[an] = {
                    "status": r["status"],
                    "started_at": r["started_at"],
                    "tokens": r["token_count"]
                }
        findings = memory.get_findings(hours_back=24, unacknowledged_only=True)
        proposals = memory.get_proposals(status_filter="pending")
        reports = memory.get_reports(limit=5)
        return {
            "agentes_ultimo_run": last_run,
            "findings_sin_resolver": len(findings),
            "propuestas_pendientes": len(proposals),
            "reportes_recientes": [{"title": r["title"], "agent": r["agent_name"], "date": r["created_at"]} for r in reports],
        }

    def run(self, context=None, triggered_by="scheduler"):
        context = context or {}
        import core.memory as mem
        run_id = mem.start_run(self.name, triggered_by, context)
        self._current_run_id = run_id
        try:
            from core.claude_runner import run_agent_loop
            final_text, tokens = run_agent_loop(
                system_prompt=self.system_prompt,
                tools=self.tools,
                initial_messages=[{"role": "user", "content": self._build_task_message(context)}],
                tool_executor=self._get_tool_executor(),
            )
            mem.finish_run(run_id, status="completed", token_count=tokens)
            self.logger.info(f"Run completado. Tokens: {tokens}")
            bus.publish(f"agent:{self.name}:completed", {"run_id": run_id})
            return {"status": "ok", "run_id": run_id}
        except Exception as e:
            self.logger.error(f"Error: {e}", exc_info=True)
            mem.finish_run(run_id, status="failed", error=str(e))
            return {"status": "error", "error": str(e)}
