"""
Clase base para todos los agentes del sistema.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core import memory
from core.claude_runner import run_agent_loop
from core.event_bus import bus

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


class BaseAgent:
    """
    Clase base abstracta.
    Cada agente hereda de esta y define:
      - self.name
      - self.system_prompt
      - self.tools
      - self._build_task_message(context) -> str
      - self._get_tool_executor() -> callable
    """

    name = "base_agent"
    system_prompt = "Eres un agente de IA."
    tools = []

    def __init__(self):
        self.logger = logging.getLogger(self.name)
        self._register_subscriptions()

    def _register_subscriptions(self):
        """Override para suscribirse a eventos del bus."""
        pass

    def run(self, context=None, triggered_by="scheduler"):
        """Ejecuta el agente. Registra en DB, llama a Claude, guarda resultado."""
        context = context or {}
        self.logger.info(f"Iniciando run (triggered_by={triggered_by})")
        run_id = memory.start_run(self.name, triggered_by, context)

        try:
            task_message = self._build_task_message(context)
            initial_messages = [{"role": "user", "content": task_message}]

            final_text, tokens = run_agent_loop(
                system_prompt=self.system_prompt,
                tools=self.tools,
                initial_messages=initial_messages,
                tool_executor=self._get_tool_executor(),
            )

            memory.finish_run(run_id, status="completed", token_count=tokens)
            self.logger.info(f"Run completado. Tokens: {tokens}")
            bus.publish(f"agent:{self.name}:completed", {"run_id": run_id, "tokens": tokens})
            return {"status": "ok", "run_id": run_id, "summary": final_text[:300]}

        except Exception as e:
            self.logger.error(f"Error en run: {e}", exc_info=True)
            memory.finish_run(run_id, status="failed", error=str(e))
            bus.publish(f"agent:{self.name}:failed", {"run_id": run_id, "error": str(e)})
            return {"status": "error", "run_id": run_id, "error": str(e)}

    def _build_task_message(self, context):
        return "Ejecuta tu tarea segun las instrucciones."

    def _get_tool_executor(self):
        raise NotImplementedError

    # --- Helpers para escribir en memoria ---

    def write_finding(self, run_id, category, severity, title, detail,
                      affected_file=None, affected_table=None):
        fid = memory.write_finding(
            run_id, self.name, category, severity, title, detail,
            affected_file, affected_table
        )
        if severity == "critical":
            bus.publish("finding:critical", {"finding_id": fid, "title": title, "agent": self.name})
        self.logger.info(f"Finding [{severity}]: {title}")
        return fid

    def write_report(self, run_id, report_type, title, content, data_snapshot=None):
        rid = memory.write_report(run_id, self.name, report_type, title, content, data_snapshot)
        bus.publish(f"report:{self.name}:new", {"report_id": rid, "title": title})
        self.logger.info(f"Reporte generado: {title}")
        return rid

    def write_proposal(self, run_id, title, rationale, implementation,
                       effort, priority, finding_id=None):
        pid = memory.write_proposal(
            run_id, title, rationale, implementation, effort, priority, finding_id
        )
        bus.publish("proposal:new", {"proposal_id": pid, "priority": priority})
        self.logger.info(f"Propuesta [{priority}]: {title}")
        return pid

    def send_message(self, recipient, message_type, payload):
        memory.send_message(self.name, recipient, message_type, payload)

    def read_inbox(self):
        return memory.read_messages(self.name)
