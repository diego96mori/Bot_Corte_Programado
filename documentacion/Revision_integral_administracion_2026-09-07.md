# Revisión posterior a la Administración simplificada

Fecha: 07/09/2026. Revisión de Graphify y código de reglas, canales de registro, vistas, permisos, administración y aprendizaje. Las 176 pruebas pasan. Modelos y migraciones están sincronizados. No se modificaron reglas ni datos operativos en esta revisión.

## Hallazgos reproducidos

1. **Calendario no respeta anulaciones explícitas (prioridad media).** `readings/services/calendar.py:72` reconstruye la mensual sin consultar el estado CANCELLED de la programación. Una mensual anulada del 11/09, consultada ese día, aparece roja como «Lectura para hoy», aunque `available_plan` impide registrarla. El bucle de seguimientos tampoco consulta la anulación. Debe mostrarse como anulada/no exigible, consistente con Gestión y con la prohibición de registrar.

2. **Eliminar una mensual deja un seguimiento pendiente sin representación coherente (prioridad media).** `readings/admin_ui.py:95` reconcilia únicamente la programación de la lectura eliminada. El calendario deriva los seguimientos de la mensual existente (`readings/services/calendar.py:91`). Reproducción: mensual del 11/09 y seguimiento pendiente del 21/09; tras eliminar la mensual, el seguimiento desaparece del calendario pero su programación continúa PENDING en la base. Conviene definir y aplicar una reconciliación explícita: conservar trazabilidad y marcar el seguimiento sin mensual como no exigible, sin borrar automáticamente otras lecturas confirmadas.

3. **La verificación de aprendizaje puede aceptar una revisión desactualizada (prioridad alta para calidad de datos).** `readings/admin_ui.py:104` recibe la confirmación únicamente por id; no comprueba que foto y valor coincidan con los mostrados al abrir la pantalla. Reproducción secuencial: abrir revisión de valor 100, cambiarlo a 200 desde otro acceso, confirmar la pantalla antigua; se marca 200 como verificado. La prueba usa OCR simulado, no transmite fotos ni depende de la precisión del modelo. Se requiere un identificador de versión o huella del contenido revisado, validado al guardar, y solicitar nueva revisión cuando cambie.

Reproducciones: `.artifact-work/audit_admin_rules.py`, que migra y escribe exclusivamente en SQLite en memoria. También confirmó que se puede crear un usuario desde el formulario simplificado y que la contraseña funciona.

## Comportamientos comprobados

- Mensual desde dos días antes; seguimiento desde un día antes de la programación calculada desde la toma mensual.
- Fechas futuras y ciclos cerrados rechazados, con reinicio de Telegram ante fecha fuera de ventana.
- Programaciones anuladas bloqueadas en ambos canales de registro.
- Seguimientos sin ventana omitidos en recordatorios.
- Protección del registro web por permiso y de fotos por sesión.
- Consulta sin Gestión, Administración ni registro; calendario/campana y grilla anual permitidos.
- Edición administrativa limitada a valor/foto; nodos sin eliminación; programaciones solo estado; recordatorios solo lectura.
- Código del nodo automático y chat predeterminado al crear.
- Borrado de una lectura aislada reabre su programación y conserva el ciclo vencido como cerrado.
- Históricos excluidos del aprendizaje; procesamiento de la revisión web sin Cloudflare.

## Límites

Las pruebas que pasan no cubrían los tres casos anteriores y no demuestran ausencia total de fallos. No se ejecutó una prueba de carga con procesos concurrentes ni una revisión visual de cada pantalla autenticada. La asociación de seguimientos depende de fechas y del texto de observaciones; cambiar el día mensual de un nodo con historial requiere una política de vigencia para evitar reclasificaciones inesperadas. No se ajustó esa política en esta revisión.

Conclusión: las reglas centrales y roles están comprobados, pero la coherencia de anulaciones/eliminaciones y la confirmación de aprendizaje necesitan las tres correcciones señaladas antes de considerar cerrada esta revisión.
