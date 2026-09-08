# Graph Report - Bot_Corte_Programado  (2026-09-08)

## Corpus Check
- 66 files · ~189,324 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 644 nodes · 1691 edges · 38 communities (13 shown, 16 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 146 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4bca4056`
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
- SimpleAdminTests
- get_reading_notifications
- Auditoría del bot y almacenamiento — 07/09/2026
- 0009_alter_node_options.py
- Revisión posterior a la Administración simplificada

## God Nodes (most connected - your core abstractions)
1. `Reading` - 72 edges
2. `ReadingSchedule` - 61 edges
3. `Node` - 57 edges
4. `TelegramFlowTests` - 33 edges
5. `get_reading_notifications()` - 31 edges
6. `get_calendar_events()` - 26 edges
7. `OCRResult` - 26 edges
8. `prepare_reminder_jobs()` - 26 edges
9. `read_meter()` - 24 edges
10. `get_cycle_state()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `SimpleGroupAdmin` --uses--> `SimpleGroupForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `NodeAdmin` --uses--> `NodeAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingAdmin` --uses--> `ReadingAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingScheduleAdmin` --uses--> `ScheduleAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingAdmin` --uses--> `Reading`  [INFERRED]
  readings/admin_ui.py → readings/models.py

## Import Cycles
- None detected.

## Communities (38 total, 16 thin omitted)

### Community 0 - "run_telegram_bot.py"
Cohesion: 0.13
Nodes (46): DEFAULT_TYPE, active_chat_ids(), ask_reading_date(), authorized_nodes(), begin_node_selection(), callback(), cancel_pending_reading(), cancel_registration_markup() (+38 more)

### Community 1 - "Reading"
Cohesion: 0.07
Nodes (46): login_required, interface_required(), Meta, NodeAdminForm, ReadingAdminForm, ScheduleAdminForm, WebReadingForm, Command (+38 more)

### Community 2 - "prepare_reminder_jobs"
Cohesion: 0.08
Nodes (12): Command, BaseCommand, ReadingNotification, prepare_reminder_jobs(), Persist each successful delivery before attempting the next recipient., reminder_text(), send_reminder_jobs(), ConfirmedScheduleRegressionTests (+4 more)

### Community 3 - "ocr.py"
Cohesion: 0.06
Nodes (50): _candidate_digit_sequence(), _candidate_effective_value(), _candidate_payload(), _candidate_raw_text(), choose_consistent_candidate(), _decimal_geometry(), detect_red_decimal(), DisplayRegion (+42 more)

### Community 5 - "get_cycle_state"
Cohesion: 0.11
Nodes (16): Path, Command, BaseCommand, apply_baseline(), baseline_plan(), _notes(), atomic, One-time reconciliation of the user-approved August 2026 starting point. (+8 more)

### Community 8 - "tests.py"
Cohesion: 0.07
Nodes (19): Command, normalize(), parse_date(), parse_day(), parse_reading(), atomic, BaseCommand, find_best_node_name() (+11 more)

### Community 9 - "Bot de lecturas eléctricas"
Cohesion: 0.12
Nodes (15): 1. Requisitos, 2. Preparación en PowerShell, 3. Crear el bot, 4. Cargar datos iniciales, 5. Ejecutar, 6. Recordatorios, Bot de lecturas eléctricas, Componentes gratuitos (+7 more)

### Community 10 - "build_profile"
Cohesion: 0.09
Nodes (15): Command, BaseCommand, Evaluación local sin red y exportación reutilizable de ejemplos confirmados., append_attempt(), build_profile(), meter_scope(), Aprendizaje local por medidor; nunca utiliza valores anteriores como predicción., Called only after an operator verifies the photo against its decimal label. (+7 more)

### Community 23 - "ReadingAdmin"
Cohesion: 0.08
Nodes (12): display, FriendlyAdmin, NodeAdmin, atomic, ReadingAdmin, ReadingScheduleAdmin, ReminderLogAdmin, SimpleGroupAdmin (+4 more)

### Community 33 - "SimpleAdminTests"
Cohesion: 0.11
Nodes (6): SimpleGroupForm, Command, atomic, BaseCommand, TestCase, SimpleAdminTests

### Community 35 - "get_reading_notifications"
Cohesion: 0.10
Nodes (10): notifications(), get_calendar_events(), Return readings and the current obligation for every active node in a month., _task_state(), _task_status(), get_reading_notifications(), TestCase, UpcomingGridTests (+2 more)

### Community 37 - "Auditoría del bot y almacenamiento — 07/09/2026"
Cohesion: 0.12
Nodes (16): 1. Telegram puede completar una programación anulada — alta, 2. Recordatorios invitan a registrar un seguimiento sin ventana — media, 3. La grilla puede mostrar un borrador anulado como dato de una tarea completada — media, 4. Las fotografías tienen una ruta directa sin autenticación — alta si el servidor es accesible por otras personas, 5. Verificar una foto web no basta para incorporarla al aprendizaje — media, 6. Un nodo nuevo puede no aparecer en la grilla anual — media, Actualización posterior: correcciones solicitadas, Aprendizaje y fotos (+8 more)

### Community 42 - "Revisión posterior a la Administración simplificada"
Cohesion: 0.40
Nodes (4): Comportamientos comprobados, Hallazgos reproducidos, Límites, Revisión posterior a la Administración simplificada

## Knowledge Gaps
- **39 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 185 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Reading` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `get_reading_notifications`, `ocr.py`, `get_cycle_state`, `AnnualCycleTests`, `RegistrationRulesTests`, `tests.py`, `TelegramFlowTests`, `build_profile`, `WebRegistrationTests`, `ReadingAdmin`?**
  _High betweenness centrality (0.220) - this node is a cross-community bridge._
- **Why does `Node` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `get_reading_notifications`, `ocr.py`, `get_cycle_state`, `AnnualCycleTests`, `RegistrationRulesTests`, `tests.py`, `TelegramFlowTests`, `build_profile`, `WebRegistrationTests`?**
  _High betweenness centrality (0.141) - this node is a cross-community bridge._
- **Why does `ReadingSchedule` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `get_reading_notifications`, `ocr.py`, `get_cycle_state`, `AnnualCycleTests`, `RegistrationRulesTests`, `tests.py`, `build_profile`, `WebRegistrationTests`, `ReadingAdmin`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Reading` (e.g. with `ReadingAdminForm` and `ScheduleAdminForm`) actually correct?**
  _`Reading` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `ReadingSchedule` (e.g. with `ScheduleAdminForm` and `ReadingAdmin`) actually correct?**
  _`ReadingSchedule` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `Node` (e.g. with `NodeAdminForm` and `Command`) actually correct?**
  _`Node` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TelegramFlowTests` (e.g. with `Node` and `Reading`) actually correct?**
  _`TelegramFlowTests` has 2 INFERRED edges - model-reasoned connections that need verification._