# Auditoría del bot y almacenamiento — 07/09/2026

## Actualización posterior: correcciones solicitadas

Los seis hallazgos principales descritos abajo fueron corregidos después de esta auditoría. El texto original se conserva como evidencia del estado anterior. Se agregó validación compartida de programaciones anuladas; se eliminaron avisos de seguimientos sin ventana y se alinearon sus proyecciones; la grilla prioriza confirmaciones; `/media/` exige sesión y referencia existente; Administración tiene una acción explícita de revisión y generación OCR local para aprendizaje, con exclusión de históricos; la grilla anual consulta todos los nodos activos. No se eliminaron fotos ni se modificaron lecturas históricas. Las reproducciones actuales están en `readings/test_audit_fixes.py`; el script de auditoría original reproduce el código anterior y ya no debe usarse como prueba de aceptación.

## Resultado y alcance

Se revisaron el grafo de Graphify, configuración, modelos, rutas, permisos, formularios, vistas, plantillas, flujo Telegram, reglas de registro, recordatorios, calendario, grilla anual, aprendizaje OCR y comandos de importación/evaluación. Se ejecutaron las 162 pruebas existentes: todas pasan. La revisión no garantiza ausencia de errores: se encontraron casos no cubiertos por esas pruebas.

La base operativa se consultó mediante SQLite en modo de solo lectura. Las reproducciones con escrituras se hicieron en una base independiente en memoria; no se enviaron fotos a Cloudflare ni mensajes a Telegram. No se corrigió ni eliminó código de aplicación o información operativa en esta auditoría. El script de reproducción está en `.artifact-work/audit_probe.py`.

No se realizó una prueba de carga concurrente, una nueva evaluación de precisión sobre imágenes reales ni una comprobación visual de cada pantalla en un navegador autenticado.

## Hallazgos prioritarios

### 1. Telegram puede completar una programación anulada — alta

En `readings/management/commands/run_telegram_bot.py`, `prepare_pending_schedule` recupera una programación por nodo y fecha sin rechazar `CANCELLED`. `confirm_reading` después la cambia a `COMPLETED`. La web sí rechaza ese estado en `readings/services/web_registration.py:available_plan`.

Reproducción: programación mensual anulada → borrador manual Telegram → confirmación válida en fecha → lectura `CONFIRMED`, programación `COMPLETED`. Por tanto, los dos canales no cumplen de forma idéntica la regla de anulación.

Corrección propuesta: validación compartida del estado y tipo de programación, tanto al comenzar como al confirmar. Mantener la anulación hasta una reapertura administrativa explícita.

### 2. Recordatorios invitan a registrar un seguimiento sin ventana — media

`readings/services/notifications.py` conserva `shortened_follow_up = due_date >= cutoff` y genera avisos durante el tiempo restante. Esa excepción pertenecía a la regla anterior que permitía adelantar seguimientos.

Reproducción: nodo con mensual día 11, tomada el 31/08, seguimiento programado para el 10/09, cierre el 09/09. El 07/09 se genera un aviso, pero `get_registration_plan` rechaza el ingreso porque no existe ventana disponible. Los textos de disponibilidad en recordatorios y algunas proyecciones de las grillas también necesitan alinearse con esta regla.

Corrección propuesta: obtener apertura, cierre y disponibilidad de una fuente compartida; no emitir un botón de registro para una obligación que no puede abrir antes de su cierre.

### 3. La grilla puede mostrar un borrador anulado como dato de una tarea completada — media

`readings/views.py:reading_grid` ordena todos los registros de una programación por creación descendente; `templates/readings/grid.html` muestra el primero. No prioriza la lectura confirmada.

Reproducción: una confirmación de 100 seguida de un borrador anulado de 999 muestra el borrador como registro elegido mientras la programación sigue `COMPLETED`. El problema afecta la presentación; la confirmación correcta sigue en la base. En la instantánea real revisada todas las 290 lecturas estaban confirmadas, por lo que la reproducción no demuestra que ya esté ocurriendo en esos datos.

Corrección propuesta: elegir la confirmación para la fila completada y presentar los intentos/borradores como historial separado.

### 4. Las fotografías tienen una ruta directa sin autenticación — alta si el servidor es accesible por otras personas

La configuración efectiva tiene `DEBUG=True`. `config/urls.py` registra `/media/` con `django.views.static.serve`, sin el requisito de iniciar sesión usado en las vistas de lecturas. Quien pueda acceder al servidor y conozca la URL podría abrir la imagen directamente.

Esto no prueba que el equipo sea accesible desde Internet. El alcance depende de la red y del modo de publicación. Corrección propuesta: servir evidencias mediante una vista autorizada y configurar su entrega protegida al desplegar. No se debe asumir que ocultar el enlace en la grilla protege el archivo.

### 5. Verificar una foto web no basta para incorporarla al aprendizaje — media

