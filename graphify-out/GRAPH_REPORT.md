# Graph Report - Bot_Corte_Programado  (2026-09-08)

## Corpus Check
- 66 files · ~189,351 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 646 nodes · 1682 edges · 44 communities (16 shown, 19 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 141 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1bb5ebd5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_telegram_bot.py
- Reading
- prepare_reminder_jobs
- ocr.py
- TelegramFlowTests
- apply_baseline
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
- admin_ui.py
- 0007_reading_ocr_learning_verified.py
- 0008_exclude_historical_ocr_learning.py
- 0006_node_ocr_learning_generation_reading_ocr_attempts.py
- SimpleAdminTests
- admin_forms.py
- ReadingAdmin
- SimpleGroupForm
- Auditoría del bot y almacenamiento — 07/09/2026
- 0009_alter_node_options.py
- SimpleUserAdmin
- NodeAdmin
- patch
- Revisión posterior a la Administración simplificada
- TestCase

## God Nodes (most connected - your core abstractions)
1. `Reading` - 67 edges
2. `ReadingSchedule` - 59 edges
3. `Node` - 55 edges
4. `TelegramFlowTests` - 33 edges
5. `get_reading_notifications()` - 31 edges
6. `OCRResult` - 26 edges
7. `prepare_reminder_jobs()` - 26 edges
8. `get_calendar_events()` - 26 edges
9. `read_meter()` - 24 edges
10. `get_cycle_state()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `AuditFixTests` --uses--> `OCRResult`  [INFERRED]
  readings/test_audit_fixes.py → readings/services/ocr.py
- `LearningTests` --uses--> `OCRResult`  [INFERRED]
  readings/test_ocr_learning.py → readings/services/ocr.py
- `NodeAdminForm` --uses--> `Node`  [INFERRED]
  readings/admin_forms.py → readings/models.py
- `NodeAdmin` --uses--> `NodeAdminForm`  [INFERRED]
  readings/admin_ui.py → readings/admin_forms.py
- `ReadingAdminForm` --uses--> `Reading`  [INFERRED]
  readings/admin_forms.py → readings/models.py

## Import Cycles
- None detected.

## Communities (44 total, 19 thin omitted)

### Community 0 - "run_telegram_bot.py"
Cohesion: 0.12
Nodes (50): DEFAULT_TYPE, active_chat_ids(), ask_reading_date(), authorized_nodes(), begin_node_selection(), callback(), cancel_pending_reading(), cancel_registration_markup() (+42 more)

### Community 1 - "Reading"
Cohesion: 0.06
Nodes (47): login_required, interface_required(), notifications(), Meta, Node, Reading, ReadingSchedule, ReminderLog (+39 more)

### Community 2 - "prepare_reminder_jobs"
Cohesion: 0.06
Nodes (14): Command, BaseCommand, prepare_reminder_jobs(), Persist each successful delivery before attempting the next recipient., reminder_text(), send_reminder_jobs(), TestCase, UpcomingGridTests (+6 more)

### Community 3 - "ocr.py"
Cohesion: 0.06
Nodes (51): patch, Command, BaseCommand, _candidate_digit_sequence(), _candidate_effective_value(), _candidate_payload(), _candidate_raw_text(), choose_consistent_candidate() (+43 more)

### Community 5 - "apply_baseline"
Cohesion: 0.19
Nodes (11): Path, Command, BaseCommand, apply_baseline(), baseline_plan(), _notes(), atomic, Only confirmed August records of active nodes participate; July is untouched. (+3 more)

### Community 7 - "RegistrationRulesTests"
Cohesion: 0.17
Nodes (4): get_registration_plan(), RegistrationPlan, TestCase, RegistrationRulesTests

### Community 8 - "tests.py"
Cohesion: 0.07
Nodes (19): Command, normalize(), parse_date(), parse_day(), parse_reading(), atomic, BaseCommand, find_best_node_name() (+11 more)

### Community 9 - "Bot de lecturas eléctricas"
Cohesion: 0.12
Nodes (15): 1. Requisitos, 2. Preparación en PowerShell, 3. Crear el bot, 4. Cargar datos iniciales, 5. Ejecutar, 6. Recordatorios, Bot de lecturas eléctricas, Componentes gratuitos (+7 more)

### Community 10 - "build_profile"
Cohesion: 0.10
Nodes (15): Command, BaseCommand, Evaluación local sin red y exportación reutilizable de ejemplos confirmados., build_profile(), meter_scope(), Aprendizaje local por medidor; nunca utiliza valores anteriores como predicción., Called only after an operator verifies the photo against its decimal label., review_identity() (+7 more)

### Community 23 - "admin_ui.py"
Cohesion: 0.22
Nodes (5): FriendlyAdmin, ReadingScheduleAdmin, ReminderLogAdmin, SimpleGroupAdmin, register

### Community 34 - "admin_forms.py"
Cohesion: 0.22
Nodes (5): Meta, NodeAdminForm, ReadingAdminForm, ScheduleAdminForm, WebReadingForm

### Community 35 - "ReadingAdmin"
Cohesion: 0.21
Nodes (3): display, atomic, ReadingAdmin

### Community 36 - "SimpleGroupForm"
Cohesion: 0.24
Nodes (4): SimpleGroupForm, Command, atomic, BaseCommand

### Community 37 - "Auditoría del bot y almacenamiento — 07/09/2026"
Cohesion: 0.12
Nodes (16): 1. Telegram puede completar una programación anulada — alta, 2. Recordatorios invitan a registrar un seguimiento sin ventana — media, 3. La grilla puede mostrar un borrador anulado como dato de una tarea completada — media, 4. Las fotografías tienen una ruta directa sin autenticación — alta si el servidor es accesible por otras personas, 5. Verificar una foto web no basta para incorporarla al aprendizaje — media, 6. Un nodo nuevo puede no aparecer en la grilla anual — media, Actualización posterior: correcciones solicitadas, Aprendizaje y fotos (+8 more)

### Community 39 - "SimpleUserAdmin"
Cohesion: 0.33
Nodes (3): SimpleUserAdmin, sync_staff(), UserAdmin

### Community 42 - "Revisión posterior a la Administración simplificada"
Cohesion: 0.40
Nodes (4): Comportamientos comprobados, Hallazgos reproducidos, Límites, Revisión posterior a la Administración simplificada

## Knowledge Gaps
- **39 isolated node(s):** `Componentes gratuitos`, `1. Requisitos`, `2. Preparación en PowerShell`, `Respaldo opcional con Cloudflare`, `OCR gratuito y aprendizaje por medidor` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 187 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Reading` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `admin_forms.py`, `ocr.py`, `ReadingAdmin`, `apply_baseline`, `prepare_reminder_jobs`, `AnnualCycleTests`, `tests.py`, `RegistrationRulesTests`, `build_profile`, `TelegramFlowTests`, `WebRegistrationTests`, `admin_ui.py`?**
  _High betweenness centrality (0.202) - this node is a cross-community bridge._
- **Why does `Node` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `admin_forms.py`, `prepare_reminder_jobs`, `TelegramFlowTests`, `apply_baseline`, `AnnualCycleTests`, `RegistrationRulesTests`, `tests.py`, `build_profile`, `WebRegistrationTests`, `admin_ui.py`?**
  _High betweenness centrality (0.136) - this node is a cross-community bridge._
- **Why does `ReadingSchedule` connect `Reading` to `run_telegram_bot.py`, `SimpleAdminTests`, `admin_forms.py`, `ReadingAdmin`, `prepare_reminder_jobs`, `apply_baseline`, `AnnualCycleTests`, `RegistrationRulesTests`, `tests.py`, `build_profile`, `WebRegistrationTests`, `admin_ui.py`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Are the 38 inferred relationships involving `Reading` (e.g. with `ReadingAdminForm` and `ScheduleAdminForm`) actually correct?**
  _`Reading` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `ReadingSchedule` (e.g. with `ScheduleAdminForm` and `ReadingAdmin`) actually correct?**
  _`ReadingSchedule` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `Node` (e.g. with `NodeAdminForm` and `Command`) actually correct?**
  _`Node` has 33 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TelegramFlowTests` (e.g. with `Node` and `Reading`) actually correct?**
  _`TelegramFlowTests` has 2 INFERRED edges - model-reasoned connections that need verification._