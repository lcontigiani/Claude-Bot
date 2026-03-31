"""
CodeAnalystAgent: Analiza el codigo fuente del proyecto buscando problemas y mejoras.
"""

import os
import sys
import re
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core.base_agent import BaseAgent
from core import memory

SYSTEM_PROMPT = """Eres un agente experto en analisis de codigo. Inspeccionas archivos Python y JavaScript
buscando problemas reales y mejoras concretas. Para cada problema que encuentres:
- Cita el archivo y numero de linea aproximado
- Explica por que es un problema
- Sugiere la solucion concreta

Categorias de findings: code_quality, security, performance, opportunity.
Severidades: info (sugerencia), warning (deberia corregirse), critical (riesgo real).

No generes findings duplicados. Antes de escribir uno, revisa si ya existe algo similar."""

TOOLS = [
    {
        "name": "list_source_files",
        "description": "Lista archivos de codigo fuente del proyecto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "extension": {"type": "string", "description": "Ej: .py, .js, .html, .css"}
            },
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo fuente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string"},
                "start_line":  {"type": "integer"},
                "end_line":    {"type": "integer"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "search_pattern",
        "description": "Busca un patron regex en los archivos del proyecto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern":    {"type": "string"},
                "extension":  {"type": "string"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "get_previous_findings",
        "description": "Obtiene findings previos del agente para evitar duplicados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_back": {"type": "integer"}
            },
            "required": []
        }
    },
    {
        "name": "write_finding",
        "description": "Registra un problema encontrado en el codigo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category":      {"type": "string", "enum": ["code_quality", "security", "performance", "opportunity"]},
                "severity":      {"type": "string", "enum": ["info", "warning", "critical"]},
                "title":         {"type": "string"},
                "detail":        {"type": "string"},
                "affected_file": {"type": "string"}
            },
            "required": ["category", "severity", "title", "detail"]
        }
    },
]


class CodeAnalystAgent(BaseAgent):
    name = "code_analyst"
    system_prompt = SYSTEM_PROMPT
    tools = TOOLS

    def __init__(self):
        super().__init__()
        self._current_run_id = None

    def _build_task_message(self, context):
        return (
            f"Analiza el codigo fuente del proyecto en: {cfg.PROJECT_ROOT}\n"
            "1. Usa list_source_files para ver que archivos hay (.py, .js, .html).\n"
            "2. Lee los archivos clave: chatbot/server.py, chatbot/config.py, chatbot/data_loader.py, chatbot/static/chatbot-widget.js\n"
            "3. Busca patrones problematicos: API keys hardcodeadas, falta de manejo de errores, "
            "vulnerabilidades XSS, falta de validacion de inputs, codigo duplicado.\n"
            "4. Revisa findings previos para no duplicar.\n"
            "5. Genera findings concretos con archivo y linea aproximada.\n"
            "Analiza al menos 3 archivos y genera al menos 2 findings."
        )

    def _get_tool_executor(self):
        def executor(name, args):
            if name == "list_source_files":
                return self._list_files(args.get("extension"))
            elif name == "read_file":
                return self._read_file(
                    args["file_path"],
                    args.get("start_line"),
                    args.get("end_line")
                )
            elif name == "search_pattern":
                return self._search_pattern(args["pattern"], args.get("extension"))
            elif name == "get_previous_findings":
                return memory.get_findings(
                    agent_name=self.name,
                    hours_back=args.get("hours_back", 48)
                )
            elif name == "write_finding":
                return self.write_finding(
                    self._current_run_id,
                    args["category"], args["severity"],
                    args["title"], args["detail"],
                    args.get("affected_file")
                )
            return {"error": f"Herramienta desconocida: {name}"}
        return executor

    def _list_files(self, extension=None):
        result = []
        for root, dirs, files in os.walk(cfg.PROJECT_ROOT):
            # Ignorar venv, __pycache__, .git
            dirs[:] = [d for d in dirs if d not in ("venv", "__pycache__", ".git", "node_modules")]
            for f in files:
                if extension is None or f.endswith(extension):
                    rel = os.path.relpath(os.path.join(root, f), cfg.PROJECT_ROOT)
                    result.append(rel)
        return result

    def _read_file(self, file_path, start_line=None, end_line=None):
        # Resolver ruta relativa o absoluta
        if not os.path.isabs(file_path):
            file_path = os.path.join(cfg.PROJECT_ROOT, file_path)
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if start_line or end_line:
                s = (start_line or 1) - 1
                e = end_line or len(lines)
                lines = lines[s:e]
            content = "".join(lines)
            return {"file": file_path, "lines": len(lines), "content": content[:4000]}
        except Exception as e:
            return {"error": str(e)}

    def _search_pattern(self, pattern, extension=None):
        results = []
        try:
            for root, dirs, files in os.walk(cfg.PROJECT_ROOT):
                dirs[:] = [d for d in dirs if d not in ("venv", "__pycache__", ".git")]
                for f in files:
                    if extension and not f.endswith(extension):
                        continue
                    path = os.path.join(root, f)
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as fh:
                            for i, line in enumerate(fh, 1):
                                if re.search(pattern, line):
                                    results.append({
                                        "file": os.path.relpath(path, cfg.PROJECT_ROOT),
                                        "line": i,
                                        "content": line.strip()[:120]
                                    })
                    except Exception:
                        pass
                    if len(results) >= 50:
                        break
        except Exception as e:
            return {"error": str(e)}
        return results

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
            from core.event_bus import bus
            bus.publish(f"agent:{self.name}:completed", {"run_id": run_id})
            return {"status": "ok", "run_id": run_id}
        except Exception as e:
            self.logger.error(f"Error: {e}", exc_info=True)
            mem.finish_run(run_id, status="failed", error=str(e))
            return {"status": "error", "error": str(e)}
