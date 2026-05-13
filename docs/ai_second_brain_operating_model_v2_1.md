# AI Second Brain — Operating Model v2
## Obsidian + OpenBrain + Meetily

**Owner:** Gniewko  
**Version:** v2 operational  
**Date:** 2026-04-19

---

## 1. Purpose

This is the operational version of the architecture.

It answers:
- what gets created
- where it lives
- what metadata it needs
- how it is processed daily
- how Meetily feeds the system
- how OpenBrain should support Obsidian without taking it over

---

## 2. Role split

## Obsidian
Use as the curated operating cockpit.

Owns:
- project notes
- decision notes
- meeting notes worth keeping
- people notes
- resource notes
- dashboards
- graph
- daily note flow

## OpenBrain
Use as memory and retrieval fabric.

Owns:
- raw meeting evidence indexing
- semantic search
- related note suggestions
- repeated-theme detection
- contradiction and stale-note flags
- synthesis drafts
- heartbeat reviews

## Meetily
Use as the structured evidence source for meetings.

Owns:
- transcript JSON
- raw meeting capture
- summary seed
- extraction input for AI workflows

---

## 3. Vault structure

```text
00 Inbox
01 Projects
03 Resources
04 People
05 Decisions
06 Meetings
07 Daily
90 Templates
99 System
Archive
```

### Rule
Do not create Areas yet.
If a taxonomy emerges later, add it deliberately.

---

## 4. Required plugins

## Core
- Properties
- Bases
- Daily Notes
- Templates
- Bookmarks
- Workspaces
- Graph View
- Canvas

## Community
- Smart Connections
- QuickAdd
- Tasks
- Dataview only if Bases does not cover a real need
- optionally Extended Graph

### Rule
No plugin without a concrete workflow benefit.

---

## 5. Naming convention

## Projects
`PRJ - <name>`

Examples:
- `PRJ - Identity modernization`
- `PRJ - Vendor governance refresh`

## Meetings
`MTG - <name> - YYYY-MM-DD`

Examples:
- `MTG - Vendor weekly - 2026-04-19`
- `MTG - Steering sync - 2026-04-19`

## Decisions
`DEC - <topic> - YYYY-MM-DD`

Examples:
- `DEC - IAM rollout governance - 2026-04-19`
- `DEC - Meeting note promotion rule - 2026-04-19`

## People
`PPL - <person name>`

## Resources
`RES - <topic>`

---

## 6. Metadata standard v2

## 6.1 Minimal global properties
Use this in almost every note:

```yaml
---
type:
status:
created:
review:
tags:
source:
project:
people:
theme:
---
```

### Field intent
- `type` = note class
- `status` = lifecycle state
- `created` = note creation date
- `review` = next review cadence or date
- `tags` = minimal tagging only
- `source` = origin, e.g. meetily, web, manual
- `project` = main project if applicable
- `people` = related people if applicable
- `theme` = optional loose topic cluster

## 6.2 Allowed type values
- `project`
- `meeting`
- `decision`
- `person`
- `resource`
- `daily`
- `inbox`

## 6.3 Allowed status values
Use a small controlled set:
- `active`
- `logged`
- `waiting`
- `done`
- `incubating`
- `archived`

---

## 7. Templates

## 7.1 Project template

```markdown
---
type: project
status: active
created: {{date:YYYY-MM-DD}}
review: weekly
tags:
source: manual
project:
people:
theme:
---

# Objective

# Scope

# Current state

# Key decisions

# Risks

# Stakeholders

# Next actions

# Related notes
```

## 7.2 Meeting template

```markdown
---
type: meeting
status: logged
created: {{date:YYYY-MM-DD}}
review:
tags:
source: meetily
project:
people:
theme:
---

# Summary

# Decisions
- 

# Action items
- 

# Risks / blockers
- 

# Linked notes
- 
```

## 7.3 Decision template

```markdown
---
type: decision
status: active
created: {{date:YYYY-MM-DD}}
review: monthly
tags:
source: manual
project:
people:
theme:
---

# Context

# Decision

# Why

# Implications

# Alternatives considered

# Related notes
```

## 7.4 Person template

