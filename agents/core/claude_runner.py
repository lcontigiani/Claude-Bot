"""
Loop de tool-use de Claude reutilizable para todos los agentes.
Mismo patron que server.py, generalizado.
"""

import json
import anthropic
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg

# Cliente compartido (thread-safe)
_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
    return _client


def run_agent_loop(system_prompt, tools, initial_messages,
                   tool_executor, max_iterations=10):
    """
    Ejecuta el loop de tool-use de Claude para un agente.

    Args:
        system_prompt:     Prompt de sistema del agente
        tools:             Lista de definiciones de herramientas
        initial_messages:  Lista de mensajes iniciales [{"role": "user", "content": "..."}]
        tool_executor:     Funcion(name, args) -> resultado que ejecuta cada herramienta
        max_iterations:    Maximo de rondas tool-use

    Returns:
        (texto_final, total_tokens)
    """
    client = get_client()
    messages = list(initial_messages)
    total_tokens = 0
    iterations = 0

    response = client.messages.create(
        model=cfg.MODEL,
        max_tokens=cfg.MAX_AGENT_TOKENS,
        system=system_prompt,
        tools=tools,
        messages=messages,
    )
    total_tokens += response.usage.input_tokens + response.usage.output_tokens

    while response.stop_reason == "tool_use" and iterations < max_iterations:
        iterations += 1
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = tool_executor(block.name, block.input)
                except Exception as e:
                    result = {"error": str(e)}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model=cfg.MODEL,
            max_tokens=cfg.MAX_AGENT_TOKENS,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

    # Extraer texto final
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    return final_text, total_tokens
