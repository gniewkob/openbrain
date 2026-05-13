# AI Second Brain Documentation
## Obsidian + OpenBrain + Meetily

**Owner:** Gniewko  
**Status:** Draft v1  
**Intended destination:** OpenBrain and/or Obsidian  
**Last updated:** 2026-04-19

---

## 1. Executive summary

This document defines a practical, low-noise, executive-grade second-brain architecture built around:

- **Obsidian** as the curated knowledge layer and operational cockpit
- **OpenBrain** as the memory, retrieval, and agent-assist layer
- **Meetily** as the meeting evidence and extraction layer

The architecture is intentionally **not** a fully autonomous AI-managed vault. The system is designed to preserve trust, auditability, and usability.

### Core architecture statement

- **Meetily** = meeting evidence layer
- **OpenBrain** = memory and retrieval layer
- **Obsidian** = curated knowledge and operating cockpit

### Short formulation

**OpenBrain should help think and remember. Obsidian should store what has been judged important enough to keep, link, and act on.**

---

## 2. Core decision

The system should be **hybrid**, but with **hard role separation**.

### Obsidian should own

- curated project notes
- decision records
- meeting summaries worth keeping
- stakeholder / people notes
- curated resource notes
- graph exploration
- Bases dashboards and operating views

### OpenBrain should own

- semantic memory
- retrieval across fragmented inputs
- raw source indexing
- related-note suggestions
- contradiction detection
- repeated-theme detection
- stale-note detection
- draft synthesis generation
- memory support for agents

### Meetily should own

- raw meeting capture
- transcript JSON as the evidence layer
- extraction of key points
- summary generation
- meeting source objects that can be parsed by agents

---

## 3. Architectural model

```text
[RAW SOURCES]
Meetily JSON / transcripts / web clips / PDFs / article captures / research dumps

    -> ingest

[OPENBRAIN]
semantic memory / extraction / retrieval / suggestions / pattern detection

    -> promotion with review

[OBSIDIAN]
curated notes / project memory / decisions / people / resources / graph / Bases
```

### Preferred flow

- RAW -> OpenBrain
- OpenBrain -> proposals / syntheses / suggestions
- user review -> Obsidian curated note

### Explicit anti-goal

Avoid uncontrolled reverse flow where AI rewrites curated notes without approval.

---

## 4. Guiding principles

1. Human-approved knowledge is distinct from machine-generated working memory.
2. Raw evidence must remain conceptually prior to generated summaries.
3. Meeting transcripts are evidence, not the final note.
4. Graph should represent curated knowledge topology, not transcript noise.
5. AI should suggest links, not create giant uncontrolled webs.
6. Metadata and note types matter more than complex folder trees.
7. Local graph is more useful day to day than global graph.
8. Bases is the operational cockpit; graph is the exploration layer.

---

## 5. Obsidian architecture

## 5.1 Recommended folder structure

```text
00 Inbox
01 Projects
02 Areas
03 Resources
04 People
05 Decisions
06 Meetings
07 Daily
90 Templates
99 System
Archive
```

### Important note on Areas

Areas should remain **optional** at the start.

Do **not** formalize areas too early. The first stable version of the system should rely mainly on:

- note type
- note status
- links between notes
- optional theme/context fields

This avoids freezing an artificial taxonomy before actual usage patterns emerge.

---

## 5.2 Core plugins

Recommended core plugins:

- Properties
- Bases
- Daily Notes
- Templates
- Bookmarks
- Workspaces
- Canvas
- Graph View

### Why

- **Properties** gives structure
- **Bases** gives operational database-like views
- **Daily Notes** supports daily cadence
- **Graph** supports exploration and context recall
- **Canvas** supports synthesis and visual reasoning

---

## 5.3 Recommended community plugins

Recommended plugin stack:

- **Smart Connections**
- **QuickAdd**
- **Tasks**
- **Dataview** only where Bases is insufficient
- optionally **Extended Graph** for richer visuals

### Plugin philosophy

Keep the plugin layer **small and durable**.

Avoid building the entire system on fragile automation or custom scripting unless there is a very clear return.

---

## 6. Metadata model

## 6.1 Recommended start: minimal model

### Mandatory properties

```yaml
type:
status:
created:
tags:
```

### Optional but useful

```yaml
project:
people:
theme:
source:
review:
```

### Recommended note types

- `project`
- `meeting`
- `decision`
- `person`
- `resource`

### Why this model is preferred

This model is deliberately **note-type-first**, not taxonomy-first.

It allows:

- meaningful graph grouping
- clean Bases views
- flexible growth
- delayed decision on areas/domains

---

## 6.2 What not to do early

Do not start with:

- large area taxonomy
- deep folder logic
- many note subtypes
- heavy tag frameworks
- fully formalized knowledge ontology

