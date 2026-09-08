# Graph Report - Bot_Corte_Programado  (2026-09-07)

## Corpus Check
- 65 files · ~111,342 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 621 nodes · 1626 edges · 43 communities (17 shown, 17 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 144 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `cb0aca95`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_telegram_bot.py
- Reading
- prepare_reminder_jobs
- ocr.py
- TelegramFlowTests
- get_cycle_state
- AnnualCycleTests
- RegistrationRulesTests
- tests.py
- Bot de lecturas eléctricas
- build_profile
- WebRegistrationTests
- ReadingsConfig
- reading_value
- 0004_backfill_reading_date.py
- AGENTS.md
- 0001_initial.py
- 0002_alter_reading_confirmed_value_and_more.py
- 0003_node_billing_day_node_due_day_node_provider_and_more.py
- 0005_remove_reminderlog_one_reminder_per_day_and_more.py
- ReadingAdmin
- 0007_reading_ocr_learning_verified.py
- 0008_exclude_historical_ocr_learning.py
- 0006_node_ocr_learning_generation_reading_ocr_attempts.py
- OCRResult
- UpcomingGridTests
- get_calendar_events
- AuditFixTests
- Auditoría del bot y almacenamiento — 07/09/2026
- 0009_alter_node_options.py
- OCRSelectionTests
- create_reading
- choose_consistent_candidate
- Revisión posterior a la Administración simplificada

## God Nodes (most connected - your core abstractions)
1. `Reading` - 72 edges
2. `ReadingSchedule` - 59 edges
3. `Node` - 57 edges
4. `TelegramFlowTests` - 33 edges
5. `get_reading_notifications()` - 31 edges
6. `prepare_reminder_jobs()` - 26 edges
7. `get_calendar_events()` - 25 edges
8. `OCRResult` - 25 edges
9. `get_cycle_state()` - 23 edges
10. `read_meter()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `NodeAdmin` --uses--> `NodeAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingAdmin` --uses--> `ReadingAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingScheduleAdmin` --uses--> `ScheduleAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingAdmin` --uses--> `Reading`  [INFERRED]
  readings/admin_ui.py → readings/models.py
- `ReadingAdmin` --uses--> `ReadingSchedule`  [INFERRED]
  readings/admin_ui.py → readings/models.py

## Import Cycles
- None detected.

## Communities (43 total, 17 thin omitted)

### Community 0 - "run_telegram_bot.py"
Cohesion: 0.09
Nodes (51): DEFAULT_TYPE, active_chat_ids(), ask_reading_date(), authorized_nodes(), begin_node_selection(), callback(), cancel_pending_reading(), cancel_registration_markup() (+43 more)

### Community 1 - "Reading"
Cohesion: 0.07
Nodes (43): login_required, interface_required(), Meta, NodeAdminForm, ReadingAdminForm, ScheduleAdminForm, notifications(), WebReadingForm (+35 more)

### Community 2 - "prepare_reminder_jobs"
Cohesion: 0.08
Nodes (12): Command, BaseCommand, ReadingNotification, prepare_reminder_jobs(), Persist each successful delivery before attempting the next recipient., reminder_text(), send_reminder_jobs(), ConfirmedScheduleRegressionTests (+4 more)

### Community 3 - "ocr.py"
Cohesion: 0.12
Nodes (22): _extract_json_object(), find_display_crop(), find_display_regions(), find_kba_display_crop(), generate_display_variants(), _intersection_over_union(), _order_points(), _parse_value() (+14 more)

### Community 5 - "get_cycle_state"
Cohesion: 0.12
Nodes (15): Command, BaseCommand, apply_baseline(), baseline_plan(), _notes(), atomic, One-time reconciliation of the user-approved August 2026 starting point., Only confirmed August records of active nodes participate; July is untouched. (+7 more)

### Community 7 - "RegistrationRulesTests"
Cohesion: 0.17
Nodes (4): get_registration_plan(), RegistrationPlan, TestCase, RegistrationRulesTests

### Community 8 - "tests.py"
Cohesion: 0.09
Nodes (13): Command, normalize(), parse_date(), parse_day(), parse_reading(), atomic, BaseCommand, create_interface_user() (+5 more)

### Community 9 - "Bot de lecturas eléctricas"
Cohesion: 0.12
Nodes (15): 1. Requisitos, 2. Preparación en PowerShell, 3. Crear el bot, 4. Cargar datos iniciales, 5. Ejecutar, 6. Recordatorios, Bot de lecturas eléctricas, Componentes gratuitos (+7 more)

### Community 10 - "build_profile"
Cohesion: 0.25
Nodes (6): build_profile(), meter_scope(), Aprendizaje local por medidor; nunca utiliza valores anteriores como predicción., technique(), LearningTests, TestCase

### Community 23 - "ReadingAdmin"
Cohesion: 0.05
Nodes (18): display, SimpleGroupForm, FriendlyAdmin, NodeAdmin, atomic, ReadingAdmin, ReadingScheduleAdmin, ReminderLogAdmin (+10 more)

### Community 33 - "OCRResult"
Cohesion: 0.29
Nodes (9): DisplayRegion, OCRResult, Consulta Workers AI solo cuando están configuradas sus credenciales., OCR local primero; Cloudflare solo actúa como respaldo y luego queda el modo…, read_meter(), read_meter_cloudflare(), OCRSafetyTests, patch (+1 more)

### Community 35 - "get_calendar_events"
Cohesion: 0.16
Nodes (6): get_calendar_events(), Return readings and the current obligation for every active node in a month., _task_state(), _task_status(), CalendarTests, NotificationTests

### Community 37 - "Auditoría del bot y almacenamiento — 07/09/2026"
Cohesion: 0.12
Nodes (16): 1. Telegram puede completar una programación anulada — alta, 2. Recordatorios invitan a registrar un seguimiento sin ventana — media, 3. La grilla puede mostrar un borrador anulado como dato de una tarea completada — media, 4. Las fotografías tienen una ruta directa sin autenticación — alta si el servidor es accesible por otras personas, 5. Verificar una foto web no basta para incorporarla al aprendizaje — media, 6. Un nodo nuevo puede no aparecer en la grilla anual — media, Actualización posterior: correcciones solicitadas, Aprendizaje y fotos (+8 more)

### Community 39 - "OCRSelectionTests"
Cohesion: 0.17
Nodes (6): detect_red_decimal(), Interpreta el reconocedor aplicado directamente al interior del visor., Lee la rueda roja de décimas ubicada al final de algunos medidores mecánicos., select_direct_recognition(), OCRSelectionTests, patch

### Community 40 - "create_reading"
Cohesion: 0.20
Nodes (11): Path, Command, BaseCommand, Evaluación local sin red y exportación reutilizable de ejemplos confirmados., create_reading(), get_pending_node_reading(), previous_confirmed_value(), validated_ocr_values() (+3 more)

### Community 41 - "choose_consistent_candidate"
Cohesion: 0.43
Nodes (3): choose_consistent_candidate(), OCRCandidate, Consenso del valor exacto, incluyendo su decimal, con experiencia del medidor.

### Community 42 - "Revisión posterior a la Administración simplificada"
Cohesion: 0.40
Nodes (4): Comportamientos comprobados, Hallazgos reproducidos, Límites, Revisión posterior a la Administración simplificada

## Knowledge Gaps
- **39 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 178 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Reading` connect `Reading` to `run_telegram_bot.py`, `OCRResult`, `prepare_reminder_jobs`, `get_calendar_events`, `AuditFixTests`, `get_cycle_state`, `AnnualCycleTests`, `UpcomingGridTests`, `create_reading`, `tests.py`, `build_profile`, `RegistrationRulesTests`, `TelegramFlowTests`, `WebRegistrationTests`, `ReadingAdmin`?**
  _High betweenness centrality (0.224) - this node is a cross-community bridge._
- **Why does `Node` connect `Reading` to `run_telegram_bot.py`, `OCRResult`, `prepare_reminder_jobs`, `get_calendar_events`, `AuditFixTests`, `get_cycle_state`, `AnnualCycleTests`, `UpcomingGridTests`, `tests.py`, `create_reading`, `build_profile`, `RegistrationRulesTests`, `TelegramFlowTests`, `WebRegistrationTests`, `ReadingAdmin`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Why does `ReadingSchedule` connect `Reading` to `run_telegram_bot.py`, `OCRResult`, `prepare_reminder_jobs`, `UpcomingGridTests`, `AuditFixTests`, `get_cycle_state`, `AnnualCycleTests`, `RegistrationRulesTests`, `tests.py`, `get_calendar_events`, `build_profile`, `WebRegistrationTests`, `ReadingAdmin`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Reading` (e.g. with `ReadingAdminForm` and `ScheduleAdminForm`) actually correct?**
  _`Reading` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `ReadingSchedule` (e.g. with `ScheduleAdminForm` and `ReadingAdmin`) actually correct?**
  _`ReadingSchedule` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `Node` (e.g. with `NodeAdminForm` and `Command`) actually correct?**
  _`Node` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TelegramFlowTests` (e.g. with `Node` and `Reading`) actually correct?**
  _`TelegramFlowTests` has 2 INFERRED edges - model-reasoned connections that need verification._