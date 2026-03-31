# Instructivo - Chatbot Asistente para Aplicacion Web Local

## Que es esto?

Un chatbot embebible que se agrega a tu pagina web local existente. Aparece como un boton flotante en la esquina inferior derecha. El usuario puede hacer preguntas y el chatbot consulta los archivos CSV/JSON del sistema para dar respuestas.

---

## Estructura del proyecto

```
chatbot/
├── server.py              ← Servidor Flask (backend)
├── config.py              ← Configuracion (API key, rutas, modelo)
├── data_loader.py         ← Modulo para leer CSV y JSON
├── requirements.txt       ← Dependencias Python
├── iniciar_chatbot.bat    ← Script para iniciar en Windows
├── INSTRUCTIVO.md         ← Este archivo
├── datos/                 ← Carpeta de datos (CSV y JSON)
│   ├── empleados.csv      ← Ejemplo CSV
│   └── configuracion.json ← Ejemplo JSON
└── static/
    ├── chatbot-widget.css ← Estilos del widget
    ├── chatbot-widget.js  ← Logica del widget (frontend)
    └── demo.html          ← Pagina demo con el chatbot integrado
```

---

## Requisitos previos

1. **Python 3.9+** instalado en el servidor
2. **API Key de Anthropic** (obtener en https://console.anthropic.com)
3. Conexion a internet desde el servidor (para llamadas a la API de Claude)

---

## Instalacion paso a paso

### 1. Copiar archivos al servidor

Copiar toda la carpeta `chatbot/` al servidor donde corre la aplicacion web.

### 2. Configurar la API Key

Abrir `config.py` y reemplazar:

```python
ANTHROPIC_API_KEY = "TU_API_KEY_AQUI"
```

Con tu API key real. Alternativa: definir la variable de entorno `ANTHROPIC_API_KEY`.

### 3. Configurar la carpeta de datos

En `config.py`, cambiar `DATA_DIR` para que apunte a la carpeta donde estan tus archivos CSV y JSON:

```python
DATA_DIR = r"C:\ruta\a\tus\datos"
```

O usar la variable de entorno `CHATBOT_DATA_DIR`.

### 4. Instalar dependencias e iniciar

**Opcion A - Usar el .bat (Windows):**

Doble clic en `iniciar_chatbot.bat`. Crea el entorno virtual, instala dependencias e inicia el servidor automaticamente.

**Opcion B - Manual:**

```bash
cd chatbot
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python server.py
```

El servidor inicia en `http://127.0.0.1:5050`.

### 5. Verificar que funciona

Abrir `http://127.0.0.1:5050` en el navegador. Deberia verse la pagina demo con el boton del chatbot en la esquina inferior derecha.

---

## Integrar en tu pagina HTML existente

Agregar estas 3 lineas antes del cierre `</body>` de tu HTML:

```html
<!-- Chatbot Asistente -->
<script>
    window.CHATBOT_CONFIG = {
        apiUrl: "http://127.0.0.1:5050/api/chat",
        title: "Asistente",
        subtitle: "Preguntame lo que necesites",
        suggestions: [
            "Que archivos de datos hay?",
            "Dame un resumen general"
        ],
        // Opcional: capturar contexto de lo que el usuario ve
        getPageContext: function() {
            return document.title + " | " + document.body.innerText.substring(0, 500);
        }
    };
</script>
<link rel="stylesheet" href="http://127.0.0.1:5050/static/chatbot-widget.css">
<script src="http://127.0.0.1:5050/static/chatbot-widget.js"></script>
```

> **Nota:** Los archivos CSS y JS se sirven desde el servidor Flask. Solo necesitas agregar estas lineas a tu HTML existente, no copiar archivos.

---

## Configuracion avanzada

### Opciones de CHATBOT_CONFIG

| Opcion | Tipo | Descripcion |
|--------|------|-------------|
| `apiUrl` | string | URL del endpoint del chatbot |
| `title` | string | Titulo en el header del chat |
| `subtitle` | string | Subtitulo en el header |
| `placeholder` | string | Texto placeholder del input |
| `welcomeMessage` | string | Mensaje inicial del bot |
| `suggestions` | array | Botones de sugerencia iniciales |
| `getPageContext` | function | Funcion que devuelve contexto de la pagina actual |

### Personalizar el System Prompt

En `config.py`, editar `SYSTEM_PROMPT` para ajustar la personalidad y comportamiento del chatbot. Por ejemplo, agregar instrucciones especificas sobre tu aplicacion.

### Cambiar el modelo

En `config.py`, cambiar `MODEL`. Opciones:
- `claude-sonnet-4-20250514` - Rapido y economico (recomendado)
- `claude-opus-4-20250514` - Mas capaz pero mas costoso

### Agregar mas archivos de datos

Simplemente colocar archivos `.csv` o `.json` en la carpeta configurada en `DATA_DIR`. El chatbot los detecta automaticamente.

---

## Iniciar junto con la aplicacion existente

Si tu aplicacion ya se inicia con un `.bat`, agregar al final de ese archivo:

```bat
:: Iniciar chatbot en segundo plano
start "" /B cmd /c "cd /d C:\ruta\a\chatbot && venv\Scripts\python.exe server.py"
```

O crear un `.bat` maestro que inicie ambos:

```bat
@echo off
:: Iniciar aplicacion principal
start "" "C:\ruta\a\tu_aplicacion.bat"

:: Iniciar chatbot
start "" "C:\ruta\a\chatbot\iniciar_chatbot.bat"
```

---

## API del servidor

El servidor expone estos endpoints:

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| POST | `/api/chat` | Enviar mensaje y recibir respuesta |
| GET | `/api/archivos` | Listar archivos de datos disponibles |
| GET | `/api/resumen` | Resumen de todos los datos |

### Ejemplo de llamada a /api/chat

```json
POST /api/chat
{
    "messages": [
        {"role": "user", "content": "Que archivos hay disponibles?"}
    ],
    "page_context": "Pagina de empleados - mostrando tabla con 8 registros"
}
```

---

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| "No se pudo conectar con el servidor" | Verificar que `server.py` esta corriendo y el puerto 5050 esta libre |
| "API key invalida" | Revisar que la key en `config.py` es correcta |
| El chatbot no aparece | Verificar que las URLs del CSS y JS son accesibles desde el navegador |
| No encuentra archivos de datos | Verificar que `DATA_DIR` en `config.py` apunta a la carpeta correcta |
| Error de CORS | El servidor ya incluye Flask-CORS, verificar que la URL del `apiUrl` coincide |

---

## Costos estimados (API de Anthropic)

Cada mensaje del chatbot consume tokens de la API. Estimacion con Claude Sonnet:
- Conversacion tipica (10 mensajes): ~$0.01 - $0.03 USD
- Uso moderado de oficina (100 consultas/dia): ~$1 - $3 USD/dia

Los precios exactos dependen del volumen de datos consultados y la longitud de las respuestas.