The system should first prove daily usefulness, then gain complexity.

---

## 7. Meeting intelligence architecture with Meetily

This is one of the strongest parts of the overall setup.

## 7.1 Core rule

**Meetily JSON should be treated as raw evidence, not as the main note.**

## 7.2 Three-layer meeting model

### Layer A — Raw

Stored as source material:

- Meetily JSON
- optional full transcript
- original summary output

This layer should **not** become part of the main curated graph.

### Layer B — Extracted

From Meetily JSON extract these fields:

- meeting title
- date
- participants
- summary
- decisions
n- action items
- blockers / risks
- unresolved questions
- mentioned entities
- related project hints

### Layer C — Curated note in Obsidian

The final operational note should contain only what is worth remembering and navigating later.

Suggested structure:

```markdown
---
type: meeting
status: logged
project:
people:
created:
source: meetily
review:
---

# Summary
2–5 sentences

# Decisions
- ...

# Action items
- ...

# Risks / blockers
- ...

# Links
- [[PRJ - ...]]
- [[PPL - ...]]
- [[DEC - ...]]
```

## 7.3 Why this matters

This model:

- preserves audit trail
- prevents transcript sprawl
- keeps graph quality high
- turns meetings into reusable decision memory
- supports OpenBrain retrieval on the raw layer

---

## 8. Graph strategy

## 8.1 Global graph

Use the global graph as a **weekly radar**, not as the main daily interface.

Purpose:

- detect clusters
- notice isolated notes
- spot unusual density
- inspect system shape

## 8.2 Local graph

Use local graph **daily** while working on a project, decision, or person note.

Purpose:

- immediate context recall
- relation checking
- quick gap discovery
- navigating nearby knowledge

## 8.3 Recommended grouping logic

At the start, group graph by **note type**, not by business area.

Suggested group categories:

- project
- meeting
- decision
- person
- resource
- inbox/system

## 8.4 What graph is for

Graph is useful for:

- context recall
- cluster discovery
- orphan detection
- decision traceability
- stakeholder relationship mapping
- cross-topic exploration

## 8.5 What graph is not for

Graph is **not**:

- a reporting layer
- a replacement for Bases
- proof that the system is good just because it looks impressive

A beautiful graph with low-quality linking is still low-quality knowledge.

---

## 9. Bases strategy

Bases should be treated as the operational control surface.

### Main use cases

- active projects
- recent meetings
- decision backlog
- people / stakeholder notes
- inbox to process
- stale notes due for review

### Recommended dashboard role

Use Bases in `00 Home` to surface:

- active work
- recent work
- pending work
- review-needed work

### Key principle

**Bases = operating cockpit**  
**Graph = exploration layer**

---

## 10. Daily usage model

## 10.1 Morning routine

Open `00 Home` and review:

- active projects
- recent meetings
- pending decisions
- inbox to process

This should be driven by Bases.

## 10.2 During work

For the active note, keep visible:

- Properties panel
- Local Graph
- Smart Connections / semantic suggestions

Operational habit:

- add 1–3 meaningful links when needed
- fix missing metadata only if useful
- use AI suggestions as prompts, not as truth

## 10.3 After meetings

- process Meetily output
- create concise curated meeting note
- link to project and people
- create decision note when there is a durable decision

## 10.4 Weekly review

- inspect the global graph briefly
- identify lonely notes and overloaded clusters
- use Bases to correct metadata and review active items
- use OpenBrain to surface repeated themes and possible missing links

---

## 11. OpenBrain role in this setup

## 11.1 Strong use cases

OpenBrain should be used for:

- semantic retrieval over meetings and research
- similar-meeting detection
- repeated-theme detection
- contradiction flags
- stale-note detection
- candidate related-note suggestions
- draft syntheses for executive notes
- agent memory across sessions and workflows

## 11.2 What OpenBrain should not own

OpenBrain should **not** be the source of truth for:

- final decision records
- approved project notes
- autonomous vault restructuring
- mass auto-linking
- rewriting curated content without review

## 11.3 Best role definition

**OpenBrain helps think and recall.**  
**Obsidian stores what is approved, durable, and operationally useful.**

---

## 12. Suggested automation scope

## 12.1 Good automation

Recommended:

- raw ingest into OpenBrain
- extraction from Meetily JSON
- similar-note suggestions
- contradiction checks
- repeated-theme detection
- stale-note flags
- candidate synthesis drafts
- weekly heartbeat review jobs

## 12.2 Bad automation

Avoid:

- automatic rewriting of curated notes
- automatic restructuring of folders
- automatic global relinking
- automatic deletion
- full autonomous knowledge refactoring

The right model is **assistive**, not **autonomous**.