El formulario web guarda la imagen como evidencia, sin ejecutar OCR y sin generar `ocr_attempts`. `build_profile` omite registros sin intentos del medidor actual, aunque tengan `ocr_learning_verified=True`.

Se reprodujo una fotografía marcada como verificada pero sin intentos: aporta cero ejemplos. Mi explicación anterior de que bastaría una revisión visual para habilitar su aprendizaje era incompleta.

Corrección propuesta: después de la revisión, generar candidatos OCR locales para esa foto y guardar su huella y ámbito del medidor antes de incorporarla. El comando `evaluate_ocr --learn` contiene parte de ese mecanismo, pero actúa sobre un conjunto amplio; no conviene ejecutarlo indiscriminadamente ni habilitar las fotos históricas excluidas.

### 6. Un nodo nuevo puede no aparecer en la grilla anual — media

La gestión y el calendario consultan nodos de la base. `annual_grid` utiliza los nombres de la lista fija `AUTHORIZED_NODES`. Hay 34 nodos en la base y uno fuera de esa lista. Su existencia puede ser intencional, pero un nodo agregado por administración no entra automáticamente en la grilla anual.

Corrección propuesta: decidir si esa lista es una restricción operativa permanente o una semilla de importación; si todos los nodos activos deben mostrarse, consultar la base de forma consistente.

## Reglas comprobadas y límites

- Mensual: abre dos días antes de la fecha programada; incluye cruces de mes y año.
- Seguimiento: fecha programada diez días después de la toma mensual; abre un día antes y termina al abrir la siguiente mensual.
- Guardia Peruana: mensual tomada el 02/09 → seguimiento permitido desde el 11/09; una toma del 07/09 es rechazada aunque se ingrese después.
- 200 Millas: agosto completo → mensual de septiembre disponible desde el 09/09 para su programación del 11/09.
- No se permiten fechas futuras ni reabrir ciclos cerrados por los canales ordinarios.
- Los estados confirmados limitan a una mensual y un seguimiento por ciclo en el flujo normal. La web firma la selección para rechazar envíos repetidos o pendientes que cambiaron.
- En Telegram, una fecha fuera de ventana cancela el borrador y devuelve al inicio. Un borrador puede conservarse en la base como `CANCELLED`, con foto; no es una lectura confirmada ni un ejemplo de aprendizaje.
- La web requiere `readings.add_reading`; los usuarios de consulta no pueden registrar. Telegram autoriza por el chat asociado al nodo, no por `TELEGRAM_ADMIN_CHAT_IDS`. En un grupo autorizado, esto no equivale a una lista individual de operadores.
- Administración e importación histórica permiten cambios fuera del flujo ordinario. No se les aplican automáticamente todas las reglas del registro web/Telegram; los cambios administrativos requieren cuidado.
- El tipo mensual/seguimiento se infiere del texto `notes`. Editar ese texto puede alterar la clasificación. Un campo explícito de tipo y ciclo sería más robusto.
- Las transacciones ayudan, pero no se verificó carga simultánea. La base no tiene una restricción única de lectura confirmada por programación; no se debe presentar la concurrencia como demostrada por las pruebas secuenciales.

## Dónde están los datos

Configurado en `config/settings.py`:

- Base SQLite: `C:/Users/user/Documents/Diego/Bot_Corte_Programado/db.sqlite3`.
- Imágenes: `C:/Users/user/Documents/Diego/Bot_Corte_Programado/media/meter_photos/AAAA/MM/`.
- Respaldos existentes: `C:/Users/user/Documents/Diego/Bot_Corte_Programado/backups/`.
- Credenciales/configuración local: `.env`; no es la base de lecturas.
- `graphify-out/` contiene el mapa del código, no las lecturas del negocio.

SQLite guarda las tablas dentro de un archivo; no hay aquí un servidor PostgreSQL/MySQL ni una base de lecturas en Cloudflare. Cloudflare se usa como servicio externo de reconocimiento cuando el flujo lo requiere.

La columna `photo` guarda una ruta relativa, por ejemplo `meter_photos/2026/09/web-….jpg`. Los bytes de la foto están en el disco, no dentro de SQLite. La carpeta año/mes corresponde al guardado del archivo y puede diferir de la fecha de toma indicada por el operador.

Para restaurar lecturas y evidencias se necesitan tanto `db.sqlite3` como `media/`. Los respaldos SQLite existentes no implican que también se hayan respaldado las fotos. `.gitignore` excluye base, fotos, `.env` y respaldos: subir código a GitHub no los respalda.

## Tablas e inventario observado

