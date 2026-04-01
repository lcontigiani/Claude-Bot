"""
Agente especializado en la gestion de proyectos/workflows del chatbot.
Orquesta el intake conversacional de datos, la validacion y la ejecucion del workflow.
"""

import json
import traceback
import anthropic

import config
import project_db
import code_introspector
import workflow_registry
import workflow_executor

# Cliente Anthropic (instancia unica del modulo)
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Modelo a usar para las llamadas internas del agente
_MODEL = config.MODEL
_MAX_TOKENS = 1024


class ProjectAgent:
    """Agente que gestiona el ciclo de vida de un workflow mediante conversacion.

    Flujo general:
    1. start()          — Introspecciona la funcion del workflow, planifica el intake,
                          guarda preguntas en BD y formula la primera pregunta al usuario.
    2. continue_conversation() — Procesa la respuesta del usuario, la valida, guarda en BD,
                                 y decide si preguntar lo siguiente o ejecutar el workflow.

    El agente usa llamadas directas al cliente Anthropic (sin run_agent_loop) para
    operaciones puntuales: generar preguntas naturales y parsear/validar respuestas.
    """

    # --- Mensajes de sistema para cada tipo de llamada LLM interna ---

    _SYSTEM_QUESTION = """Eres el asistente de una empresa de oficina que guia al usuario
en el proceso de generacion de documentos internos (cotizaciones, informes).
Tu tarea es formular UNA sola pregunta en espanol para recopilar la informacion indicada.
La pregunta debe ser clara, amigable y precisa. No expliques el proceso, solo formula la pregunta.
Si el parametro tiene un valor por defecto, mencionalo como opcion rapida al final de la pregunta.
Maximo 2 oraciones."""

    _SYSTEM_PARSE = """Eres un extractor de datos estructurado.
Tu tarea es analizar la respuesta del usuario y extraer el valor del campo solicitado.
Responde SOLO con un objeto JSON valido. Sin explicaciones, sin texto adicional.
Si no puedes extraer el valor (respuesta ambigua o invalida), usa {"valid": false, "error": "razon breve"}.
Si puedes extraer el valor, usa {"valid": true, "value": <valor_extraido>}.
El tipo del valor debe coincidir con el tipo esperado del campo."""

    _SYSTEM_FORMAT_RESULT = """Eres un asistente de empresa que presenta resultados de forma clara y profesional.
Recibes el resultado JSON de un workflow y debes presentarlo al usuario en espanol,
de manera organizada, usando formato markdown basico (negrita, listas).
Destaca los datos mas importantes. Se conciso pero completo. Maximo 400 palabras."""

    def start(self, project: dict, messages: list) -> str:
        """Inicia un proyecto nuevo: introspecciona el workflow y formula la primera pregunta.

        Pasos:
        1. Obtiene metadata del workflow desde el registro.
        2. Introspecciona la funcion para extraer todos los parametros.
        3. Guarda las preguntas en la BD (una por parametro requerido).
        4. Genera la primera pregunta en lenguaje natural y la retorna.

        Args:
            project: Dict del proyecto activo obtenido de project_db.get_active_project().
            messages: Historial de mensajes de la sesion (lista de dicts role/content).

        Returns:
            String con el mensaje de bienvenida + primera pregunta para mostrar al usuario.
        """
        project_id = project["project_id"]
        project_type = project["project_type"]

        wf_meta = workflow_registry.get_workflow(project_type)
        if not wf_meta:
            project_db.update_project_status(project_id, "error", f"Workflow '{project_type}' no registrado.")
            return "Lo siento, no puedo iniciar este tipo de proyecto. Por favor contacta al administrador."

        # --- Introspeccionar la funcion del workflow ---
        try:
            func_info = code_introspector.introspect_function(
                wf_meta["source_file"],
                wf_meta["function_name"],
            )
        except Exception as e:
            project_db.update_project_status(project_id, "error", str(e))
            return f"Error al inicializar el workflow: {e}"

        # --- Registrar preguntas en BD (solo parametros requeridos primero, luego opcionales) ---
        # Primero verificar si ya hay preguntas registradas (reanudar)
        existing_state = project_db.get_intake_state(project_id)
        if not existing_state:
            all_params = func_info["all_params"]
            for idx, param in enumerate(all_params):
                # Generar la pregunta para este campo
                question_text = self._generate_question(param)
                project_db.add_intake_question(
                    project_id=project_id,
                    field_name=param["name"],
                    question_asked=question_text,
                    order_index=idx,
                )

        # --- Obtener la primera pregunta sin responder ---
        next_q = project_db.get_unanswered_question(project_id)
        if not next_q:
            # Caso raro: ya estaba todo respondido
            return self._try_execute(project_id, project_type)

        display_name = wf_meta["display_name"]
        first_question = next_q["question_asked"]

        return (
            f"Perfecto, voy a ayudarte con la **{display_name}**.\n\n"
            f"Te hare algunas preguntas para recopilar la informacion necesaria. "
            f"Puedes escribir **'cancelar'** en cualquier momento para detener el proceso.\n\n"
            f"{first_question}"
        )

    def continue_conversation(self, project: dict, messages: list) -> str:
        """Procesa la respuesta del usuario y avanza en el flujo de intake.

        Pasos:
        1. Verifica si el mensaje es una cancelacion.
        2. Obtiene la pregunta actual sin responder.
        3. Parsea y valida la respuesta del usuario.
        4. Guarda la respuesta en la BD.
        5. Pregunta el siguiente campo o ejecuta el workflow si ya terminaron.

        Args:
            project: Dict del proyecto activo.
            messages: Historial de mensajes de la sesion.

        Returns:
            String con la siguiente pregunta, confirmacion de ejecucion, o mensaje de error.
        """
        project_id = project["project_id"]
        project_type = project["project_type"]

        # Extraer el ultimo mensaje del usuario
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_message = content if isinstance(content, str) else str(content)
                break

        # --- Verificar cancelacion ---
        if workflow_registry.is_cancel_message(project_type, user_message):
            project_db.update_project_status(project_id, "cancelled")
            return (
                "El proceso ha sido **cancelado**. "
                "Puedes iniciar uno nuevo cuando lo desees. "
                "En que mas puedo ayudarte?"
            )

        # --- Obtener pregunta actual ---
        current_q = project_db.get_unanswered_question(project_id)
        if not current_q:
            # No hay preguntas pendientes: intentar ejecutar
            return self._try_execute(project_id, project_type)

        field_name = current_q["field_name"]
        question_asked = current_q["question_asked"]

        # Obtener metadata del parametro para el parse
        wf_meta = workflow_registry.get_workflow(project_type)
        func_info = None
        if wf_meta:
            try:
                func_info = code_introspector.introspect_function(
                    wf_meta["source_file"],
                    wf_meta["function_name"],
                )
            except Exception:
                pass

        # Buscar la metadata del campo actual
        field_meta = {}
        if func_info:
            for param in func_info["all_params"]:
                if param["name"] == field_name:
                    field_meta = param
                    break

        # --- Parsear la respuesta del usuario ---
        parse_result = self._parse_answer(question_asked, user_message, field_meta)

        if not parse_result.get("valid", False):
            # Respuesta invalida: pedir de nuevo
            error_reason = parse_result.get("error", "respuesta no reconocida")
            return (
                f"No pude entender tu respuesta ({error_reason}). "
                f"Por favor, intentalo de nuevo:\n\n{question_asked}"
            )

        # --- Guardar respuesta ---
        parsed_value = parse_result.get("value")
        project_db.record_intake_answer(
            project_id=project_id,
            field_name=field_name,
            raw_answer=user_message,
            parsed_value=parsed_value,
        )

        # --- Verificar siguiente pregunta ---
        next_q = project_db.get_unanswered_question(project_id)
        if next_q:
            return next_q["question_asked"]

        # --- Todas las preguntas respondidas: ejecutar workflow ---
        return self._try_execute(project_id, project_type)

    def _generate_question(self, field: dict) -> str:
        """Genera una pregunta natural en espanol para recopilar el valor de un parametro.

        Usa Claude para transformar la metadata del parametro (nombre, tipo, descripcion,
        default) en una pregunta conversacional clara.

        Args:
            field: Diccionario con metadata del parametro:
                   {name, type, required, default, description}

        Returns:
            String con la pregunta formulada en espanol.
        """
        # Construir prompt con metadata del campo
        type_str = field.get("type") or "texto"
        required_str = "requerido" if field.get("required") else "opcional"
        default_str = ""
        if not field.get("required") and field.get("default") is not None:
            default_str = f"Valor por defecto: {field['default']}"

        prompt = (
            f"Necesito recopilar el valor del parametro:\n"
            f"- Nombre: {field['name']}\n"
            f"- Tipo de dato: {type_str}\n"
            f"- Es: {required_str}\n"
            f"- Descripcion: {field.get('description', 'Sin descripcion')}\n"
            f"{default_str}\n\n"
            f"Formula una pregunta clara y amigable en espanol para solicitar este dato al usuario."
        )

        try:
            response = _client.messages.create(
                model=_MODEL,
                max_tokens=200,
                system=self._SYSTEM_QUESTION,
                messages=[{"role": "user", "content": prompt}],
            )
            question = ""
            for block in response.content:
                if hasattr(block, "text"):
                    question += block.text
            return question.strip() or f"Por favor, ingresa el valor para '{field['name']}':"
        except Exception:
            # Fallback: pregunta generica basada en el nombre del campo
            nombre_legible = field["name"].replace("_", " ").capitalize()
            return f"Por favor, indica el **{nombre_legible}**:"

    def _parse_answer(self, question: str, raw_answer: str, field: dict) -> dict:
        """Valida y extrae el valor estructurado de una respuesta del usuario.

        Usa Claude para interpretar la respuesta en el contexto del campo esperado
        y retorna un dict con valid (bool) y value o error.

        Args:
            question: Pregunta que se le hizo al usuario.
            raw_answer: Texto literal de la respuesta del usuario.
            field: Metadata del parametro esperado.

        Returns:
            Dict: {"valid": True, "value": <valor>} o {"valid": False, "error": "razon"}.
        """
        type_str = field.get("type") or "str"
        field_name = field.get("name", "campo")
        description = field.get("description", "")

        # Manejo especial para campos opcionales con respuesta de aceptacion
        if not field.get("required") and raw_answer.lower().strip() in (
            "si", "sí", "ok", "de acuerdo", "bien", "vale", "yes", "default"
        ):
            default_val = field.get("default")
            if default_val is not None:
                return {"valid": True, "value": default_val}

        prompt = (
            f"Pregunta formulada al usuario: \"{question}\"\n"
            f"Respuesta del usuario: \"{raw_answer}\"\n\n"
            f"Campo a extraer:\n"
            f"- Nombre: {field_name}\n"
            f"- Tipo esperado: {type_str}\n"
            f"- Descripcion: {description}\n\n"
            f"Extrae el valor del campo de la respuesta del usuario."
        )

        try:
            response = _client.messages.create(
                model=_MODEL,
                max_tokens=512,
                system=self._SYSTEM_PARSE,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = ""
            for block in response.content:
                if hasattr(block, "text"):
                    raw_json += block.text

            raw_json = raw_json.strip()

            # Intentar parsear JSON de la respuesta
            parsed = json.loads(raw_json)
            return parsed

        except json.JSONDecodeError:
            # Si Claude no retorno JSON valido, aceptar el valor raw como string
            return {"valid": True, "value": raw_answer.strip()}
        except Exception:
            # Error de API u otro: aceptar el valor raw como fallback
            return {"valid": True, "value": raw_answer.strip()}

    def _try_execute(self, project_id: str, project_type: str) -> str:
        """Recopila los parametros, ejecuta el workflow y retorna el resultado formateado.

        Args:
            project_id: UUID del proyecto.
            project_type: Tipo de workflow a ejecutar.

        Returns:
            String con el resultado del workflow formateado para el usuario,
            o un mensaje de error descriptivo.
        """
        # Recopilar todos los campos respondidos
        params = project_db.get_answered_fields(project_id)

        # Actualizar estado a 'executing'
        project_db.update_project_status(project_id, "executing")

        # Guardar spec
        project_db.save_workflow_spec(project_id, params)

        # Ejecutar
        exec_result = workflow_executor.execute_workflow(project_type, params)

        if exec_result["status"] == "ok":
            project_db.update_project_status(project_id, "completed")
            project_db.save_workflow_result(project_id, exec_result["result"])
            return self._format_result(project_type, exec_result["result"])
        elif exec_result["status"] == "timeout":
            project_db.update_project_status(project_id, "error", exec_result["error"])
            return (
                "El proceso tardo demasiado tiempo y fue interrumpido. "
                "Por favor intentalo de nuevo o contacta al administrador."
            )
        else:
            error_msg = exec_result.get("error", "Error desconocido")
            project_db.update_project_status(project_id, "error", error_msg)
            return (
                f"Hubo un error al generar el documento:\n\n"
                f"_{error_msg}_\n\n"
                f"Por favor, verifica los datos ingresados e intentalo de nuevo."
            )

    def _format_result(self, project_type: str, result: dict) -> str:
        """Formatea el resultado del workflow en un mensaje amigable para el usuario.

        Para cotizaciones y informes, usa Claude para generar una presentacion
        estructurada en markdown. Si Claude falla, genera un resumen basico.

        Args:
            project_type: Tipo de workflow ejecutado.
            result: Diccionario con el resultado del workflow.

        Returns:
            String formateado con el resultado para mostrar en el chat.
        """
        wf_meta = workflow_registry.get_workflow(project_type)
        display_name = wf_meta["display_name"] if wf_meta else project_type

        result_json = json.dumps(result, ensure_ascii=False, indent=2, default=str)

        prompt = (
            f"El workflow '{display_name}' se ejecuto exitosamente. "
            f"Presenta los siguientes resultados al usuario de forma clara y profesional:\n\n"
            f"```json\n{result_json}\n```"
        )

        try:
            response = _client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=self._SYSTEM_FORMAT_RESULT,
                messages=[{"role": "user", "content": prompt}],
            )
            formatted = ""
            for block in response.content:
                if hasattr(block, "text"):
                    formatted += block.text

            if formatted.strip():
                return f"**{display_name} completada exitosamente**\n\n{formatted.strip()}"

        except Exception:
            pass

        # Fallback: formateo basico segun tipo de proyecto
        return self._format_result_fallback(project_type, result, display_name)

    def _format_result_fallback(self, project_type: str, result: dict, display_name: str) -> str:
        """Formateo de fallback sin LLM para los tipos de resultado conocidos."""
        lines = [f"**{display_name} generada exitosamente**\n"]

        if project_type == "cotizacion":
            lines.append(f"**Numero:** {result.get('numero_cotizacion', 'N/A')}")
            lines.append(f"**Cliente:** {result.get('cliente', {}).get('nombre', 'N/A')} - {result.get('cliente', {}).get('empresa', 'N/A')}")
            lines.append(f"**Moneda:** {result.get('moneda', 'USD')}")
            lines.append(f"\n**Resumen Financiero:**")
            lines.append(f"- Subtotal: {result.get('subtotal', 0):.2f}")
            if result.get("descuento_monto", 0) > 0:
                lines.append(f"- Descuento ({result.get('descuento_pct', 0)}%): -{result.get('descuento_monto', 0):.2f}")
            lines.append(f"- IVA ({result.get('iva_pct', 21)}%): {result.get('iva_monto', 0):.2f}")
            lines.append(f"- **Total: {result.get('total', 0):.2f} {result.get('moneda', 'USD')}**")
            if result.get("notas"):
                lines.append(f"\n**Notas:** {result['notas']}")
            lines.append(f"\n*Valida hasta: {result.get('fecha_vencimiento', 'N/A')}*")

        elif project_type == "informe_ventas":
            kpis = result.get("kpis", {})
            lines.append(f"**Periodo:** {result.get('periodo', 'N/A')} ({result.get('fecha_inicio', '')} al {result.get('fecha_fin', '')})")
            lines.append(f"**Departamento:** {result.get('departamento_filtro', 'todos')}")
            lines.append(f"\n**KPIs Principales:**")
            lines.append(f"- Total ventas: {kpis.get('total_ventas', 0):,.2f}")
            lines.append(f"- Transacciones: {kpis.get('num_transacciones', 0):,}")
            lines.append(f"- Ticket promedio: {kpis.get('ticket_promedio', 0):.2f}")
            lines.append(f"- Mejor vendedor: {kpis.get('mejor_vendedor', 'N/A')}")
            lines.append(f"- Categoria top: {kpis.get('categoria_top', 'N/A')}")

            ranking = result.get("ranking_vendedores", [])
            if ranking:
                lines.append(f"\n**Top Vendedores:**")
                for v in ranking[:5]:
                    lines.append(f"{v['posicion']}. {v['nombre']} - {v['total_vendido']:,.2f}")
        else:
            # Generico
            for key, value in result.items():
                lines.append(f"- **{key}:** {value}")

        return "\n".join(lines)
