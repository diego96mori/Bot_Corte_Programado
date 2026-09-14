# Graph Report - Bot_Corte_Programado  (2026-09-14)

## Corpus Check
- 66 files · ~190,174 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 654 nodes · 1728 edges · 42 communities (17 shown, 16 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 146 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `be8f31bd`
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
- AuditFixTests
- WebRegistrationTests
- ReadingsConfig
- reading_value
- 0004_backfill_reading_date.py
- AGENTS.md
- 0001_initial.py
- 0002_alter_reading_confirmed_value_and_more.py
- 0003_node_billing_day_node_due_day_node_provider_and_more.py
- 0005_remove_reminderlog_one_reminder_per_day_and_more.py
- admin_ui.py
- 0007_reading_ocr_learning_verified.py
- 0008_exclude_historical_ocr_learning.py
- 0006_node_ocr_learning_generation_reading_ocr_attempts.py
- SimpleAdminTests
- ReadingAdmin
- UpcomingGridTests
- ocr_learning.py
- Auditoría del bot y almacenamiento — 07/09/2026
- 0009_alter_node_options.py
- build_profile
- SimpleUserAdmin
- Revisión posterior a la Administración simplificada

## God Nodes (most connected - your core abstractions)
1. `Reading` - 72 edges
2. `ReadingSchedule` - 61 edges
3. `Node` - 57 edges
4. `TelegramFlowTests` - 33 edges
5. `get_reading_notifications()` - 31 edges
6. `OCRResult` - 27 edges
7. `read_meter()` - 27 edges
8. `OCRSafetyTests` - 27 edges
9. `get_calendar_events()` - 26 edges
10. `prepare_reminder_jobs()` - 26 edges

## Surprising Connections (you probably didn't know these)
- `SimpleGroupAdmin` --uses--> `SimpleGroupForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `NodeAdminForm` --uses--> `Node`  [INFERRED]
  readings/admin_forms.py → readings/models.py
- `NodeAdmin` --uses--> `NodeAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingAdminForm` --uses--> `WebReadingForm`  [INFERRED]
  readings/admin_forms.py → readings/forms.py
- `ReadingAdminForm` --uses--> `Reading`  [INFERRED]
  readings/admin_forms.py → readings/models.py

## Import Cycles
- None detected.

## Communities (42 total, 16 thin omitted)

### Community 0 - "run_telegram_bot.py"
Cohesion: 0.09
Nodes (55): DEFAULT_TYPE, active_chat_ids(), ask_reading_date(), authorized_nodes(), begin_node_selection(), callback(), cancel_pending_reading(), cancel_registration_markup() (+47 more)

### Community 1 - "Reading"
Cohesion: 0.06
Nodes (42): login_required, interface_required(), ScheduleAdminForm, notifications(), WebReadingForm, Meta, Node, Reading (+34 more)

### Community 2 - "prepare_reminder_jobs"
Cohesion: 0.08
Nodes (14): Command, BaseCommand, ReminderLog, ReadingNotification, prepare_reminder_jobs(), Persist each successful delivery before attempting the next recipient., record_reminder_results(), reminder_text() (+6 more)

### Community 3 - "ocr.py"
Cohesion: 0.05
Nodes (53): Command, BaseCommand, _apply_display_format(), _candidate_digit_sequence(), _candidate_effective_value(), _candidate_payload(), _candidate_raw_text(), choose_consistent_candidate() (+45 more)

### Community 5 - "get_cycle_state"
Cohesion: 0.11
Nodes (16): Path, Command, BaseCommand, apply_baseline(), baseline_plan(), _notes(), atomic, One-time reconciliation of the user-approved August 2026 starting point. (+8 more)

### Community 7 - "RegistrationRulesTests"
Cohesion: 0.17
Nodes (4): get_registration_plan(), RegistrationPlan, TestCase, RegistrationRulesTests

### Community 8 - "tests.py"
Cohesion: 0.09
Nodes (13): Command, normalize(), parse_date(), parse_day(), parse_reading(), atomic, BaseCommand, create_interface_user() (+5 more)

### Community 9 - "Bot de lecturas eléctricas"
Cohesion: 0.12
Nodes (15): 1. Requisitos, 2. Preparación en PowerShell, 3. Crear el bot, 4. Cargar datos iniciales, 5. Ejecutar, 6. Recordatorios, Bot de lecturas eléctricas, Componentes gratuitos (+7 more)

### Community 10 - "AuditFixTests"
Cohesion: 0.23
Nodes (4): Called only after an operator verifies the photo against its decimal label., verify_for_learning(), AuditFixTests, TestCase

### Community 23 - "admin_ui.py"
Cohesion: 0.18
Nodes (6): FriendlyAdmin, NodeAdmin, ReadingScheduleAdmin, ReminderLogAdmin, SimpleGroupAdmin, register

### Community 33 - "SimpleAdminTests"
Cohesion: 0.08
Nodes (9): Meta, NodeAdminForm, ReadingAdminForm, SimpleGroupForm, Command, atomic, BaseCommand, TestCase (+1 more)

### Community 34 - "ReadingAdmin"
Cohesion: 0.18
Nodes (3): display, atomic, ReadingAdmin

### Community 36 - "ocr_learning.py"
Cohesion: 0.22
Nodes (9): Command, BaseCommand, Evaluación local sin red y exportación reutilizable de ejemplos confirmados., append_attempt(), meter_scope(), Aprendizaje local por medidor; nunca utiliza valores anteriores como predicción., review_identity(), review_token() (+1 more)

### Community 37 - "Auditoría del bot y almacenamiento — 07/09/2026"
Cohesion: 0.12
Nodes (16): 1. Telegram puede completar una programación anulada — alta, 2. Recordatorios invitan a registrar un seguimiento sin ventana — media, 3. La grilla puede mostrar un borrador anulado como dato de una tarea completada — media, 4. Las fotografías tienen una ruta directa sin autenticación — alta si el servidor es accesible por otras personas, 5. Verificar una foto web no basta para incorporarla al aprendizaje — media, 6. Un nodo nuevo puede no aparecer en la grilla anual — media, Actualización posterior: correcciones solicitadas, Aprendizaje y fotos (+8 more)

### Community 39 - "build_profile"
Cohesion: 0.32
Nodes (3): build_profile(), LearningTests, TestCase

### Community 40 - "SimpleUserAdmin"
Cohesion: 0.33
Nodes (3): SimpleUserAdmin, sync_staff(), UserAdmin

### Community 42 - "Revisión posterior a la Administración simplificada"
Cohesion: 0.40
Nodes (4): Comportamientos comprobados, Hallazgos reproducidos, Límites, Revisión posterior a la Administración simplificada

## Knowledge Gaps
- **39 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 186 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Reading` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `ReadingAdmin`, `ocr.py`, `ocr_learning.py`, `get_cycle_state`, `prepare_reminder_jobs`, `build_profile`, `tests.py`, `AnnualCycleTests`, `AuditFixTests`, `UpcomingGridTests`, `RegistrationRulesTests`, `TelegramFlowTests`, `WebRegistrationTests`, `admin_ui.py`?**
  _High betweenness centrality (0.217) - this node is a cross-community bridge._
- **Why does `Node` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `UpcomingGridTests`, `ocr.py`, `get_cycle_state`, `AnnualCycleTests`, `build_profile`, `tests.py`, `RegistrationRulesTests`, `AuditFixTests`, `TelegramFlowTests`, `WebRegistrationTests`, `admin_ui.py`?**
  _High betweenness centrality (0.140) - this node is a cross-community bridge._
- **Why does `ReadingSchedule` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `ReadingAdmin`, `prepare_reminder_jobs`, `UpcomingGridTests`, `get_cycle_state`, `AnnualCycleTests`, `ocr.py`, `tests.py`, `build_profile`, `AuditFixTests`, `RegistrationRulesTests`, `WebRegistrationTests`, `admin_ui.py`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Reading` (e.g. with `ReadingAdminForm` and `ScheduleAdminForm`) actually correct?**
  _`Reading` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `ReadingSchedule` (e.g. with `ScheduleAdminForm` and `ReadingAdmin`) actually correct?**
  _`ReadingSchedule` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `Node` (e.g. with `NodeAdminForm` and `Command`) actually correct?**
  _`Node` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TelegramFlowTests` (e.g. with `Node` and `Reading`) actually correct?**
  _`TelegramFlowTests` has 2 INFERRED edges - model-reasoned connections that need verification._