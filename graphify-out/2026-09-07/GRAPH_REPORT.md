# Graph Report - Bot_Corte_Programado  (2026-09-07)

## Corpus Check
- 64 files · ~110,797 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 616 nodes · 1622 edges · 39 communities (14 shown, 16 thin omitted)
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
- tests.py
- TelegramFlowTests
- apply_baseline
- AnnualCycleTests
- RegistrationRulesTests
- create_interface_user
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
- UpcomingGridTests
- get_calendar_events
- AuditFixTests
- Auditoría del bot y almacenamiento — 07/09/2026
- 0009_alter_node_options.py

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

## Communities (39 total, 16 thin omitted)

### Community 0 - "run_telegram_bot.py"
Cohesion: 0.09
Nodes (56): DEFAULT_TYPE, active_chat_ids(), ask_reading_date(), authorized_nodes(), begin_node_selection(), callback(), cancel_pending_reading(), cancel_registration_markup() (+48 more)

### Community 1 - "Reading"
Cohesion: 0.07
Nodes (49): login_required, interface_required(), Meta, NodeAdminForm, ReadingAdminForm, ScheduleAdminForm, notifications(), WebReadingForm (+41 more)

### Community 2 - "prepare_reminder_jobs"
Cohesion: 0.06
Nodes (13): Command, BaseCommand, ReadingNotification, prepare_reminder_jobs(), Persist each successful delivery before attempting the next recipient., reminder_text(), send_reminder_jobs(), ConfirmedScheduleRegressionTests (+5 more)

### Community 3 - "tests.py"
Cohesion: 0.06
Nodes (47): Command, BaseCommand, normalize(), parse_date(), parse_day(), parse_reading(), choose_consistent_candidate(), detect_red_decimal() (+39 more)

### Community 5 - "apply_baseline"
Cohesion: 0.17
Nodes (12): Path, atomic, Command, BaseCommand, apply_baseline(), baseline_plan(), _notes(), atomic (+4 more)

### Community 7 - "RegistrationRulesTests"
Cohesion: 0.17
Nodes (4): get_registration_plan(), RegistrationPlan, TestCase, RegistrationRulesTests

### Community 8 - "create_interface_user"
Cohesion: 0.12
Nodes (6): create_interface_user(), Explicit permissions for pre-existing tests of the operational screens., AuthorizedNodesTests, GridAccessTests, ManagementStatusLabelTests, TestCase

### Community 9 - "Bot de lecturas eléctricas"
Cohesion: 0.12
Nodes (15): 1. Requisitos, 2. Preparación en PowerShell, 3. Crear el bot, 4. Cargar datos iniciales, 5. Ejecutar, 6. Recordatorios, Bot de lecturas eléctricas, Componentes gratuitos (+7 more)

### Community 10 - "build_profile"
Cohesion: 0.21
Nodes (6): Command, BaseCommand, build_profile(), meter_scope(), LearningTests, TestCase

### Community 23 - "ReadingAdmin"
Cohesion: 0.09
Nodes (12): display, FriendlyAdmin, NodeAdmin, atomic, ReadingAdmin, ReadingScheduleAdmin, ReminderLogAdmin, SimpleGroupAdmin (+4 more)

### Community 33 - "SimpleAdminTests"
Cohesion: 0.13
Nodes (6): SimpleGroupForm, Command, atomic, BaseCommand, TestCase, SimpleAdminTests

### Community 35 - "get_calendar_events"
Cohesion: 0.16
Nodes (6): get_calendar_events(), Return readings and the current obligation for every active node in a month., _task_state(), _task_status(), CalendarTests, NotificationTests

### Community 36 - "AuditFixTests"
Cohesion: 0.23
Nodes (4): Called only after an operator verifies the photo against its decimal label., verify_for_learning(), AuditFixTests, TestCase

### Community 37 - "Auditoría del bot y almacenamiento — 07/09/2026"
Cohesion: 0.12
Nodes (16): 1. Telegram puede completar una programación anulada — alta, 2. Recordatorios invitan a registrar un seguimiento sin ventana — media, 3. La grilla puede mostrar un borrador anulado como dato de una tarea completada — media, 4. Las fotografías tienen una ruta directa sin autenticación — alta si el servidor es accesible por otras personas, 5. Verificar una foto web no basta para incorporarla al aprendizaje — media, 6. Un nodo nuevo puede no aparecer en la grilla anual — media, Actualización posterior: correcciones solicitadas, Aprendizaje y fotos (+8 more)

## Knowledge Gaps
- **36 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+31 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 174 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Reading` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `tests.py`, `get_calendar_events`, `apply_baseline`, `AuditFixTests`, `AnnualCycleTests`, `UpcomingGridTests`, `RegistrationRulesTests`, `build_profile`, `TelegramFlowTests`, `WebRegistrationTests`, `create_interface_user`, `ReadingAdmin`?**
  _High betweenness centrality (0.227) - this node is a cross-community bridge._
- **Why does `Node` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `get_calendar_events`, `tests.py`, `AuditFixTests`, `AnnualCycleTests`, `apply_baseline`, `UpcomingGridTests`, `RegistrationRulesTests`, `build_profile`, `TelegramFlowTests`, `WebRegistrationTests`, `create_interface_user`?**
  _High betweenness centrality (0.145) - this node is a cross-community bridge._
- **Why does `ReadingSchedule` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `prepare_reminder_jobs`, `tests.py`, `AuditFixTests`, `apply_baseline`, `AnnualCycleTests`, `UpcomingGridTests`, `RegistrationRulesTests`, `get_calendar_events`, `build_profile`, `WebRegistrationTests`, `create_interface_user`, `ReadingAdmin`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `Reading` (e.g. with `ReadingAdminForm` and `ScheduleAdminForm`) actually correct?**
  _`Reading` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `ReadingSchedule` (e.g. with `ScheduleAdminForm` and `ReadingAdmin`) actually correct?**
  _`ReadingSchedule` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `Node` (e.g. with `NodeAdminForm` and `Command`) actually correct?**
  _`Node` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TelegramFlowTests` (e.g. with `Node` and `Reading`) actually correct?**
  _`TelegramFlowTests` has 2 INFERRED edges - model-reasoned connections that need verification._