| Tabla | Filas | Función |
|---|---:|---|
| `readings_node` | 34 | Catálogo de nodos: nombre, código, ubicación, medidor, suministro, concesionaria, día mensual, chat autorizado, activo y versión de aprendizaje. |
| `readings_readingschedule` | 331 | Obligaciones: nodo, fecha programada, pendiente/completada/anulada y observaciones que identifican el tipo. |
| `readings_reading` | 290 | Capturas: programación, fecha de toma, valor detectado y confirmado, foto, origen, responsable, estado, fecha de creación/confirmación e historial OCR. Las 290 estaban confirmadas. |
| `readings_reminderlog` | 424 | Avisos enviados: programación, chat, fecha/hora e identificador del mensaje; permite controlar el intervalo de recordatorios. |
| `auth_user` | 1 | Usuarios web, contraseña almacenada mediante hash y atributos de acceso. |
| `auth_group` | 0 | Grupos de usuarios. |
| `auth_permission` | 40 | Permisos de las aplicaciones. |
| `auth_group_permissions` | 0 | Relación entre grupos y permisos. |
| `auth_user_groups` | 0 | Relación entre usuarios y grupos. |
| `auth_user_user_permissions` | 0 | Permisos asignados directamente; un superusuario no necesita filas aquí para tener permisos. |
| `django_session` | 10 | Sesiones web; diez filas no significa diez usuarios conectados. |
| `django_admin_log` | 0 | Historial de operaciones efectuadas mediante administración Django. |
| `django_content_type` | 10 | Catálogo técnico de modelos para permisos y administración. |
| `django_migrations` | 26 | Migraciones aplicadas, incluidas las de Django y las ocho de lecturas. |
| `sqlite_sequence` | 10 | Contadores internos de identificadores autoincrementales. |

Relación principal: **nodo → programaciones → lecturas**. Una programación puede tener varios intentos, aunque el flujo operativo deba conservar una sola confirmación. Los recordatorios también pertenecen a una programación. Los registros web pueden enlazar al usuario en `confirmed_by`; Telegram conserva identificadores y nombre del operador en sus propios campos.

Fechas: `due_date` es la programada; `reading_date` es la toma indicada; `created_at` es creación del registro; `confirmed_at` es confirmación. La pantalla usa hora de Lima. En Telegram, creación puede preceder a confirmación porque primero se crea un borrador.

La comprobación SQLite `quick_check` dio `ok`. Se observaron 18 referencias a imágenes y ninguna faltante. Hay 19 archivos de foto: uno no tiene referencia en la base actual.

## Aprendizaje y fotos

No existe una tabla independiente de entrenamiento. `readings_reading.ocr_attempts` guarda JSON con propuestas, técnicas, confianza, huella y ámbito del medidor. `ocr_learning_verified` habilita una etiqueta revisada; `ocr_learning_excluded` impide usar los históricos excluidos.

`build_profile` calcula en memoria estadísticas de hasta 100 registros elegibles recientes, deduplicando fotos. No modifica los pesos de RapidOCR ni entrena Gemma. La versión `ocr_learning_generation` permite separar experiencias de distintos medidores o reiniciar el perfil.

En la instantánea revisada: 18 lecturas excluidas del aprendizaje y cero marcadas como verificadas. Por ello no hay ejemplos verificados aportando al perfil en ese momento. Esto es distinto de que el sistema no pueda ejecutar OCR: puede reconocer con sus modelos existentes, pero aún no obtiene calibración de ejemplos propios elegibles.

## Elementos sin uso o candidatos a limpieza

- `select_direct_recognition` en `readings/services/ocr.py`: se referencia desde pruebas, pero no desde el flujo OCR productivo inspeccionado. Candidato a retirada junto con sus pruebas específicas si no se desea conservar como utilidad.
- `TELEGRAM_ADMIN_CHAT_IDS` en `config/settings.py`: se carga, pero no encontré consumidores en el código. No controla actualmente quién puede registrar.
- Parámetro `edit` de `finish_reading`: no se usa dentro de la función.
- `billing_day` y `due_day`: se importan y almacenan, pero no deciden las ventanas de lectura actuales. Son metadatos, no necesariamente basura.
- Foto sin referencia actual: `media/meter_photos/2026/08/telegram_AQADWQxrG64BGUR-.jpg`. Conviene revisar si pertenece a un respaldo o intento anterior antes de eliminarla.
- `.artifact-work/`, cachés y salidas de Graphify son artefactos regenerables o de trabajo; `backups/` y `documentacion/` tienen una función deliberada. No se deben confundir ausencia de importaciones con archivos inútiles.
- Mantener migraciones, pruebas, `.venv`, `media`, base, configuración y plantillas usadas. No se eliminó ningún archivo durante la auditoría.

## Orden propuesto de corrección

1. Compartir validación de anulaciones entre Telegram y web.
2. Alinear notificaciones y proyecciones con las nuevas ventanas.
3. Corregir la elección del registro mostrado en la grilla.
4. Proteger el acceso a las fotografías según el modo de publicación.
5. Completar el proceso explícito de aprendizaje de fotos web verificadas.
6. Unificar el catálogo de nodos y revisar candidatos a limpieza.
