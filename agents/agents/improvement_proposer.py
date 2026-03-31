"""
ImprovementProposerAgent: Genera propuestas de mejora basadas en findings de otros agentes.
Se activa por scheduler Y por eventos de findings criticos.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core.base_agent import BaseAgent
from core import memory
from core.event_bus import bus

SYSTEM_PROMPT = """Eres un agente especializado en proponer mejoras concretas y accionables.
Recibes findings de otros agentes y generas propuestas detalladas con:
- Titulo claro y conciso
- Razon de por que es importante (rationale)
- Pasos de implementacion especificos (implementation)
- Estimacion honesta de esfuerzo
- Prioridad asignada

Reglas:
- Solo propones cosas que NO esten ya propuestas en proposals existentes
- Cada propuesta debe ser autosuficiente (alguien debe poder implementarla leyendo solo la propuesta)
- Sé realista con el esfuerzo: no subestimes
- Prioridad: critical=riesgo de seguridad o perdida de datos, high=impacto significativo, medium=mejora importante, low=nice-to-have"""

TOOLS = [
    {
        "name": "get_unaddressed_findings",
        "description": "Obtiene findings recientes que aun no tienen propuesta asociada.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                "hours_back":   {"type": "integer"}
            },
            "required": []
        }
    },
    {
        "name": "get_existing_proposals",
        "description": "Lee propuestas existentes para evitar duplicados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {"type": "string"}
            },
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Lee un archivo fuente para entender mejor el contexto de un finding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path":  {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line":   {"type": "integer"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "write_proposal",
        "description": "Guarda una propuesta de mejora en la base de datos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":            {"type": "string"},
                "rationale":        {"type": "string"},
                "implementation":   {"type": "string"},
                "estimated_effort": {"type": "string"},
                "priority":         {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "finding_id":       {"type": "string"}
            },
            "required": ["title", "rationale", "implementation", "estimated_effort", "priority"]
        }
    },
]


class ImprovementProposerAgent(BaseAgent):
    name = "improvement_proposer"
    system_prompt = SYSTEM_PROMPT
    tools = TOOLS

    def __init__(self):
        super().__init__()
        self._current_run_id = None
        # Suscribirse a findings criticos para wakeup inmediato
        bus.subscribe("finding:critical", self._on_critical_finding)

    def _on_critical_finding(self, event_name, data):
        self.logger.info(f"Wakeup por finding critico: {data.get('title')}")
        self.run(
            context={"triggered_finding": data},
            triggered_by="event:finding:critical"
        )

    def _build_task_message(self, context):
        extra = ""
        if context.get("triggered_finding"):
            f = context["triggered_finding"]
            extra = f"\n\nATENCION: Fuiste activado por un finding critico:\nTitulo: {f.get('title')}\nAgente: {f.get('agent')}\nID: {f.get('finding_id')}\nGenera una propuesta para este finding como prioridad."
        return (
            "Revisa los findings recientes de todos los agentes y genera propuestas de mejora.\n"
            "1. Usa get_unaddressed_findings para ver findings sin propuesta (min_severity=warning).\n"
            "2. Usa get_existing_proposals para no duplicar propuestas.\n"
            "3. Para cada finding relevante, usa read_file si necesitas ver el codigo para ser especifico.\n"
            "4. Genera propuestas concretas con write_proposal. Minimo 1, maximo 3 por ejecucion.\n"
            "5. Asigna prioridades correctamente segun impacto real." + extra
        )

    def _get_tool_executor(self):
        def executor(name, args):
            if name == "get_unaddressed_findings":
                all_findings = memory.get_findings(
                    severity_filter=args.get("min_severity"),
                    hours_back=args.get("hours_back", 48),
                    unacknowledged_only=True
                )
                # Filtrar los que ya tienen propuesta
                existing = memory.get_proposals()
                linked_finding_ids = {p["finding_id"] for p in existing if p["finding_id"]}
                return [f for f in all_findings if f["finding_id"] not in linked_finding_ids]

            elif name == "get_existing_proposals":
                return memory.get_proposals(status_filter=args.get("status_filter"))

            elif name == "read_file":
                path = args["file_path"]
                if not os.path.isabs(path):
                    path = os.path.join(cfg.PROJECT_ROOT, path)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    s = (args.get("start_line") or 1) - 1
                    e = args.get("end_line") or len(lines)
                    return {"content": "".join(lines[s:e])[:3000]}
                except Exception as e:
                    return {"error": str(e)}

            elif name == "write_proposal":
                return self.write_proposal(
                    self._current_run_id,
                    args["title"], args["rationale"], args["implementation"],
                    args["estimated_effort"], args["priority"],
                    args.get("finding_id")
                )
            return {"error": f"Herramienta desconocida: {name}"}
        return executor

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
