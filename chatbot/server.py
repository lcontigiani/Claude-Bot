"""
Servidor Flask que expone el API del chatbot.
Recibe mensajes del frontend, consulta datos locales y responde usando Claude.
"""

import json
import traceback
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic

import config
import data_loader

app = Flask(__name__, static_folder="static")
CORS(app)

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# ---- Definicion de herramientas para Claude ----

TOOLS = [
    {
        "name": "listar_archivos",
        "description": "Lista todos los archivos de datos (CSV y JSON) disponibles en el sistema. Usar cuando el usuario pregunte que datos hay o que archivos existen.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "leer_csv",
        "description": "Lee un archivo CSV. Puede aplicar filtros por columna. Usar cuando el usuario pida datos de un CSV especifico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_archivo": {
                    "type": "string",
                    "description": "Nombre del archivo CSV (ej: ventas.csv)",
                },
                "filtros": {
                    "type": "object",
                    "description": "Filtros a aplicar. Clave = nombre de columna, valor = texto a buscar. Ejemplo: {\"ciudad\": \"Madrid\"}",
                },
                "limite": {
                    "type": "integer",
                    "description": "Cantidad maxima de filas a devolver (default 50).",
                },
            },
            "required": ["nombre_archivo"],
        },
    },
    {
        "name": "leer_json",
        "description": "Lee un archivo JSON y devuelve un resumen de su contenido. Usar cuando el usuario pregunte por datos en archivos JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_archivo": {
                    "type": "string",
                    "description": "Nombre del archivo JSON (ej: config.json)",
                },
            },
            "required": ["nombre_archivo"],
        },
    },
    {
        "name": "resumen_datos",
        "description": "Genera un resumen general de todos los archivos de datos disponibles, incluyendo columnas de CSVs. Usar al inicio o cuando el usuario quiera una vision general.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def ejecutar_herramienta(nombre, argumentos):
    """Ejecuta una herramienta y devuelve el resultado."""
    if nombre == "listar_archivos":
        return data_loader.listar_archivos()
    elif nombre == "leer_csv":
        return data_loader.leer_csv(
            argumentos["nombre_archivo"],
            filtros=argumentos.get("filtros"),
            limite=argumentos.get("limite", 50),
        )
    elif nombre == "leer_json":
        return data_loader.leer_json(argumentos["nombre_archivo"])
    elif nombre == "resumen_datos":
        return data_loader.resumen_datos()
    else:
        return {"error": f"Herramienta '{nombre}' no reconocida."}


# ---- Endpoints ----


@app.route("/")
def index():
    return send_from_directory("static", "demo.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """Endpoint principal del chatbot. Recibe mensajes y devuelve respuesta."""
    try:
        data = request.get_json()
        mensajes = data.get("messages", [])
        contexto_pagina = data.get("page_context", "")

        system_prompt = config.SYSTEM_PROMPT
        if contexto_pagina:
            system_prompt += f"\n\nContexto actual de la pagina que el usuario esta viendo:\n{contexto_pagina}"

        # Primera llamada a Claude
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=system_prompt,
            tools=TOOLS,
            messages=mensajes,
        )

        # Procesar tool_use en bucle hasta obtener respuesta final
        while response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    resultado = ejecutar_herramienta(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(resultado, ensure_ascii=False, default=str),
                    })

            # Agregar respuesta del asistente y resultados de herramientas
            mensajes.append({"role": "assistant", "content": response.content})
            mensajes.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                system=system_prompt,
                tools=TOOLS,
                messages=mensajes,
            )

        # Extraer texto de la respuesta final
        texto_respuesta = ""
        for block in response.content:
            if hasattr(block, "text"):
                texto_respuesta += block.text

        return jsonify({"response": texto_respuesta, "status": "ok"})

    except anthropic.AuthenticationError:
        return jsonify({"response": "Error: API key invalida. Revisa config.py.", "status": "error"}), 401
    except Exception as e:
        traceback.print_exc()
        return jsonify({"response": f"Error interno: {str(e)}", "status": "error"}), 500


@app.route("/api/archivos", methods=["GET"])
def archivos():
    """Lista archivos de datos disponibles."""
    return jsonify(data_loader.listar_archivos())


@app.route("/api/resumen", methods=["GET"])
def resumen():
    """Devuelve resumen de todos los datos."""
    return jsonify(data_loader.resumen_datos())


if __name__ == "__main__":
    print(f"Chatbot server iniciando en http://{config.HOST}:{config.PORT}")
    print(f"Directorio de datos: {config.DATA_DIR}")
    app.run(host=config.HOST, port=config.PORT, debug=True)
