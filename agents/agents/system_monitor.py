"""
SystemMonitorAgent: Monitorea la disponibilidad y performance del servidor Flask.
Es el agente mas frecuente (cada 5 minutos).
"""

import os
import sys
import time
import requests
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core.base_agent import BaseAgent
from core import memory

SYSTEM_PROMPT = """Eres un agente de monitoreo de sistemas. Tu trabajo es:
1. Verificar que el servidor Flask del chatbot este corriendo y respondiendo correctamente.
2. Medir tiempos de respuesta y comparar con el historial.
3. Revisar recursos del sistema (CPU, memoria, disco).
4. Generar alertas (findings) cuando algo este degradado o caido.
5. Escribir metricas para construir el historial de performance.

Se conciso. Si todo esta bien, registra las metricas y termina.
Si algo esta mal, genera un finding con severity apropiada."""

TOOLS = [
    {
        "name": "probe_endpoint",
        "description": "Hace un request HTTP al servidor y mide el tiempo de respuesta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":        {"type": "string"},
                "method":     {"type": "string", "enum": ["GET", "POST"]},
                "payload":    {"type": "object"},
                "timeout_ms": {"type": "integer"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_metric_history",
        "description": "Obtiene el historial de una metrica para comparar con la situacion actual.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_name": {"type": "string"},
                "hours_back":  {"type": "integer"}
            },
            "required": ["metric_name"]
        }
    },
    {
        "name": "write_metric",
        "description": "Registra una metrica de sistema en la base de datos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_name":  {"type": "string"},
                "metric_value": {"type": "number"},
                "metric_unit":  {"type": "string"},
                "context":      {"type": "object"}
            },
            "required": ["metric_name", "metric_value", "metric_unit"]
        }
    },
    {
        "name": "get_system_resources",
        "description": "Obtiene uso de CPU, memoria y disco del servidor.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "write_finding",
        "description": "Registra un problema o alerta detectada.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["performance", "availability", "security", "opportunity"]},
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                "title":    {"type": "string"},
                "detail":   {"type": "string"}
            },
            "required": ["category", "severity", "title", "detail"]
        }
    },
]


class SystemMonitorAgent(BaseAgent):
    name = "system_monitor"
    system_prompt = SYSTEM_PROMPT
    tools = TOOLS

    def __init__(self):
        super().__init__()
        self._current_run_id = None

    def _build_task_message(self, context):
        return (
            f"Monitorea el servidor Flask en {cfg.CHATBOT_BASE_URL}. "
            "Verifica los endpoints /api/archivos y /. "
            "Compara los tiempos de respuesta con el historial de la ultima hora. "
            "Registra las metricas y genera findings si algo no esta dentro de lo normal. "
            "Tambien revisa los recursos del sistema."
        )

    def _get_tool_executor(self):
        def executor(name, args):
            if name == "probe_endpoint":
                return self._probe_endpoint(**args)
            elif name == "get_metric_history":
                rows = memory.get_metrics(args["metric_name"], args.get("hours_back", 1))
                return [{"recorded_at": r["recorded_at"], "value": r["metric_value"]} for r in rows]
            elif name == "write_metric":
                memory.write_metric(
                    self._current_run_id,
                    args["metric_name"],
                    args["metric_value"],
                    args["metric_unit"],
                    args.get("context")
                )
                return {"ok": True}
            elif name == "get_system_resources":
                return {
                    "cpu_percent":    psutil.cpu_percent(interval=1),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent":   psutil.disk_usage("/").percent,
                }
            elif name == "write_finding":
                return self.write_finding(
                    self._current_run_id,
                    args["category"], args["severity"],
                    args["title"], args["detail"]
                )
            return {"error": f"Herramienta desconocida: {name}"}
        return executor

    def run(self, context=None, triggered_by="scheduler"):
        result = super().run(context, triggered_by)
        return result

    def _probe_endpoint(self, url, method="GET", payload=None, timeout_ms=5000):
        try:
            start = time.time()
            if method == "POST":
                resp = requests.post(url, json=payload, timeout=timeout_ms / 1000)
            else:
                resp = requests.get(url, timeout=timeout_ms / 1000)
            elapsed = round((time.time() - start) * 1000, 1)
            return {
                "status_code":    resp.status_code,
                "response_ms":    elapsed,
                "ok":             resp.status_code == 200,
                "body_snippet":   resp.text[:200],
            }
        except requests.exceptions.ConnectionError:
            return {"error": "Connection refused - servidor no disponible", "ok": False}
        except requests.exceptions.Timeout:
            return {"error": f"Timeout despues de {timeout_ms}ms", "ok": False}
        except Exception as e:
            return {"error": str(e), "ok": False}

    # Guardamos el run_id para usarlo en el executor
    def _build_task_message(self, context):
        return (
            f"Monitorea el servidor Flask en {cfg.CHATBOT_BASE_URL}. "
            "Usa probe_endpoint para verificar GET / y GET /api/archivos. "
            "Usa get_metric_history para 'api_response_ms' de la ultima hora y compara. "
            "Registra metricas con write_metric para cada endpoint probado. "
            "Usa get_system_resources para ver estado del hardware. "
            "Si el servidor no responde o tarda mas del doble del promedio historico, "
            "genera un finding con severity=critical. "
            "Si los recursos superan 85% de uso, genera finding severity=warning."
        )

    def run(self, context=None, triggered_by="scheduler"):
        context = context or {}
        import core.memory as mem
        run_id = mem.start_run(self.name, triggered_by, context)
        self._current_run_id = run_id

        try:
            from core.claude_runner import run_agent_loop
            task_message = self._build_task_message(context)
            final_text, tokens = run_agent_loop(
                system_prompt=self.system_prompt,
                tools=self.tools,
                initial_messages=[{"role": "user", "content": task_message}],
                tool_executor=self._get_tool_executor(),
            )
            mem.finish_run(run_id, status="completed", token_count=tokens)
            self.logger.info(f"Run completado. Tokens: {tokens}")
            from core.event_bus import bus
            bus.publish(f"agent:{self.name}:completed", {"run_id": run_id})
            return {"status": "ok", "run_id": run_id}
        except Exception as e:
            self.logger.error(f"Error: {e}", exc_info=True)
            mem.finish_run(run_id, status="failed", error=str(e))
            return {"status": "error", "error": str(e)}
