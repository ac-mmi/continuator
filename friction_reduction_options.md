# Friction Reduction Options

**Status:** Design only — evaluate paths to easier testing and early adoption  
**Goal:** Reduce steps from "I have a conversation" → "I have a continuation briefing / checkpoint"  
**Out of scope:** Extension implementation, browser integrations, V10 changes

---

## Problem

Current happy path for testers:

```
Copy conversation from ChatGPT / Claude / Cursor
  → paste into text editor
  → save as chat.txt
  → continuator continue chat.txt
  → read briefing (or copy from TUI)
```

**Friction points:**

| Step | Pain |
|------|------|
| Save intermediate file | Extra app switch, naming, cleanup |
| Remember CLI syntax | File path, subcommand |
| Re-run on edits | Re-save file or duplicate |
| Platform export formats | JSON vs plain text varies by host |

For **product validation** (`validation_plan_v2.md`), every extra step reduces completion rate of the resume protocol. For **early adoption**, friction before first "wow" moment kills conversion.

---

## Evaluation framework

Each option scored on five dimensions:

| Dimension | Scale | Meaning |
|-----------|-------|---------|
| **Implementation complexity** | Low / Medium / High | Engineering effort in Continuator repo (no V10) |
| **User friction** | Low / Medium / High | Steps for user after copying conversation |
| **Reliability** | Low / Medium / High | Format fidelity, failure modes, repeatability |
| **Platform support** | Narrow / Broad | macOS / Linux / Windows / browser hosts |
| **MVP suitability** | ✅ / ⚠️ / ❌ | Fit for *testing and demand validation* right now |

**MVP suitability** is weighted toward speed-to-learn and breadth of testers — not long-term product completeness.

---

## Option 1 — Clipboard mode

**Concept:** Read conversation directly from system clipboard — no file.

```bash
continuator continue --clipboard
continuator checkpoint --clipboard
# or shorthand
continuator continue -p   # paste
```

**User flow:**

```
Copy conversation → continuator continue --clipboard → briefing
```

### Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation complexity | **Low** | `keyboard.py` already has `copy_to_clipboard`; add `read_clipboard()` via `pbpaste` / `xclip` / PowerShell — ~40–80 LOC + tests |
| User friction | **Low** | One command after copy; eliminates save-file step entirely |
| Reliability | **Medium** | Clipboard may truncate on some systems; rich text vs plain text; empty clipboard errors |
| Platform support | **Broad** | macOS (`pbpaste`), Linux (`xclip`/`xsel`), Windows (`Get-Clipboard`) — graceful degrade with message |
| MVP suitability | **✅** | Best ROI for validation cohort |

### Pros

- Matches mental model: "I just copied the chat"
- Works for ChatGPT power users, researchers, learners immediately
- No host integration required
- Composes with existing pipeline unchanged

### Cons

- No persistent artifact unless user also runs `checkpoint` (could auto-save to `.continuator/`)
- Large transcripts may hit OS clipboard limits (rare > 1MB)
- Cannot re-run `--update` without re-copy unless checkpoint stores snapshot

### Existing code leverage

- Output clipboard: `continuator/keyboard.py`, TUI `c` binding
- Input path: extend `read_transcript()` or parallel `read_clipboard()`

---

## Option 2 — STDIN mode

**Concept:** Pipe or paste conversation into stdin — no file.

```bash
pbpaste | continuator continue -
continuator continue - < chat.txt
cat chat.txt | continuator checkpoint -
```

**User flow (macOS):**

```
Copy → pbpaste | continuator continue -
```

### Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation complexity | **Low** | **Already shipped** — `read_transcript("-")` in `runtime.py`; all subcommands accept `-` |
| User friction | **Medium** | Requires pipe idiom or heredoc; non-obvious to non-CLI users |
| Reliability | **High** | No clipboard size quirks; deterministic bytes |
| Platform support | **Broad** | Unix pipes universal; Windows needs `Get-Content` / type redirection |
| MVP suitability | **✅** | Zero build — **documentation and examples only** |

### Pros

- Works today
- Scriptable for benchmark corpus and CI
- Composes with `tee` to save file if needed: `pbpaste | tee chat.txt | continuator continue -`

### Cons

- Discoverability near zero — testers don't know `-` exists
- Pipe syntax intimidates ChatGPT-only users
- Interactive paste into terminal is awkward (EOF confusion)

### Gap

Not a product gap — a **UX/documentation gap**. Help text mentions `-` but onboarding doesn't lead with it.

---

## Option 3 — Drag-and-drop transcript

**Concept:** Drop `.txt` / `.json` onto CLI, TUI, or OS open-with handler.

**Variants:**

| Variant | Where |
|---------|-------|
| A | TUI file drop zone (Textual supports drag) |
| B | Shell: `continuator continue @path` or open-with association |
| C | macOS Quick Action / Finder service |

**User flow (TUI):**