```markdown
---
type: person
status: active
created: {{date:YYYY-MM-DD}}
review:
tags:
source: manual
project:
people:
theme:
---

# Role / context

# What matters

# Current topics

# Relevant meetings

# Related projects
```

## 7.5 Resource template

```markdown
---
type: resource
status: active
created: {{date:YYYY-MM-DD}}
review:
tags:
source:
project:
people:
theme:
---

# Summary

# Key takeaways

# Why it matters

# Linked decisions

# Related notes
```

---

## 8. Meetily operating workflow

## 8.1 Rule
Meetily JSON is evidence, not the final note.

## 8.2 Processing chain

```text
Meetily JSON
  -> extraction
  -> candidate summary / decisions / actions / people / topics
  -> concise Obsidian meeting note
  -> optional decision note(s)
  -> OpenBrain memory indexing
```

## 8.3 Fields to extract from every meeting JSON
- title
- date
- participants
- summary
- decisions
- action items
- blockers
- unresolved questions
- referenced projects
- referenced people
- repeated topics

## 8.4 Promotion rule
Only promote to Obsidian if at least one of these is true:
- a decision was made
- a next action matters later
- a risk or blocker matters later
- the meeting changes project context
- the meeting materially changes your understanding of a person, vendor, or topic

If none of the above is true, keep it in OpenBrain/raw only.

---

## 9. OpenBrain operating model v2

## 9.1 What should be stored in OpenBrain
- Meetily JSON and meeting-derived raw facts
- research fragments
- article captures
- synthesis drafts
- relation suggestions
- repeated-topic observations
- stale-note and contradiction flags

## 9.2 What should not be authoritative in OpenBrain
- final decision records
- final curated project notes
- final people notes
- final operational truth

## 9.3 Recommended memory classes
For your practical use, treat OpenBrain entries like:
- `MeetingEvidence`
- `WorkingSynthesis`
- `LinkSuggestion`
- `ReviewSignal`
- `ResearchCapture`
- `ArchitectureNote`

Even if the connector schema stays generic, keep this conceptual model.

## 9.4 Heartbeat jobs to run
- daily meeting extraction digest
- weekly stale-note scan
- weekly orphan-note / weak-link scan
- weekly repeated-theme report
- periodic contradiction scan

---

## 10. Bases configuration v2

## 10.1 Home dashboard
Create a `00 Home.md` note and embed these Bases views:
- Active Projects
- Recent Meetings
- Recent Decisions
- Inbox to process
- Review due

## 10.2 Suggested base views

### Projects
Filter:
- `type = project`

Columns:
- title
- status
- review
- created
- theme

### Meetings
Filter:
- `type = meeting`

Columns:
- title
- created
- project
- people
- source

### Decisions
Filter:
- `type = decision`

Columns:
- title
- created
- project
- status
- review

### People
Filter:
- `type = person`

Columns:
- title
- project
- theme
- review

### Review Due
Filter idea:
- notes where `review` is due or `status = active`

---

## 11. Graph configuration v2

## 11.1 Group by type
Use color groups for:
- project
- meeting
- decision
- person
- resource
- inbox/system

## 11.2 Graph operating rule
- global graph = weekly radar
- local graph = daily context map

## 11.3 Link discipline
Add a link only if it helps future retrieval.

Good links:
- meeting -> project
- meeting -> person
- meeting -> decision
- decision -> project
- resource -> decision
- project -> key people

Bad links:
- trivial mention links
- decorative links
- AI mass-links without review

---

## 12. Daily operating rhythm

## Morning
1. Open `00 Home`
2. Review active projects
3. Review recent meetings
4. Review decisions needing action
5. Pick top 1–3 moves for the day

## During work
1. Work from a project / decision note
2. Keep Properties + Local Graph + Smart Connections visible
3. Add only meaningful links
4. Fix metadata only where it improves later retrieval

## After meetings
1. Process Meetily extraction
2. Create short meeting note only if worth keeping
3. Promote durable decisions into `DEC` note
4. Link the note to project and relevant people

## Weekly review
1. Scan global graph for lonely notes and overloaded clusters
2. Review stale active project notes
3. Review inbox and unpromoted meeting outputs
4. Use OpenBrain signals to patch weak links or missing notes


