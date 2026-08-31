# Bot de lecturas eléctricas

MVP gratuito para programar lecturas, enviar recordatorios por Telegram, recibir fotografías, reconocer números mediante OCR local y mostrar las lecturas confirmadas en una grilla web.

## Componentes gratuitos

- Python y Django: aplicación web y reglas del negocio.
- SQLite: base de datos inicial sin servidor ni licencia.
- Telegram Bot API: recepción de fotos y avisos.
- RapidOCR + ONNX Runtime: reconocimiento local principal.
- Cloudflare Workers AI: respaldo opcional; recibe el recorte del visor cuando el OCR local no logra un resultado confiable. Solo si no fue posible localizar el visor, recibe la foto para ubicarlo visualmente.
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

### Respaldo opcional con Cloudflare

El reconocimiento funciona localmente aunque Cloudflare no esté configurado. Para habilitar el respaldo automático, crear un token de Workers AI y completar en `.env`:

```text
CLOUDFLARE_ACCOUNT_ID=identificador-de-la-cuenta
CLOUDFLARE_API_TOKEN=token-secreto
CLOUDFLARE_VISION_MODEL=@cf/moondream/moondream3.1-9B-A2B
```

Moondream 3.1 está especializado en visión y OCR. El token nunca debe guardarse en Git ni enviarse por Telegram.

## 4. Cargar datos iniciales

```powershell
python manage.py runserver
```

Abrir http://127.0.0.1:8000/admin/ y crear, en este orden:

1. Un nodo con código, nombre, día de lectura (1 a 31) y chat de Telegram. Si falta el día, el bot solicita configurarlo antes de permitir un registro.
2. Una programación de lectura pendiente para ese nodo.

Para conocer el identificador del chat, iniciar el bot y enviarle `/id`. Copiar el número que responde en el campo **chat de Telegram** del nodo.

### Importar el Excel operativo

El importador procesa exclusivamente la hoja `LECTURAS 2026` y los 33 nodos autorizados en `readings/authorized_nodes.py`. Ignora los demás nodos, la leyenda de colores y los valores no numéricos como `PENDIENTE`.

```powershell
python manage.py import_readings_excel "RUTA\LECTURAS WIN 2026.xlsx" --telegram-chat-id NUMERO_DE_CHAT
```

Puede ejecutarse nuevamente sobre el mismo archivo sin duplicar las lecturas ya importadas.

### Punto de partida: agosto de 2026

Por decisión operativa, los registros confirmados existentes de agosto se toman como base: la primera fecha de cada nodo es su lectura mensual y, si hay una segunda, es su seguimiento. No se reclasifican esos registros a partir del manejo manual de julio. Se conservan fechas reales, valores, fotos, origen y responsables; las fechas programadas se alinean con el día mensual configurado y con los diez días desde la primera lectura.

Esta excepción se limita a agosto de 2026. Pelitres toma el 05/08 como mensual y el 19/08 como seguimiento completado: no corresponde ningún recordatorio hasta el 21/09, inicio de su ventana del día 23. Santa Fe toma el 03/08 como mensual y el 25/08 como seguimiento completado: vuelve a avisar el 15/09 para su lectura del día 17. Desde septiembre se aplica el ciclo normal; no se clasifica automáticamente cualquier primera fecha del mes como lectura mensual por esta excepción.

Los nodos que todavía no tienen una lectura de agosto, como Las Palmeras al preparar esta base, permanecen pendientes: no se inventa un registro ni se reutiliza una lectura de julio. Cuando se registre su lectura mensual, se conserva la fecha real indicada y el seguimiento se calcula diez días después, sujeto al cierre por la siguiente ventana mensual.

Para revisar esa base sin modificar datos, ejecutar `python manage.py normalize_august_baseline`. Para aplicarla, detener primero el bot y ejecutar `python manage.py normalize_august_baseline --apply`; genera un respaldo SQLite y un informe en `backups/`. Omite nodos inactivos y rechaza casos con más de dos lecturas o destinos con otros registros. Esta es una conciliación histórica específica, no una regla para reiniciar la clasificación en cada mes.

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

En Telegram, enviar `/start`. El bot muestra dos opciones: **Ingresar lectura** y **Consultar lectura**. Para ingresar, se puede escribir el nombre del nodo (tolera errores de escritura) o abrir la lista de nodos autorizados. Después solicita la foto, detecta el valor y pide confirmarlo o corregirlo. Antes de guardar solicita elegir **Hoy** o **Escribir fecha**; esta última opción acepta una fecha real con formato `DD/MM/AAAA`, por ejemplo `31/08/2026`. La consulta permite ver el mes actual o las últimas lecturas.