```
Drag chat.txt onto Continuator window → auto-run continue
```

### Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation complexity | **Medium** (TUI) / **Low** (open-with) | TUI drop handler ~50–100 LOC; OS associations are packaging/docs |
| User friction | **Low** | Familiar desktop pattern; still requires export-to-file from host |
| Reliability | **High** | File-based; same as today once file exists |
| Platform support | **Medium** | TUI drag: cross-platform via Textual; Quick Actions macOS-only |
| MVP suitability | **⚠️** | Helps users who already saved a file; doesn't remove save step from browser |

### Pros

- Improves TUI default experience (`continuator` with no args)
- Good for repeat testers with saved exports
- No clipboard size limits

### Cons

- **Does not eliminate** export-from-ChatGPT step — only eliminates path typing
- Open-with requires install/packaging (`.app`, `.desktop`)
- JSON export shapes vary — existing parser helps but not all hosts

### Existing code leverage

- TUI already has `DirectoryTree`, file path input, `read_transcript`

---

## Option 4 — Browser extension

**Concept:** Chrome/Firefox extension reads ChatGPT/Claude/Gemini thread in-page → sends to Continuator.

**User flow:**

```
Click extension → "Checkpoint" → briefing in sidebar or clipboard
```

### Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation complexity | **High** | DOM scraping per host, manifest v3, store review, `continuator serve` bridge — weeks |
| User friction | **Low** | Best UX for browser-primary users |
| Reliability | **Medium** | Host UI changes break selectors; auth/session edge cases |
| Platform support | **Broad** (browser) | Chrome + Firefox; not Cursor/CLI users |
| MVP suitability | **❌** | Explicitly deferred (`integration_roadmap.md` Phase 5); overkill for demand test |

### Pros

- Lowest friction for largest addressable audience long-term
- Natural checkpoint/resume surface in-browser

### Cons

- **Out of scope for this cycle** per product direction
- Maintenance burden per host (ChatGPT DOM churn)
- Requires running local `serve` or cloud API — security/trust story
- Validates integration demand, not extraction quality, if bundled too early

### Verdict for now

**Design reference only.** Revisit after CLI friction fixes + validation pass (`validation_plan_v2.md` Phase V2).

---

## Option 5 — Cursor integration

**Concept:** Cursor extension observes agent chat → checkpoint to `.continuator/checkpoint.yaml` → resume injects briefing.

**User flow:**

```
Command palette → "Continuator: Checkpoint" → done
```

### Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation complexity | **High** | Extension host APIs uncertain; SDK + serve + storage — Phase 3 (`extension_strategy.md`) |
| User friction | **Low** | Best for P0 validation audience (Cursor users) |
| Reliability | **Medium–High** | Once wired, stable; blocked on chat API access |
| Platform support | **Narrow** | Cursor / VS Code fork only |
| MVP suitability | **❌** for *fastest* path — **✅** for *highest-value* audience after CLI proof |

### Pros

- #1 ranked user in `validation_plan_v2.md`
- Repo-local `.continuator/checkpoint.yaml` already designed for this
- `continuator serve` endpoints exist for thin client

### Cons

- **Weeks not days** — API discovery is week-1 blocker per extension strategy
- Validates distribution channel before core resume quality proven
- Not available to ChatGPT-only testers

### Verdict for now

**Follow-on after clipboard/stdin + 8 user validation sessions.** Prototype API feasibility in parallel, don't block demand test.

---

## Option 6 — Shared-link import

**Concept:** Paste a ChatGPT/Claude share URL → Continuator fetches and extracts transcript.

```bash
continuator continue --url "https://chatgpt.com/share/..."
```

**User flow:**

```
Share conversation → copy link → continuator continue --url <link>
```

### Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation complexity | **Medium–High** | HTTP fetch + HTML/JSON parse per host; auth walls; ToS; brittle scrapers |
| User friction | **Low** | No export, no file — if it works |
| Reliability | **Low–Medium** | Share pages change; private chats unavailable; rate limits |
| Platform support | **Medium** | Per-host implementers (OpenAI, Anthropic, Google) |
| MVP suitability | **❌** | High breakage risk during validation; legal/ToS ambiguity |

### Pros

- Eliminates copy-paste entirely for shared threads
- Easy to demo in marketing

### Cons

- Scraping shared pages is fragile and may violate ToS
- Doesn't work for private/unshared threads (majority of dev sessions)
- Each host needs separate parser maintenance
- Failed fetch = worse UX than file path

### Verdict for now

**Defer.** If pursued later, start with one host + official export API only — not HTML scrape.

---

## Comparison matrix

