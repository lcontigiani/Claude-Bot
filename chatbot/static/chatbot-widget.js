/**
 * CHATBOT WIDGET
 * Widget de chatbot embebible en cualquier pagina HTML.
 * Comunicacion con el backend Flask via API REST.
 *
 * USO: Incluir este archivo + chatbot-widget.css en tu HTML.
 *      Opcionalmente configurar CHATBOT_CONFIG antes de cargar este script.
 */

(function () {
    "use strict";

    // --- Configuracion ---
    const CONFIG = Object.assign(
        {
            apiUrl: "http://127.0.0.1:5050/api/chat",
            title: "Asistente",
            subtitle: "Siempre disponible para ayudarte",
            placeholder: "Escribe tu mensaje...",
            welcomeMessage:
                "Hola! Soy tu asistente. Puedo ayudarte a entender lo que ves en pantalla, buscar informacion en las bases de datos y responder tus preguntas. Como puedo ayudarte?",
            suggestions: [
                "Que archivos de datos hay?",
                "Dame un resumen de los datos",
                "Que estoy viendo en pantalla?",
            ],
            // Funcion para capturar contexto de la pagina actual
            getPageContext: function () {
                return document.title + " | " + window.location.pathname;
            },
        },
        window.CHATBOT_CONFIG || {}
    );

    // --- Estado ---
    let messages = [];
    let isOpen = false;
    let isLoading = false;

    // --- Crear DOM ---
    function createWidget() {
        // Boton flotante
        const toggle = document.createElement("button");
        toggle.id = "chatbot-toggle";
        toggle.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>`;
        toggle.addEventListener("click", toggleChat);

        // Ventana
        const win = document.createElement("div");
        win.id = "chatbot-window";
        win.innerHTML = `
            <div id="chatbot-header">
                <div class="chat-avatar">🤖</div>
                <div class="chat-info">
                    <div class="chat-title">${CONFIG.title}</div>
                    <div class="chat-subtitle">${CONFIG.subtitle}</div>
                </div>
                <button class="chat-close" id="chatbot-close">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div id="chatbot-messages"></div>
            <div id="chatbot-suggestions"></div>
            <div id="chatbot-input-area">
                <textarea id="chatbot-input" rows="1" placeholder="${CONFIG.placeholder}"></textarea>
                <button id="chatbot-send">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                </button>
            </div>
        `;

        document.body.appendChild(toggle);
        document.body.appendChild(win);

        // Event listeners
        document.getElementById("chatbot-close").addEventListener("click", toggleChat);
        document.getElementById("chatbot-send").addEventListener("click", sendMessage);
        document.getElementById("chatbot-input").addEventListener("keydown", function (e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Auto-resize textarea
        const input = document.getElementById("chatbot-input");
        input.addEventListener("input", function () {
            this.style.height = "auto";
            this.style.height = Math.min(this.scrollHeight, 100) + "px";
        });

        // Renderizar sugerencias
        renderSuggestions();

        // Mensaje de bienvenida
        addMessage("bot", CONFIG.welcomeMessage);
    }

    function toggleChat() {
        isOpen = !isOpen;
        const win = document.getElementById("chatbot-window");
        const btn = document.getElementById("chatbot-toggle");

        if (isOpen) {
            win.classList.add("visible");
            btn.classList.add("open");
            document.getElementById("chatbot-input").focus();
        } else {
            win.classList.remove("visible");
            btn.classList.remove("open");
        }
    }

    function renderSuggestions() {
        const container = document.getElementById("chatbot-suggestions");
        container.innerHTML = "";
        CONFIG.suggestions.forEach(function (text) {
            const btn = document.createElement("button");
            btn.className = "chat-suggestion";
            btn.textContent = text;
            btn.addEventListener("click", function () {
                document.getElementById("chatbot-input").value = text;
                sendMessage();
            });
            container.appendChild(btn);
        });
    }

    function addMessage(role, text) {
        const container = document.getElementById("chatbot-messages");
        const div = document.createElement("div");
        div.className = "chat-message " + (role === "user" ? "user" : "bot");

        if (role === "bot") {
            div.innerHTML = formatMarkdown(text);
        } else {
            div.textContent = text;
        }

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function showTyping() {
        const container = document.getElementById("chatbot-messages");
        const div = document.createElement("div");
        div.className = "chat-typing";
        div.id = "chatbot-typing";
        div.innerHTML = "<span></span><span></span><span></span>";
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function hideTyping() {
        const el = document.getElementById("chatbot-typing");
        if (el) el.remove();
    }

    function formatMarkdown(text) {
        // Formato basico de markdown
        let html = text
            // Code blocks
            .replace(/```(\w*)\n?([\s\S]*?)```/g, "<pre><code>$2</code></pre>")
            // Inline code
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            // Bold
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            // Italic
            .replace(/\*(.+?)\*/g, "<em>$1</em>")
            // Lists
            .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
            // Numbered lists
            .replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

        // Wrap consecutive <li> in <ul>
        html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, "<ul>$1</ul>");

        // Paragraphs
        html = html
            .split("\n\n")
            .map(function (p) {
                p = p.trim();
                if (!p) return "";
                if (
                    p.startsWith("<pre>") ||
                    p.startsWith("<ul>") ||
                    p.startsWith("<ol>")
                )
                    return p;
                return "<p>" + p + "</p>";
            })
            .join("");

        return html || text;
    }

    async function sendMessage() {
        if (isLoading) return;

        const input = document.getElementById("chatbot-input");
        const text = input.value.trim();
        if (!text) return;

        // Limpiar input
        input.value = "";
        input.style.height = "auto";

        // Ocultar sugerencias despues del primer mensaje
        document.getElementById("chatbot-suggestions").style.display = "none";

        // Mostrar mensaje del usuario
        addMessage("user", text);

        // Agregar al historial
        messages.push({ role: "user", content: text });

        // Mostrar indicador de carga
        isLoading = true;
        document.getElementById("chatbot-send").disabled = true;
        showTyping();

        try {
            const pageContext =
                typeof CONFIG.getPageContext === "function"
                    ? CONFIG.getPageContext()
                    : "";

            const response = await fetch(CONFIG.apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    messages: messages,
                    page_context: pageContext,
                }),
            });

            const data = await response.json();

            hideTyping();

            if (data.response) {
                addMessage("bot", data.response);
                messages.push({ role: "assistant", content: data.response });
            } else {
                addMessage("bot", "Lo siento, hubo un error al procesar tu mensaje.");
            }
        } catch (error) {
            hideTyping();
            addMessage(
                "bot",
                "No se pudo conectar con el servidor. Verifica que el servicio este activo en " +
                    CONFIG.apiUrl
            );
            console.error("Chatbot error:", error);
        }

        isLoading = false;
        document.getElementById("chatbot-send").disabled = false;
    }

    // --- Inicializar cuando el DOM este listo ---
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", createWidget);
    } else {
        createWidget();
    }
})();
