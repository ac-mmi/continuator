# Continuator TUI Redesign

## Problem

The first TUI felt empty and passive: a single progress line and blank space until the briefing appeared. Professional terminal tools (Lazygit, K9s, GitUI, Claude Code) stay informative before, during, and after work.

## Design principles

1. **Never empty** — welcome screen when idle; activity feed + analysis panel while running; split metadata + briefing when done.
2. **Persistent status** — cyan status bar always shows current mode (`Ready`, `Analyzing chunk 2/4`, `Generating briefing`).
3. **Visual hierarchy** — Current Position, Active Problems, and Next Action use amber emphasis in the briefing panel.
4. **Extraction unchanged** — all pipeline hooks map to existing `ContinuatorConsole` callbacks via `TuiConsole`.

## Layout

```
┌ STATUS ─────────────────────────────────────────────────────┐
│ Ready · Analyzing chunk 2/4 · Generating briefing           │
├─────────────────────────────────────────────────────────────┤
│ WELCOME (idle)  OR  INFO BAR: file · size · chunks · est   │
├──────────────┬──────────────────────────────────────────────┤
│ ACTIVITY     │ ANALYSIS: stage + progress + rank detail     │
│ ✓ Parsed     ├──────────────────────────────────────────────┤
│ › Extract    │ CONTINUATION BRIEFING (streamed sections)    │
│ ○ Briefing   │   CURRENT POSITION  ← highlighted          │
│              │   NEXT ACTION       ← highlighted          │
│ METADATA     │                                              │
│ (after done) │                                              │
├──────────────┴──────────────────────────────────────────────┤
│ Copy · Claude · ChatGPT · Save  │  Open · Quit               │
└─────────────────────────────────────────────────────────────┘
```

## Components

| Module | Role |
|--------|------|
| `tui/widgets.py` | WelcomePanel, ActivityFeed, InfoBar, MetadataPanel |
| `tui/briefing_render.py` | Rich markup + section highlighting |
| `tui/console_adapter.py` | Pipeline → activity feed + status bar |
| `tui/app.py` | Three-panel shell, section streaming |
| `tui/styles.tcss` | Lazygit-inspired dark cyan theme |

## Activity feed mapping

| Pipeline event | Feed line |
|----------------|-----------|
| `on_reading` | › Reading conversation |
| `on_parsed` | ✓ Parsed conversation |
| `on_ranked` | ✓ Selected frontier chunks |
| `on_analyze_progress` | status bar: Analyzing chunk N/M |
| `on_building` | ✓ Extracted state · › Generating briefing |
| `on_analysis_complete` | ✓ Generated briefing |

## Briefing streaming

Extraction still returns the full briefing at once. The TUI **reveals sections incrementally** (PROJECT → Objective → … → Next Action) for a live feel without changing backend logic.

## Footer

Grouped actions:

- **Export group:** Copy, Claude, ChatGPT, Save
- **Nav group:** Open, Quit

Keyboard bindings unchanged: `C` `L` `G` `S` `O` `Q`.