Para ingresar sin fotografía es obligatorio pulsar **Escribir lectura manualmente** antes de enviar el número. Si no se reconoce la foto, hay que elegir **Ingresar lectura manual** o **Cancelar registro**. El valor admite enteros o decimales con punto o coma, hasta 12 dígitos enteros y 3 decimales, sin signos, letras ni unidades. Cada paso repite su pregunta y sus botones cuando recibe texto, fotos, audios u otros mensajes que no corresponden. Los botones de preguntas anteriores no permiten saltar pasos ni confirmar otro registro. Tras registrar o cancelar, vuelve al menú inicial.

La programación definitiva se asigna al confirmar la fecha real de la lectura, incluso si corresponde a un ciclo anterior; no se completan otras programaciones solo por ser más antiguas.

Antes de pedir la fotografía o el valor, el bot revisa las lecturas confirmadas del ciclo activo y explica si corresponde una **lectura mensual** o un **seguimiento**, con sus fechas. Si ya existen ambos registros, bloquea otro ingreso e indica cuándo se abre el siguiente ciclo. Por ejemplo, Huacho, con día mensual 3 y su ciclo de agosto completo, no admite otra lectura el 31/08: vuelve a permitirla desde el 01/09. Guardia Peruana, con día mensual 2, ya admite la lectura mensual de septiembre desde el 31/08; el seguimiento pendiente de agosto deja de ser la obligación activa.

La validación se repite al crear el borrador y al confirmar, para impedir un tercer registro incluso si otro operador completó el ciclo durante la conversación. No se aceptan fechas futuras ni fechas antiguas que oculten registros ya confirmados para reabrir un ciclo completo. Un seguimiento no puede tener fecha anterior a la lectura mensual existente. Los registros históricos se conservan y la consulta continúa disponible aunque el ingreso esté bloqueado.

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

Mientras un chat está seleccionando el nodo, consultando, enviando la foto, confirmando o corrigiendo el valor, o indicando la fecha, sus recordatorios quedan pausados para no interrumpir el proceso. Después de **8 minutos sin mensajes ni pulsaciones**, el bot cancela el borrador sin confirmar y muestra automáticamente el menú inicial. Si sigue sin respuesta, vuelve a mostrarlo cada 8 minutos mientras el proceso del bot esté encendido. Cada nueva interacción renueva el plazo; el tiempo de procesamiento del OCR no cuenta como inactividad. Al finalizar o volver al menú se reanudan los recordatorios.

La campana de la esquina superior derecha y Telegram comparten estas reglas:

- La ventana mensual comprende tres días contando el día de lectura: para el día 11 comienza el día 9.
- La ventana puede comenzar en el mes o año anterior: para el 2 de septiembre empieza el 31 de agosto. Desde ese día, la grilla muestra la lectura próxima (por ejemplo, **Lectura: faltan 2 días**) y los avisos corresponden al nuevo ciclo.
- La grilla calcula las próximas obligaciones aunque el bot no esté ejecutándose o el nodo no tenga chat. No crea lecturas ficticias ni duplica programaciones ya guardadas. Los ciclos anteriores permanecen como historial en gris, con la indicación **ciclo cerrado**.
- Después de registrar la lectura mensual, su único seguimiento vence diez días después de la fecha real de lectura y se avisa un día antes.
- Al comenzar la nueva ventana mensual, el seguimiento anterior deja de ser la obligación activa. Para una lectura mensual del 11 de agosto registrada el 31, el seguimiento vence el 10 de septiembre, pero solo puede registrarse como seguimiento hasta el 8; desde el 9 corresponde a la lectura mensual de septiembre.
- Una lectura mensual atrasada continúa generando avisos aunque cambie el mes, hasta el inicio de la siguiente ventana mensual. Telegram conserva el intervalo de cinco horas mientras el bot esté funcionando.
- Al confirmar una lectura se completa únicamente la programación correspondiente a su fecha y ciclo.
- Cada envío exitoso se registra antes de intentar el siguiente. Si Telegram rechaza un destinatario, se registra el error y se continúa con los demás.

## Siguiente etapa

- Importar los nodos y el histórico desde el Excel actual.
- Exportar la grilla filtrada a `.xlsx`.
- Añadir auditoría detallada, copias de seguridad y PostgreSQL.
- Automatizar el bot, la web y los recordatorios con Docker Compose.