| Option | Complexity | User friction | Reliability | Platform | MVP suitability |
|--------|:----------:|:-------------:|:-----------:|:--------:|:---------------:|
| **1. Clipboard mode** | Low | **Low** | Medium | Broad | **✅** |
| **2. STDIN mode** | **None** (exists) | Medium | **High** | Broad | **✅** (docs) |
| **3. Drag-and-drop** | Medium | Low–Med | High | Medium | **⚠️** |
| **4. Browser extension** | High | **Low** | Medium | Browser | **❌** |
| **5. Cursor integration** | High | **Low** | Med–High | Narrow | **❌** now / **✅** later |
| **6. Shared-link import** | Med–High | Low | **Low** | Medium | **❌** |

```
Friction (user)     ▲
                    │  4 Browser    5 Cursor
                    │       6 URL
                    │  1 Clipboard
                    │  3 Drag-drop
                    │  2 STDIN
                    └──────────────────────────► Complexity
```

---

## Recommended fastest path

### Tier 0 — Today, zero code (1 day)

**Lead with STDIN + pipe recipes** in README and validation onboarding:

```bash
# macOS
pbpaste | continuator continue -

# Linux
xclip -o | continuator continue -

# Save optional copy while continuing
pbpaste | tee session.txt | continuator continue -
```

Add to `continuator --help` epilog and `validation_plan_v2.md` participant instructions.

**Why:** Already implemented; only discoverability blocks adoption.

---

### Tier 1 — Highest ROI build (2–4 days)

**Ship clipboard input mode** (`--clipboard` / `-p`) across `continue`, `checkpoint`, `explain`, `export`.

| Property | Value |
|----------|-------|
| Effort | ~40–80 LOC + cross-platform tests |
| Friction | Copy → one command |
| Risk | Low — no V10, no extensions |
| Validates | Core extraction + resume for all P0/P1 groups except pure browser |

**Optional pairing:** auto-write `.continuator/checkpoint.yaml` when running `continue --clipboard --save-checkpoint` for resume validation without a named file.

---

### Tier 2 — TUI polish (3–5 days, parallel)

**Paste buffer in default TUI** — multiline text area: paste conversation → Enter → run.

**Drag-and-drop** onto TUI window for `.txt` / `.json`.

Improves `continuator` (no subcommand) path for less CLI-comfortable testers.

---

### Tier 3 — After validation gate (weeks+)

| When | Option |
|------|--------|
| Resume pass ≥ 80% on corpus | Cursor integration spike (Phase 3) |
| ≥ 60% repeat intent from ChatGPT users | Browser extension design review (Phase 5) |
| Never first | Shared-link scrape |

---

## Demand validation protocol (recommended)

Use friction reduction itself as the experiment:

### Cohort A — STDIN docs only (control)

- Instructions: `pbpaste | continuator continue -`
- Measure: completion rate, time-to-first-briefing

### Cohort B — Clipboard flag (treatment)

- Instructions: `continuator continue --clipboard`
- Same metrics

### Success signals

| Signal | Interpretation |
|--------|----------------|
| Cohort B completion > A by ≥ 20% | Clipboard worth shipping |
| Time-to-first-briefing < 30s | Friction acceptable for validation |
| ≥ 50% run checkpoint + resume protocol | Demand for state product, not just briefing |
| Unprompted "how do I use in Cursor?" | Signal to start Phase 3 extension |

**Do not** invest in browser/Cursor until clipboard+stdin cohorts complete `resume_validation_runner.md` on ≥ 5 real sessions.

---

## What not to do (this cycle)

| Action | Why |
|--------|-----|
| Build browser extension | Out of scope; high maintenance |
| Build Cursor extension before resume validation | Validates distribution before product |
| Shared-link scraping | Fragile, ToS risk, fails on private chats |
| Retrain V10 for UX | Friction is input path, not extraction |
| New extraction formats | JSON import already in `read_transcript` |

---

## Suggested user-facing messaging (post Tier 0+1)

**Before:**

> Save your chat as a `.txt` file and run `continuator continue chat.txt`

**After:**

> Copy your conversation, then run:
> `continuator continue --clipboard`
>
> Or: `pbpaste | continuator continue -`

**For validation participants:**

> Copy → `continuator checkpoint --clipboard` → `continuator resume`

---

## Implementation notes (when approved — not in this doc's scope)

| Item | Location | Touch |
|------|----------|-------|
| `read_clipboard()` | `continuator/keyboard.py` | New |
| `--clipboard` flag | `commands/*_cmd.py` | Shared parent parser |
| TUI paste area | `continuator/tui/app.py` | New widget |
| Docs | `README.md`, `cli-ux-examples.md` | Examples |

**Invariant:** All paths call existing `run_continuation()` / `extract_full()` — no V10 changes.

---

## Related documents

- `validation_plan_v2.md` — who to test with and phasing
- `resume_validation_runner.md` — protocol friction depends on easy checkpoint
- `extension_strategy.md` — Cursor/browser deferred architecture
- `integration_roadmap.md` — Phase 3+ timeline
- `continuator/docs/cli-ux-examples.md` — existing UX patterns
