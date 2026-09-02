# Graph Report - Bot_Corte_Programado  (2026-09-01)

## Corpus Check
- 44 files · ~100,723 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 425 nodes · 1127 edges · 29 communities (9 shown, 10 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 100 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a6e86327`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_telegram_bot.py
- Reading
- prepare_reminder_jobs
- tests.py
- TelegramFlowTests
- get_cycle_state
- get_reading_notifications
- RegistrationRulesTests
- GridAccessTests
- Bot de lecturas eléctricas
- ReadingCycleRegressionTests
- ReadingsConfig
- reading_value
- 0004_backfill_reading_date.py
- AGENTS.md
- 0001_initial.py
- 0002_alter_reading_confirmed_value_and_more.py
- 0003_node_billing_day_node_due_day_node_provider_and_more.py
- 0005_remove_reminderlog_one_reminder_per_day_and_more.py

## God Nodes (most connected - your core abstractions)
1. `Reading` - 48 edges
2. `Node` - 42 edges
3. `ReadingSchedule` - 37 edges
4. `TelegramFlowTests` - 33 edges
5. `get_reading_notifications()` - 27 edges
6. `prepare_reminder_jobs()` - 26 edges
7. `get_calendar_events()` - 23 edges
8. `get_cycle_state()` - 23 edges
9. `RegistrationRulesTests` - 20 edges
10. `baseline_plan()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `Command` --uses--> `Reading`  [INFERRED]
  readings/management/commands/benchmark_cloudflare_ocr.py → readings/models.py
- `Command` --uses--> `Node`  [INFERRED]
  readings/management/commands/import_readings_excel.py → readings/models.py
- `Command` --uses--> `Reading`  [INFERRED]
  readings/management/commands/import_readings_excel.py → readings/models.py
- `Command` --uses--> `ReadingSchedule`  [INFERRED]
  readings/management/commands/import_readings_excel.py → readings/models.py
- `authorized_nodes()` --uses--> `Node`  [INFERRED]
  readings/management/commands/run_telegram_bot.py → readings/models.py

## Import Cycles
- None detected.

## Communities (29 total, 10 thin omitted)

### Community 0 - "run_telegram_bot.py"
Cohesion: 0.09
Nodes (55): DEFAULT_TYPE, active_chat_ids(), ask_reading_date(), authorized_nodes(), begin_node_selection(), callback(), cancel_pending_reading(), cancel_registration_markup() (+47 more)

### Community 1 - "Reading"
Cohesion: 0.07
Nodes (31): login_required, NodeAdmin, ReadingAdmin, ReadingScheduleAdmin, ReminderLogAdmin, Meta, Node, Reading (+23 more)

### Community 2 - "prepare_reminder_jobs"
Cohesion: 0.10
Nodes (13): Command, BaseCommand, ReminderLog, ReadingNotification, prepare_reminder_jobs(), Persist each successful delivery before attempting the next recipient., record_reminder_results(), reminder_text() (+5 more)

### Community 3 - "tests.py"
Cohesion: 0.07
Nodes (39): patch, Command, BaseCommand, choose_consistent_candidate(), detect_red_decimal(), DisplayRegion, _extract_json_object(), find_display_crop() (+31 more)

### Community 5 - "get_cycle_state"
Cohesion: 0.16
Nodes (15): Path, Command, BaseCommand, apply_baseline(), baseline_plan(), _notes(), atomic, One-time reconciliation of the user-approved August 2026 starting point. (+7 more)

### Community 6 - "get_reading_notifications"
Cohesion: 0.15
Nodes (5): notifications(), get_reading_notifications(), TestCase, UpcomingGridTests, NotificationTests

### Community 7 - "RegistrationRulesTests"
Cohesion: 0.16
Nodes (5): get_registration_plan(), Eligibility for new bot registrations, without changing historical records., RegistrationPlan, TestCase, RegistrationRulesTests

### Community 8 - "GridAccessTests"
Cohesion: 0.09
Nodes (11): Command, normalize(), parse_date(), parse_day(), parse_reading(), atomic, BaseCommand, AuthorizedNodesTests (+3 more)

### Community 9 - "Bot de lecturas eléctricas"
Cohesion: 0.14
Nodes (13): 1. Requisitos, 2. Preparación en PowerShell, 3. Crear el bot, 4. Cargar datos iniciales, 5. Ejecutar, 6. Recordatorios, Bot de lecturas eléctricas, Componentes gratuitos (+5 more)

## Knowledge Gaps
- **17 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 116 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Reading` connect `Reading` to `run_telegram_bot.py`, `prepare_reminder_jobs`, `tests.py`, `TelegramFlowTests`, `get_cycle_state`, `get_reading_notifications`, `RegistrationRulesTests`, `GridAccessTests`, `ReadingCycleRegressionTests`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Why does `Node` connect `Reading` to `run_telegram_bot.py`, `prepare_reminder_jobs`, `tests.py`, `TelegramFlowTests`, `get_cycle_state`, `get_reading_notifications`, `RegistrationRulesTests`, `GridAccessTests`, `ReadingCycleRegressionTests`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Why does `TelegramFlowTests` connect `TelegramFlowTests` to `Reading`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 28 inferred relationships involving `Reading` (e.g. with `Command` and `Command`) actually correct?**
  _`Reading` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `Node` (e.g. with `Command` and `authorized_nodes()`) actually correct?**
  _`Node` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `ReadingSchedule` (e.g. with `Command` and `confirm_reading()`) actually correct?**
  _`ReadingSchedule` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TelegramFlowTests` (e.g. with `Node` and `Reading`) actually correct?**
  _`TelegramFlowTests` has 2 INFERRED edges - model-reasoned connections that need verification._