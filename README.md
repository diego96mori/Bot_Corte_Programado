# Bot de lecturas eléctricas

MVP gratuito para programar lecturas, enviar recordatorios por Telegram, recibir fotografías, reconocer números mediante OCR local y mostrar las lecturas confirmadas en una grilla web.

## Componentes gratuitos

- Python y Django: aplicación web y reglas del negocio.
- SQLite: base de datos inicial sin servidor ni licencia.
- Telegram Bot API: recepción de fotos y avisos.
- RapidOCR + ONNX Runtime: reconocimiento local; las fotos no se envían a servicios de IA.
- OpenPyXL: futura importación y exportación de Excel.

Telegram no cobra por crear y utilizar un bot. La computadora donde se ejecute el proyecto debe permanecer encendida para recibir fotos y enviar recordatorios.

## 1. Requisitos

Instalar Python 3.12 desde https://www.python.org/downloads/ y marcar **Add Python to PATH** durante la instalación.

## 2. Preparación en PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
```

## 3. Crear el bot

1. Abrir Telegram y buscar `@BotFather`.
2. Enviar `/newbot` y seguir las indicaciones.
3. Copiar el token recibido.
4. Pegar el token después de `TELEGRAM_BOT_TOKEN=` en `.env`.

Nunca compartir ni subir el archivo `.env`.

## 4. Cargar datos iniciales

```powershell
python manage.py runserver
```

Abrir http://127.0.0.1:8000/admin/ y crear, en este orden:

1. Un nodo con código, nombre y chat de Telegram.
2. Una programación de lectura pendiente para ese nodo.

Para conocer el identificador del chat, iniciar el bot y enviarle `/id`. Copiar el número que responde en el campo **chat de Telegram** del nodo.

### Importar el Excel operativo

El importador procesa exclusivamente la hoja `LECTURAS 2026` y los 33 nodos autorizados en `readings/authorized_nodes.py`. Ignora los demás nodos, la leyenda de colores y los valores no numéricos como `PENDIENTE`.

```powershell
python manage.py import_readings_excel "RUTA\LECTURAS WIN 2026.xlsx" --telegram-chat-id NUMERO_DE_CHAT
```

Puede ejecutarse nuevamente sobre el mismo archivo sin duplicar las lecturas ya importadas.

## Usuarios y permisos

El sistema utiliza solamente dos tipos de acceso:

1. **Administrador/operador:** es un superusuario de Django. Puede configurar nodos, usuarios y respaldos; revisar, corregir, editar, reportar y reprogramar lecturas; además puede enviar y confirmar fotografías desde Telegram.
2. **Consulta:** es un usuario normal, sin las opciones `Staff` ni `Superuser`. Solo puede iniciar sesión y ver la grilla; no ve ni puede abrir la administración.

El administrador se crea con `createsuperuser`. Para crear un usuario de consulta, entrar en **Administración > Usuarios > Añadir usuario**, asignar su contraseña y dejar desmarcados `Staff status` y `Superuser status`.

El bot solo acepta fotografías desde el chat de Telegram guardado en el nodo. Para un único operador se recomienda usar su chat privado, no un grupo compartido.

## 5. Ejecutar

Usar dos ventanas de PowerShell con el entorno virtual activado:

```powershell
python manage.py runserver
```

```powershell
python manage.py run_telegram_bot
```

En Telegram, enviar `/start`. El bot muestra dos opciones: **Ingresar lectura** y **Consultar lectura**. Para ingresar, se puede escribir el nombre del nodo (tolera errores de escritura) o abrir la lista de los 33 nodos. Después solicita la foto, detecta el valor y pide confirmarlo o corregirlo. Antes de guardar solicita la fecha: se puede elegir **Hoy** o escribirla como `DÍA/MES/AÑO`. La consulta permite ver el mes actual o las últimas lecturas.

La grilla se encuentra en http://127.0.0.1:8000/ y exige iniciar sesión.

La barra lateral izquierda permite cambiar entre:

- **Gestión de lecturas:** todos los registros, estados y evidencias.
- **LECTURAS WI-NET:** vista mensual basada en el Excel, limitada a los nodos autorizados.

## 6. Recordatorios

El proceso `run_telegram_bot` revisa y envía automáticamente los avisos cada cinco horas. También se puede ejecutar una revisión manual con:

```powershell
python manage.py send_reminders
```

Cada aviso corresponde a un nodo e incluye el botón **Registrar lectura**, que inicia directamente el flujo de fotografía para ese nodo.

Mientras un chat está seleccionando el nodo, enviando la foto, confirmando o corrigiendo el valor, o indicando la fecha, sus recordatorios quedan pausados para no interrumpir el proceso. Al finalizar se reanudan; una conversación abandonada pierde la pausa automáticamente después de una hora.

La campana de la esquina superior derecha y Telegram comparten estas reglas:

- Si todavía no existe una lectura del mes, avisan desde tres días antes del día de lectura configurado para el nodo.
- Después de registrar una lectura, la siguiente vence diez días después y se avisa un día antes.
- Si no se registra a tiempo, el aviso permanece como atrasado en la web y Telegram continúa enviándolo cada cinco horas mientras el bot esté funcionando.
- Al confirmar una nueva lectura se completan las programaciones pendientes que esa lectura satisface.

## Siguiente etapa

- Importar los nodos y el histórico desde el Excel actual.
- Exportar la grilla filtrada a `.xlsx`.
- Añadir auditoría detallada, copias de seguridad y PostgreSQL.
- Automatizar el bot, la web y los recordatorios con Docker Compose.
