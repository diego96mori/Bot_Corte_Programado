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
CLOUDFLARE_VISION_MODEL=@cf/google/gemma-4-26b-a4b-it
```

Gemma 4 recibe la fotografía como entrada visual y devuelve la lectura en JSON. El token nunca debe guardarse en Git ni enviarse por Telegram. El resultado de la IA siempre debe confirmarse en el bot antes de guardar la lectura.

### OCR gratuito y aprendizaje por medidor

Para visores con un formato fijo se puede configurar `OCR_DISPLAY_FORMATS` en `.env`
como un objeto JSON indexado por código de nodo, número de medidor o alcance interno.
Por ejemplo, `{"SUM-123456":"6+1"}` conserva seis enteros, un decimal y los ceros
iniciales únicamente para ese medidor; los demás continúan con detección automática.

El reconocimiento local no utiliza una API de pago. El respaldo externo solo permite
`@cf/google/gemma-4-26b-a4b-it` y exige `CLOUDFLARE_FREE_PLAN_CONFIRMED=True`.
Activar esta opción únicamente con Workers **Free**, que bloquea solicitudes al agotar
la cuota gratuita. Workers Paid puede facturar excedentes: si se cambia de plan,
desactivar esta opción. El programa no contrata planes, compra créditos ni cambia de
modelo automáticamente. Ante errores de cuota o servicio, solicita ingreso manual.
La configuración de una instalación nueva deja Cloudflare desactivado hasta confirmar
el plan. Referencia: https://developers.cloudflare.com/workers-ai/platform/pricing/.

El bot conserva la foto original, cada intento de OCR, sus candidatos, versión del
algoritmo, modelo externo, confianza y valor propuesto. Al confirmar o corregir la
lectura, el valor confirmado se convierte en la etiqueta de esa imagen. Un ingreso
manual **sin foto** no sirve como ejemplo visual. No se modifica el valor propuesto
para hacerlo coincidir con la corrección.

En las siguientes fotografías del mismo nodo y medidor, el OCR consulta hasta 100
lecturas confirmadas con etiqueta visual verificada. Cuenta un voto por fotografía distinta y técnica. Después de
tres ejemplos de una técnica, si acertó menos de la mitad se excluyen sus candidatos;
las técnicas con resultados fiables reciben una preferencia pequeña, manteniendo el
consenso entre variantes. Las lecturas canceladas y sin confirmar no enseñan al sistema.
Se aprende qué preprocesamientos resultan fiables; **no se reentrena Gemma ni se copia
la lectura del mes anterior**, ni se garantiza una mejora con cada fotografía.

En Administración > Nodos, mantener el número de medidor actualizado. Al reemplazar
el equipo, cambiar ese número o incrementar «versión de aprendizaje del medidor»:
los ejemplos de la versión anterior dejan de influir. Cada nodo tiene su propia
memoria; no se mezclan automáticamente equipos de otros nodos. En Administración >
Lecturas se puede consultar el historial de reconocimiento, que es de solo lectura.
Corregir una etiqueta confirmada también corrige el aprendizaje en la siguiente consulta.
Por decisión operativa, las fotos anteriores al inicio de esta etapa quedan excluidas
del aprendizaje mediante una marca independiente, de solo lectura en Administración.
Aunque se marquen como verificadas, no alimentan la memoria local. Se conservan como
evidencia operativa. Las confirmaciones nuevas del bot con foto activan la marca de verificación;
si se confirma un valor incorrecto se debe corregir o desmarcar. Se puede filtrar
la lista por esa marca para revisar los ejemplos pendientes.

Los decimales se comparan como parte del valor exacto. Una discrepancia decimal exige
revisión. El modelo no recibe el consumo anterior en el mensaje; el histórico se valida
después. Una lectura igual a la anterior se permite; una inferior requiere revisión manual.
Un resultado local solo evita la nube si alcanza confianza 0.85 y una técnica que lo
produjo acertó al menos el 90 % de tres o más fotos distintas del mismo medidor.
Sin esa experiencia, el resultado local es orientativo y Gemma realiza la lectura.
Si un resultado local calibrado de menor confianza discrepa de la nube, se solicita
ingreso manual. Un recorte ilegible puede reintentarse una vez
con la foto completa, pero los errores de cuota o servicio no generan ese reintento.

Para evaluar sin red las fotografías confirmadas:

```powershell
python manage.py evaluate_ocr
python manage.py evaluate_ocr --export backups/ejemplos_ocr.jsonl
python manage.py evaluate_ocr --learn
```

El informe distingue aciertos exactos, errores, rechazos e imágenes ausentes. Excluye
del aprendizaje la etiqueta de la foto evaluada y las confirmaciones posteriores.
El archivo de exportación no se sobrescribe, contiene rutas relativas a `media/`,
etiquetas y candidatos, y no duplica fotografías. Sirve como conjunto de ejemplos para
un futuro entrenamiento especializado; para validar ese entrenamiento se deben separar
fotos por sesión/fecha, manteniendo duplicados fuera de ambos grupos.
La evaluación sin Cloudflare informa los candidatos locales, incluso los todavía no
calibrados; no representa la precisión del flujo completo ni prueba una mejora futura.
`--learn` registra los candidatos de fotos antiguas sin cambiar su valor confirmado,
marcándolos como reproducción histórica. Solo debe usarse si las fotos corresponden
al equipo actual de cada nodo. Las etiquetas deben revisarse antes de entrenar:
un valor manual incorrecto también puede enseñar un error.
Registrar candidatos históricos no verifica sus etiquetas ni elimina su exclusión.
Los ejemplos excluidos o no verificados no influyen en el OCR; los números de la evaluación son
coincidencias con datos guardados, no una medida de precisión visual certificada.

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

Los grupos se configuran con casillas por función: ver Gestión, ver Lecturas WI-NET, ver calendario/campana, registrar por web y administrar. Los controles también se verifican en el servidor, no solamente ocultando botones.

1. **Operadores:** acceso a ambas pantallas, calendario/campana, registro web y Administración. La cuenta `administrador` pertenece a este grupo y conserva sus privilegios de superusuario.
2. **Consulta:** solo Lecturas WI-NET y calendario/campana. Sin Gestión, Administración ni registro web. La cuenta `Consulta` está activa en este grupo. Al abrir la raíz se redirige a la grilla anual.

En **Administración > Usuarios** se selecciona el grupo; el acceso administrativo se ajusta automáticamente al guardar. No es necesario conceder superusuario a un operador nuevo. Un superusuario existente conserva todos sus permisos independientemente del grupo.

Administración utiliza botones por fila en lugar de acciones masivas. Lecturas no admite altas: solo valor confirmado/foto y eliminación con confirmación. Una corrección revoca la verificación OCR hasta una nueva revisión; sustituir la foto limpia sus intentos anteriores. Al eliminar una lectura se recalcula el estado de su programación, conservando anulaciones explícitas; un ciclo vencido sigue mostrándose cerrado. No se borran automáticamente las fotos del disco ni otras lecturas vinculadas al nodo.

Nodos permite editar nombre, ubicación, suministro, concesionaria, día mensual y activo. El código se genera como `SUM-<suministro>` y el chat de los nodos nuevos es `8463146362`. No permite eliminar nodos: se desactivan. Programaciones permite cambiar solo estado, sin marcar completada una obligación sin lectura ni cambiar de completada una que todavía conserva una confirmación. Recordatorios enviados es exclusivamente de consulta.

El bot solo acepta fotografías desde el chat de Telegram guardado en el nodo. Para un único operador se recomienda usar su chat privado, no un grupo compartido.

## 5. Ejecutar

### Registro manual desde la web

El administrador/operador puede usar **Agregar lectura**, al extremo derecho de los filtros en Gestión de lecturas o abajo a la izquierda del calendario. También se puede conceder específicamente el permiso Django `readings.add_reading`; los usuarios de consulta no pueden registrar ni ven estos botones.

El formulario muestra la obligación disponible según `get_registration_plan`, la misma regla del bot: mensual del ciclo activo o su único seguimiento. No permite elegir ciclos cerrados, programaciones anuladas ni completadas. La mensual abre dos días antes del día programado. El seguimiento se programa diez días después de la fecha de toma mensual y abre un día antes de esa programación; cierra al abrir el siguiente ciclo mensual. Tanto el día de ingreso como la fecha de toma deben permitir esa obligación: registrar después no permite usar una fecha anterior a la apertura. Si la mensual fue el 02/09, el seguimiento abre el 11/09 y rechaza una fecha de toma del 07/09. En Telegram, una fecha fuera de ventana cancela el borrador sin confirmar la lectura ni habilitar su aprendizaje, informa la restricción y vuelve al inicio.

La captura web permite elegir la fecha de toma, que se muestra en **Fecha bot/web**, y conserva automáticamente la fecha y hora actuales en **Fecha de registro**. La fecha elegida debe pertenecer al ciclo activo, no puede ser futura ni anterior a la mensual si corresponde un seguimiento. Por ejemplo, el 07/09 se puede registrar una mensual de Chancay tomada el 19/08 para su programación del 18/08, mientras siga activo ese ciclo. También guarda el usuario responsable, el valor manual y una foto opcional JPG/PNG/WebP de hasta 10 MB. Admite hasta 12 dígitos enteros y 3 decimales usando punto o coma, sin letras, negativos, exponentes ni separadores de miles. Al guardar se comprueba nuevamente el pendiente dentro de una transacción. Una selección caducada o completada por otro operador debe consultarse de nuevo; un envío repetido de mensual no se convierte en seguimiento.

La tabla, los avisos y el calendario se actualizan tras guardar. El calendario muestra el registro verde en su fecha real de toma; la grilla anual conserva su agrupación por ciclo. La foto web se almacena como evidencia sin ejecutar OCR ni enviar imágenes a Cloudflare. Para habilitar aprendizaje, el administrador abre **Revisar foto** en la fila, compara la imagen y sus decimales y pulsa **La foto coincide: preparar aprendizaje local**. Genera candidatos sin Cloudflare y marca la etiqueta verificada solo si hay candidatos. Los históricos excluidos se rechazan.

Las rutas `/media/` se sirven mediante Django con sesión autenticada y sin caché compartida; solo se entregan archivos referenciados por una lectura. Si se publica detrás de un servidor web, no configurar una ruta estática pública que evite esta protección. La grilla prioriza lecturas confirmadas sobre borradores y anulaciones posteriores. Telegram y web comparten la validación de programaciones anuladas; los avisos omiten seguimientos sin ventana y anulaciones.

Usar dos ventanas de PowerShell con el entorno virtual activado:

```powershell
python manage.py runserver
```

```powershell
python manage.py run_telegram_bot
```

En Telegram, enviar `/start`. El bot muestra únicamente la opción **Ingresar lectura**. Se puede escribir el nombre del nodo (tolera errores de escritura) o abrir la lista de nodos autorizados. Después solicita la foto, detecta el valor y pide confirmarlo o corregirlo. Antes de guardar solicita elegir **Hoy** o **Escribir fecha**; esta última opción acepta una fecha real con formato `DD/MM/AAAA`, por ejemplo `31/08/2026`.

Para ingresar sin fotografía es obligatorio pulsar **Escribir lectura manualmente** antes de enviar el número. Si no se reconoce la foto, hay que elegir **Ingresar lectura manual** o **Cancelar registro**. El valor admite enteros o decimales con punto o coma, hasta 12 dígitos enteros y 3 decimales, sin signos, letras ni unidades. Cada paso repite su pregunta y sus botones cuando recibe texto, fotos, audios u otros mensajes que no corresponden. Los botones de preguntas anteriores no permiten saltar pasos ni confirmar otro registro. Tras registrar o cancelar, vuelve al menú inicial.

La programación definitiva se asigna al confirmar la fecha real de la lectura, siempre que pertenezca al ciclo activo. Las fechas de ciclos anteriores se conservan como historial en gris, pero no pueden reabrirse ni recibir nuevos registros desde el bot.

Antes de pedir la fotografía o el valor, el bot revisa las lecturas confirmadas del ciclo activo y explica si corresponde una **lectura mensual** o un **seguimiento**, con sus fechas. Si ya existen ambos registros, bloquea otro ingreso e indica cuándo se abre el siguiente ciclo. Por ejemplo, Huacho, con día mensual 3 y su ciclo de agosto completo, no admite otra lectura el 31/08: vuelve a permitirla desde el 01/09. Guardia Peruana, con día mensual 2, ya admite la lectura mensual de septiembre desde el 31/08; el seguimiento pendiente de agosto deja de ser la obligación activa.

La validación se repite al crear el borrador y al confirmar, para impedir un tercer registro incluso si otro operador completó el ciclo durante la conversación. No se aceptan fechas futuras ni fechas pertenecientes a ciclos ya cerrados. Un seguimiento no puede tener fecha anterior a la lectura mensual existente. Los registros históricos se conservan en LECTURAS WI-NET aunque el ingreso esté bloqueado.

La grilla se encuentra en http://127.0.0.1:8000/ y exige iniciar sesión.

La barra lateral izquierda permite cambiar entre:

- **Gestión de lecturas:** todos los registros, estados y evidencias.
- **LECTURAS WI-NET:** vista por ciclo mensual de todos los nodos activos de la base, incluidos los agregados por administración. La lista fija autorizada se mantiene únicamente para la importación de Excel.

La grilla WI-NET agrupa las mensuales por el ciclo de su programación, manteniendo
visible «Tomada el» con la fecha real. Por ejemplo, Guardia Peruana tiene su mensual
del 02/09 en la columna septiembre aunque la foto se tome el 31/08. Su seguimiento
del 10/09 aparece en ese mismo ciclo, como registro confirmado o como pendiente con
fecha programada. Los seguimientos se vinculan a una mensual del mismo nodo cuya
fecha real más diez días coincide con su programación; si hay varios posibles
orígenes, no se adivina el vínculo. Al cerrar el ciclo, el seguimiento ausente se
indica como no registrado, no como una obligación todavía activa.

Los registros importados sin clasificación y los seguimientos sin origen inequívoco
conservan su mes de fecha real con la etiqueta «Histórica · ciclo sin identificar».
La base operativa de agosto conserva su ciclo asignado explícitamente. Los cruces de
diciembre y enero se agrupan por el año del ciclo. Los registros sin fecha se muestran
aparte. Este cambio es de presentación: no modifica fechas, valores, programaciones,
recordatorios ni la vista cronológica de Gestión de lecturas.

## 6. Recordatorios

El proceso `run_telegram_bot` revisa y envía automáticamente los avisos cada cinco horas. También se puede ejecutar una revisión manual con:

```powershell
python manage.py send_reminders
```

Cada aviso corresponde a un nodo e incluye el botón **Registrar lectura**, que inicia directamente el flujo de fotografía para ese nodo.

Mientras un chat está seleccionando el nodo, enviando la foto, confirmando o corrigiendo el valor, o indicando la fecha, sus recordatorios quedan pausados para no interrumpir el proceso. Después de **8 minutos sin mensajes ni pulsaciones**, el bot cancela el borrador sin confirmar y muestra automáticamente el menú inicial una sola vez. En el menú no vuelve a escribir hasta que el usuario interactúe o corresponda un recordatorio. Cada nueva interacción durante un registro renueva el plazo; el tiempo de procesamiento del OCR no cuenta como inactividad. Al finalizar o volver al menú se reanudan los recordatorios.

La campana de la esquina superior derecha y Telegram comparten estas reglas:

- La ventana mensual comprende tres días contando el día de lectura: para el día 11 comienza el día 9.
- La ventana puede comenzar en el mes o año anterior: para el 2 de septiembre empieza el 31 de agosto. Desde ese día, la grilla muestra la lectura próxima (por ejemplo, **Lectura: faltan 2 días**) y los avisos corresponden al nuevo ciclo.
- La grilla calcula las próximas obligaciones aunque el bot no esté ejecutándose o el nodo no tenga chat. No crea lecturas ficticias ni duplica programaciones ya guardadas. Los ciclos anteriores permanecen como historial en gris, con la indicación **ciclo cerrado**.
- Después de registrar la lectura mensual, su único seguimiento vence diez días después de la fecha real de lectura y se avisa un día antes.
- Al comenzar la nueva ventana mensual, el seguimiento anterior deja de ser la obligación activa. Para una mensual del 11 de agosto tomada el 31, el seguimiento se programa para el 10 de septiembre y abriría el 9, justo cuando se cierra el ciclo anterior. En ese caso no tiene ventana disponible: no se adelanta el seguimiento y desde el 9 corresponde registrar la mensual de septiembre.
- Una lectura mensual atrasada continúa generando avisos aunque cambie el mes, hasta el inicio de la siguiente ventana mensual. Telegram conserva el intervalo de cinco horas mientras el bot esté funcionando.
- Al confirmar una lectura se completa únicamente la programación correspondiente a su fecha y ciclo.
- Cada envío exitoso se registra antes de intentar el siguiente. Si Telegram rechaza un destinatario, se registra el error y se continúa con los demás.

## Siguiente etapa

- Importar los nodos y el histórico desde el Excel actual.
- Exportar la grilla filtrada a `.xlsx`.
- Añadir auditoría detallada, copias de seguridad y PostgreSQL.
- Automatizar el bot, la web y los recordatorios con Docker Compose.
