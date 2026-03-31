"""
Configuracion central del sistema multi-agente.
"""

import os
import sys

# Ruta raiz del proyecto
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Agregar el chatbot al path para reusar config.py
sys.path.insert(0, os.path.join(PROJECT_ROOT, "chatbot"))

# API Key (comparte la misma que el chatbot)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or "TU_API_KEY_AQUI"

# Modelo
MODEL = "claude-sonnet-4-20250514"

# Base de datos SQLite de agentes
DB_PATH = os.path.join(os.path.dirname(__file__), "agent_memory.db")

# Puertos
CHATBOT_BASE_URL = "http://127.0.0.1:5050"
DASHBOARD_PORT   = 5051

# Directorio de datos (mismo que el chatbot)
DATA_DIR = os.path.join(PROJECT_ROOT, "chatbot", "datos")

# Tokens maximos por llamada de agente
MAX_AGENT_TOKENS = 4096

# Timezone del scheduler
SCHEDULER_TIMEZONE = "America/Argentina/Buenos_Aires"

# Log level
LOG_LEVEL = "INFO"
