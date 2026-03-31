"""
DataReporterAgent: Analiza archivos CSV/JSON y genera reportes de datos.
"""

import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg
from core.base_agent import BaseAgent
from core import memory

SYSTEM_PROMPT = """Eres un agente analista de datos. Examinas archivos CSV y JSON para encontrar:
- Estadisticas clave (conteos, promedios, distribuciones)
- Anomalias y problemas de calidad de datos
- Tendencias y patrones
- Inconsistencias entre archivos

Genera reportes claros con numeros concretos. Si encuentras problemas de calidad de datos,
crea findings. Siempre incluye un resumen ejecutivo al inicio del reporte."""

TOOLS = [
    {
        "name": "list_data_files",
        "description": "Lista todos los archivos de datos disponibles.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "read_csv_stats",
        "description": "Lee un CSV y devuelve estadisticas completas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename":        {"type": "string"},
                "group_by_column": {"type": "string"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "read_csv_sample",
        "description": "Lee una muestra de un CSV con filtros opcionales.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "filters":  {"type": "object"},
                "limit":    {"type": "integer"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "read_json_file",
        "description": "Lee y resume un archivo JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "detect_anomalies",
        "description": "Detecta valores anomalos en una columna numerica usando z-score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "column":   {"type": "string"}
            },
            "required": ["filename", "column"]
        }
    },
    {
        "name": "write_report",
        "description": "Guarda un reporte generado en la base de datos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "report_type":   {"type": "string", "enum": ["data_summary", "data_quality", "weekly_digest"]},
                "title":         {"type": "string"},
                "content":       {"type": "string"},
                "data_snapshot": {"type": "object"}
            },
            "required": ["report_type", "title", "content"]
        }
    },
    {
        "name": "write_finding",
        "description": "Registra un problema de calidad de datos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category":       {"type": "string", "enum": ["data_anomaly", "opportunity"]},
                "severity":       {"type": "string", "enum": ["info", "warning", "critical"]},
                "title":          {"type": "string"},
                "detail":         {"type": "string"},
                "affected_table": {"type": "string"}
            },
            "required": ["category", "severity", "title", "detail"]
        }
    },
]


class DataReporterAgent(BaseAgent):
    name = "data_reporter"
    system_prompt = SYSTEM_PROMPT
    tools = TOOLS

    def __init__(self):
        super().__init__()
        self._current_run_id = None

    def _build_task_message(self, context):
        return (
            f"Analiza todos los archivos de datos en {cfg.DATA_DIR}.\n"
            "1. Usa list_data_files para ver los archivos disponibles.\n"
            "2. Para cada CSV, usa read_csv_stats para obtener estadisticas completas.\n"
            "3. Intenta agrupar por columnas categoricas relevantes (departamento, estado, etc).\n"
            "4. Busca problemas de calidad: valores nulos, formatos incorrectos, inconsistencias.\n"
            "5. Genera un reporte data_summary con los hallazgos principales.\n"
            "6. Si encuentras anomalias importantes, genera findings."
        )

    def _get_tool_executor(self):
        def executor(name, args):
            if name == "list_data_files":
                return self._list_data_files()
            elif name == "read_csv_stats":
                return self._read_csv_stats(args["filename"], args.get("group_by_column"))
            elif name == "read_csv_sample":
                return self._read_csv_sample(args["filename"], args.get("filters"), args.get("limit", 20))
            elif name == "read_json_file":
                return self._read_json(args["filename"])
            elif name == "detect_anomalies":
                return self._detect_anomalies(args["filename"], args["column"])
            elif name == "write_report":
                return self.write_report(
                    self._current_run_id,
                    args["report_type"], args["title"], args["content"],
                    args.get("data_snapshot")
                )
            elif name == "write_finding":
                return self.write_finding(
                    self._current_run_id,
                    args["category"], args["severity"],
                    args["title"], args["detail"],
                    affected_table=args.get("affected_table")
                )
            return {"error": f"Herramienta desconocida: {name}"}
        return executor

    def _list_data_files(self):
        if not os.path.isdir(cfg.DATA_DIR):
            return []
        files = []
        for f in os.listdir(cfg.DATA_DIR):
            if f.endswith((".csv", ".json")):
                path = os.path.join(cfg.DATA_DIR, f)
                files.append({"nombre": f, "tamano_kb": round(os.path.getsize(path) / 1024, 1)})
        return files

    def _read_csv_stats(self, filename, group_by=None):
        path = os.path.join(cfg.DATA_DIR, filename)
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            stats = {
                "archivo":        filename,
                "total_filas":    len(df),
                "total_columnas": len(df.columns),
                "columnas":       list(df.columns),
                "nulos_por_col":  df.isnull().sum().to_dict(),
                "tipos":          {c: str(t) for c, t in df.dtypes.items()},
            }
            # Estadisticas de columnas numericas
            num_cols = df.select_dtypes(include="number").columns.tolist()
            if num_cols:
                stats["estadisticas_numericas"] = df[num_cols].describe().to_dict()
            # Frecuencias de columnas categoricas
            cat_cols = df.select_dtypes(include="object").columns.tolist()
            stats["frecuencias"] = {}
            for col in cat_cols[:5]:
                stats["frecuencias"][col] = df[col].value_counts().head(10).to_dict()
            # Group by
            if group_by and group_by in df.columns:
                stats["agrupado_por"] = group_by
                stats["conteo_por_grupo"] = df.groupby(group_by).size().to_dict()
            return stats
        except Exception as e:
            return {"error": str(e)}

    def _read_csv_sample(self, filename, filters=None, limit=20):
        path = os.path.join(cfg.DATA_DIR, filename)
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            if filters:
                for col, val in filters.items():
                    if col in df.columns:
                        df = df[df[col].astype(str).str.contains(str(val), case=False, na=False)]
            return {"datos": df.head(limit).to_dict(orient="records"), "total": len(df)}
        except Exception as e:
            return {"error": str(e)}

    def _read_json(self, filename):
        path = os.path.join(cfg.DATA_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {"tipo": "lista", "total": len(data), "muestra": data[:5]}
            elif isinstance(data, dict):
                return {"tipo": "diccionario", "claves": list(data.keys()), "contenido": data}
        except Exception as e:
            return {"error": str(e)}

    def _detect_anomalies(self, filename, column):
        path = os.path.join(cfg.DATA_DIR, filename)
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            if column not in df.columns:
                return {"error": f"Columna '{column}' no existe"}
            col = pd.to_numeric(df[column], errors="coerce").dropna()
            if len(col) < 3:
                return {"error": "Datos insuficientes para detectar anomalias"}
            mean, std = col.mean(), col.std()
            if std == 0:
                return {"anomalias": [], "mean": mean, "std": 0}
            z_scores = ((col - mean) / std).abs()
            anomalies = df[z_scores > 2.5][[column]].to_dict(orient="records")
            return {"columna": column, "mean": round(mean, 2), "std": round(std, 2), "anomalias": anomalies[:10]}
        except Exception as e:
            return {"error": str(e)}

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
