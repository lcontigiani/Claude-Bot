# Guia: Acceso Remoto al Servidor de Oficina con Cloudflare Tunnel

## Por que Cloudflare Tunnel?

Cloudflare Tunnel permite acceder a la aplicacion web y al chatbot del servidor de oficina
desde cualquier lugar (casa, viaje, etc.) sin necesidad de VPN ni abrir puertos en el router.

- El servidor nunca expone puertos a internet
- Todo el trafico va encriptado por HTTPS
- Proteccion contra ataques incluida
- Se instala una sola vez y corre automaticamente con Windows
- Plan gratuito suficiente para uso de oficina

```
Desde cualquier lugar
        |
        v
https://app.tudominio.com
        |
[Login con email - Cloudflare Access]
        |
        v
Servidor de oficina (tu app + chatbot)
```

---

## Requisitos previos

- [ ] Acceso al servidor Windows con permisos de Administrador
- [ ] Cuenta de Cloudflare gratuita (crear en cloudflare.com)
- [ ] Opcional: dominio propio (desde ~$10/año en Cloudflare Domains)
        Si no tenes dominio, Cloudflare da uno gratuito .trycloudflare.com para pruebas

---

## PASO 1 — Crear cuenta y acceder a Zero Trust

1. Ir a https://cloudflare.com y crear una cuenta gratuita (o iniciar sesion)
2. Desde el panel principal, ir a **Zero Trust**:
   https://one.dash.cloudflare.com
3. Si pide elegir un plan → elegir **Free**

---

## PASO 2 — Crear el Tunnel

1. En el panel Zero Trust ir a **Networks → Tunnels**
2. Click en **Create a tunnel**
3. Elegir **Cloudflared** como conector
4. Ponerle un nombre descriptivo, por ejemplo: `oficina-servidor`
5. Click **Save tunnel**
6. En la siguiente pantalla, seleccionar **Windows** como sistema operativo
7. Copiar el token que aparece (se usa en el Paso 3)

---

## PASO 3 — Instalar cloudflared en el servidor Windows

Abrir **PowerShell como Administrador** en el servidor y ejecutar:

```powershell
# 1. Descargar el instalador
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi -o cloudflared.msi

# 2. Instalar
msiexec /i cloudflared.msi
```

Esperar que termine la instalacion, luego ejecutar el comando con el token
que copiaste del panel de Cloudflare (reemplazar TU_TOKEN_AQUI):

```powershell
cloudflared.exe tunnel --no-autoupdate run --token TU_TOKEN_AQUI
```

Si en el panel de Cloudflare el tunnel aparece como **"Connected"** (en verde),
la conexion esta funcionando correctamente.

---

## PASO 4 — Instalar como servicio de Windows

Para que el tunnel arranque automaticamente cada vez que el servidor enciende,
sin que nadie tenga que hacerlo manualmente:

```powershell
cloudflared.exe service install --token TU_TOKEN_AQUI
```

Verificar que el servicio quedo activo:

```powershell
sc query cloudflared
```

Debe aparecer el estado como **RUNNING**.

Para controlar el servicio manualmente si fuera necesario:

```powershell
# Detener
net stop cloudflared

# Iniciar
net start cloudflared
```

---

## PASO 5 — Configurar las URLs publicas

De vuelta en el panel de Cloudflare:
**Networks → Tunnels → (tu tunnel) → Configure → Public Hostname**

Click en **Add a public hostname** y agregar una entrada por cada servicio:

### Entrada 1 — Aplicacion web principal

| Campo     | Valor                        |
|-----------|------------------------------|
| Subdomain | app                          |
| Domain    | tudominio.com                |
| Type      | HTTP                         |
| URL       | localhost:PUERTO_DE_TU_APP   |

### Entrada 2 — Chatbot Flask

| Campo     | Valor                |
|-----------|----------------------|
| Subdomain | chatbot              |
| Domain    | tudominio.com        |
| Type      | HTTP                 |
| URL       | localhost:5050       |

Resultado:
- https://app.tudominio.com      → tu aplicacion web de oficina
- https://chatbot.tudominio.com  → el chatbot con IA

> Nota: si no tenes dominio propio, en el campo Domain podes usar el subdominio
> gratuito que asigna Cloudflare (termina en .trycloudflare.com)

---

## PASO 6 — Proteger el acceso con login (muy recomendado)

Sin este paso, cualquiera que tenga la URL puede entrar.
Cloudflare Access agrega una pantalla de autenticacion antes de mostrar la app.

1. En Zero Trust ir a **Access → Applications**
2. Click **Add an application**
3. Elegir **Self-hosted**
4. Completar:
   - **Application name:** Oficina
   - **Session duration:** 24 hours (o lo que prefieras)
   - **Application domain:** `*.tudominio.com` (el asterisco protege todos los subdominios)
5. Click **Next**
6. En **Policies**, crear una regla:
   - **Policy name:** Solo equipo
   - **Action:** Allow
   - **Configure rules → Include:**
     - Selector: **Emails**
     - Value: agregar los emails de cada persona autorizada
       (ej: lorenzo@gmail.com, colega@gmail.com)
7. Click **Next** → **Add application**

Desde ahora, al entrar a cualquier URL de tu dominio:
- Cloudflare pide el email
- Manda un codigo de verificacion al email
- Solo si el email esta en la lista autorizada, deja pasar

---

## PASO 7 — Actualizar el chatbot para funcionar remotamente

Cuando el chatbot corre de forma remota (no solo en localhost), hay que
ajustar la configuracion para que acepte conexiones desde cualquier origen.

En el servidor, abrir `chatbot/config.py` y cambiar:

```python
# Antes
HOST = "127.0.0.1"

# Despues
HOST = "0.0.0.0"
```

Luego reiniciar el servidor del chatbot:

```powershell
# Detener el proceso anterior y volver a iniciar
iniciar_chatbot.bat
```

Y en tu pagina HTML, actualizar la URL del chatbot:

```javascript
window.CHATBOT_CONFIG = {
    apiUrl: "https://chatbot.tudominio.com/api/chat",
    // ... resto de la configuracion
};
```

---

## Resumen del resultado final

```
SERVIDOR DE OFICINA (Windows)
├── Tu aplicacion web  (puerto XXXX)  ←── https://app.tudominio.com
├── Chatbot Flask      (puerto 5050)  ←── https://chatbot.tudominio.com
└── cloudflared        (servicio)     ←── mantiene el tunnel activo 24/7

ACCESO DESDE CUALQUIER LUGAR
├── Abrir https://app.tudominio.com
├── Cloudflare pide verificacion de email
├── Si el email esta autorizado → acceso completo
└── La sesion dura 24 horas antes de pedir login de nuevo
```

---

## Solucion de problemas

| Problema | Solucion |
|----------|----------|
| Tunnel aparece como "Inactive" en Cloudflare | Ejecutar `net start cloudflared` en el servidor |
| La URL no carga | Verificar que la app esta corriendo en el puerto correcto |
| "Too many redirects" | En Public Hostname, cambiar Type de HTTPS a HTTP |
| El chatbot no responde desde remoto | Verificar que HOST es "0.0.0.0" en config.py |
| Acceso denegado en Cloudflare Access | Verificar que el email esta en la lista de la politica |

---

## Recursos utiles

- Panel Zero Trust: https://one.dash.cloudflare.com
- Documentacion cloudflared Windows: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
- Cloudflare Access: https://developers.cloudflare.com/cloudflare-one/policies/access/