---

## 13. RAW-first processing model

This section adds the preferred pattern inspired by AI second-brain workflows where the model processes **RAW files first** instead of writing directly into curated notes.

### Core rule
Do **not** send raw source files straight into the main Obsidian graph as regular notes.

Use this flow instead:

```text
RAW sources
→ OpenBrain / agent processing
→ review and promotion
→ curated Obsidian note
```

### What counts as RAW
Typical RAW inputs in this system:
- Meetily JSON
- full meeting transcripts
- clipped web articles
- PDFs
- vendor documents
- research dumps
- rough notes and exports

### Why this model is preferred
- AI works from original evidence instead of summaries of summaries
- OpenBrain becomes a true processing and retrieval layer
- Obsidian stays clean and navigable
- graph quality stays high
- only durable knowledge gets promoted

### Processing responsibilities
The processing layer should do four things:

#### 1. Extraction
Extract:
- decisions
- action items
- risks
- people
- projects
- recurring themes
- unresolved questions

#### 2. Classification
Assign a likely candidate type:
- meeting
- decision
- person
- resource
- project signal

#### 3. Link suggestion
Suggest:
- likely project
- likely related people
- possible existing note matches
- candidate decision lineage
- possible duplicates or conflicts

#### 4. Promotion recommendation
Return one of:
- `promote`
- `keep_raw`
- `needs_review`
- `discard`

### Promotion rule
A RAW item should be promoted into Obsidian only when it contains at least one of the following:
- a durable decision
- a meaningful follow-up
- a reusable insight
- a valuable project update
- a high-value reference worth later retrieval

If it is only noise, repetition, or context with no durable value, keep it in RAW memory and do not promote it.

### Meetily-specific application
This is the best first implementation target.

Recommended flow:

```text
Meetily JSON
→ OpenBrain ingest
→ extraction agent
→ meeting candidate
→ review
→ curated meeting note
→ optional decision note
```

### Daily operating impact
This model changes the daily workflow in a useful way:
- morning work starts from curated cockpit notes, not RAW
- after meetings, the user reviews promoted output instead of drafting from scratch
- OpenBrain becomes the processing engine
- Obsidian becomes the approved knowledge layer

### Architectural conclusion
The preferred system is not an autonomous note app.

It is a **RAW evidence in → agent extraction → curated memory out** pipeline.


---

## 14. OpenBrain connector debug findings

Observed behavior in this session:
- capability check worked
- sync check worked
- one small `brain_store` write succeeded
- subsequent `brain_store` calls returned misleading `Resource not found`

### Most likely explanation
This does **not** look like a true missing resource.
It looks like one of these:
1. unstable gateway routing for that tool
2. intermittent connector/session issue
3. payload-sensitive failure surfaced as the wrong error
4. backend/tool registry desynchronization after first write

### Operational conclusion
Treat the OpenBrain connector as **partially available** right now:
- reads/checks appear usable
- writes are not reliable enough to trust blindly

### Safe workaround
Use this flow until connector stability is verified:
1. write canonical notes to Obsidian / file first
2. keep deterministic `match_key`
3. run `brain_sync_check`
4. store to OpenBrain only after successful connector retry
5. if connector fails, preserve import-ready markdown

---

## 15. Recommended next implementation steps

## Step 1
Deploy the Obsidian structure and templates first.

## Step 2
Standardize Meetily extraction into the meeting template.

## Step 3
Use OpenBrain only for memory support and suggestions.

## Step 4
Stabilize the write path before relying on automatic OpenBrain persistence.

## Step 5
After 4–6 weeks, decide whether `theme` should become `area` or remain lightweight.

---

## 16. Final rule set

### Keep
- small metadata model
- strong note typing
- concise meeting promotion
- local graph during work
- global graph during review
- Bases as cockpit
- OpenBrain as assistive memory

### Avoid
- giant taxonomy early
- transcript clutter in the graph
- autonomous rewriting of curated notes
- plugin sprawl
- excessive link generation

---

## 17. One-line operating doctrine

**Capture with Meetily, remember with OpenBrain, curate and operate from Obsidian.**
