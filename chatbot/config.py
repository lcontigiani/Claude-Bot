"""
Configuracion central del chatbot.
Editar este archivo para ajustar rutas, modelo y comportamiento.
"""

import os

# --- API ---
# Poner la API key de Anthropic aqui o como variable de entorno
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or "TU_API_KEY_AQUI"

# Modelo a usar
MODEL = "claude-sonnet-4-20250514"

# --- Rutas de datos ---
# Carpeta donde estan los CSV y JSON que el chatbot puede consultar
DATA_DIR = os.environ.get("CHATBOT_DATA_DIR", os.path.join(os.path.dirname(__file__), "datos"))

# --- Servidor ---
HOST = "127.0.0.1"
PORT = 5050

# --- Chatbot ---
MAX_TOKENS = 2048
SYSTEM_PROMPT = """Eres un asistente integrado en una aplicacion web de oficina.
Tu trabajo es ayudar al usuario a:
1. Entender lo que esta viendo en la pantalla.
2. Buscar informacion en las bases de datos disponibles (CSV y JSON).
3. Responder preguntas sobre los datos y procesos de la aplicacion.

Responde siempre en espanol, de forma clara y concisa.
Si el usuario pide datos, usa las herramientas disponibles para consultarlos.
Si no tienes la informacion, dilo honestamente."""