---

## 13. Fancy map of connections: real value

A strong map of connections is useful only if it is part of a working rhythm.

## 13.1 What the map gives in practice

- faster context recall
- easier discovery of missing links
- better visibility of decision chains
- better understanding of stakeholder and project clusters
- easier navigation across related notes

## 13.2 What it does not give

- it does not replace thinking
- it does not automatically create knowledge quality
- it does not replace dashboards or reviews

## 13.3 Real daily value

The graph becomes useful when it is used as:

- **global radar** once a week
- **local context map** during daily work

That is the practical model.

---

## 14. Article and concept takeaways incorporated into this architecture

## 14.1 Karpathy LLM Wiki

Useful idea adopted:

- raw sources separate from generated wiki
- outputs should compound into durable knowledge

Adaptation here:

- raw sources -> OpenBrain
- curated knowledge -> Obsidian
- no full autonomous wiki generation

## 14.2 MindStudio / Claude Code architecture

Useful ideas adopted:

- memory layers
- heartbeat / reflection cycles
- modular skills

Adaptation here:

- heartbeat belongs in OpenBrain workflows
- Claude-Code-like orchestration is optional, not the main owner of the system

## 14.3 Obsidian-specific conclusion

Most practical stack:

- Properties + Bases for structure and operations
- Graph for exploration
- Smart Connections for semantic prompts
- small plugin surface
- no over-automation

---

## 15. Recommended implementation direction

## 15.1 Version 1 goals

Build a usable first version with:

- note-type-first model
- light metadata
- curated meeting notes from Meetily
- OpenBrain as memory layer
- Obsidian as curated cockpit
- graph grouped by note type
- Bases-driven home dashboard

## 15.2 Version 1 should not include

- rigid area taxonomy
- deep ontology
- fully autonomous note writing
- giant plugin ecosystem
- full bidirectional AI editing of curated notes

---

## 16. Final recommendation

### Recommended final architecture

- **Meetily** = meeting evidence layer
- **OpenBrain** = memory, retrieval, heartbeat, suggestion layer
- **Obsidian** = curated source of truth for what matters operationally

### Final recommendation sentence

**Use Meetily to capture, OpenBrain to remember and suggest, and Obsidian to keep only what is important enough to review, link, and act on.**

---

## 17. Suggested OpenBrain entry metadata

If this document is stored in OpenBrain, recommended metadata:

- **domain:** build
- **entity_type:** Architecture
- **title:** AI Second Brain Architecture - Obsidian + OpenBrain + Meetily
- **tags:**
  - second-brain
  - obsidian
  - openbrain
  - meetily
  - architecture
  - knowledge-management
  - meeting-intelligence
  - executive-workflow
- **sensitivity:** internal
- **owner:** Gniewko
- **match_key:** gniewko-second-brain-architecture-v1

---

## 18. Suggested follow-up documents

Next useful companion docs would be:

1. **Operating Model**
   - daily routine
   - weekly review
   - meeting processing rules

2. **Metadata & Note Template Spec**
   - exact YAML/frontmatter
   - note templates
   - naming conventions

3. **OpenBrain Agent Skills Spec**
   - meeting extractor
   - related-note suggester
   - contradiction checker
   - weekly heartbeat

4. **Graph and Bases Config Guide**
   - graph grouping rules
   - dashboard views
   - home cockpit layout



---

## 19. RAW-first processing extension

An additional design principle adopted from modern AI second-brain workflows is the **RAW-first processing model**.

### Principle
The model should ingest and process **RAW source files first**, instead of writing directly into curated notes.

Preferred flow:

```text
RAW sources
→ OpenBrain / processing layer
→ review and promotion
→ curated Obsidian note
```

### Example RAW inputs
- Meetily JSON
- full transcripts
- PDFs
- web clips
- vendor documents
- rough research dumps

### What the processing layer should do
1. extract decisions, actions, risks, people, projects, and recurring themes
2. classify the candidate output
3. propose likely links to existing notes
4. recommend one of: promote / keep_raw / needs_review / discard

### Promotion logic
Only promote into curated Obsidian when the source contains:
- a durable decision
- a meaningful follow-up
- a reusable insight
- a valuable project update
- a high-value reference

Everything else should remain in RAW memory.

### Why this matters
This pattern keeps OpenBrain useful as a processing and retrieval layer while preserving Obsidian as a clean, high-trust, approved knowledge base.

### Meetily application
This is the strongest first use case:

```text
Meetily JSON
→ OpenBrain ingest
→ extraction agent
→ meeting candidate
→ review
→ curated meeting note
→ optional decision note
```

### Architectural conclusion
The target system is not an autonomous note app.

It is a **RAW evidence in → agent extraction → curated memory out** pipeline.
