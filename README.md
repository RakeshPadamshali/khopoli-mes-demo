# Khopoli NextGen MES — product demo (static)

Clickable, self-contained demo for the **JSW Steel Coated Products — Khopoli** RFP (One MES Coated Products template), built to walk the Annexure A scenarios on one common dataset:

| Scenario | Where in the demo |
|---|---|
| **S1 Golden Thread: order → dispatch (mandatory)** | Sales Orders & TDC → Routes & Schedules → Material Allocator → Shop-floor Execution (PDI/PDO) → Quality (zinc band, DFT) → Slitting · Packing · Dispatch → Genealogy |
| **S2 Planning & batch allocation** | Routes & Schedules (leftover-order feed → clubbing proposals → multi-slit plan, APS rush re-sequencing, reroute to the alternate line → rework production order generated automatically) · Material Allocator (batch swap, BTA/BTP) |
| S3 partial — delays, mass balance | Shop-floor Execution (stoppage with delay + equipment defect codes, OEE, imbalance flag) |
| **S4 Quality, defect propagation, ontology** | Quality & Defects · Genealogy · Digital Thread (propagation, Defect → Equipment → Line → Plant, triples) |
| **S5 Integration resilience** | Integration Monitor (stuck PDI queue, malformed IDoc, detect → alert → replay, contract versions) |
| S6 Dashboards | Plant Dashboard (live board, OEE / yield / OTIF / delay categories) |
| **S7 AI-agent support (mandatory)** | Data feed only — AI Support Data page + `data/json/`; the chatbot is a separate deliverable |
| S8 partial — master data | Master Data: 26 masters (lines, work centres, equipment, product definitions, specs, QC characteristics, compatibility, rate chart, codes, batch numbering, SAP–MES / MES–L2 mappings, consumables, shifts, roles, users) with Excel template download, upload with validation, preview and audit |

Everything is fictional (customers, orders, coils, people, incidents). Line names, products, rules and the ontology come from the RFP.

## Run

```
python serve.py            # http://localhost:8080/
```
or any static server (`python -m http.server 8080`). Open `index.html` for the tab host; each module also works standalone (`orders.html`, `execution.html`, …). Works offline — fonts and icons are vendored under `assets/vendor/`.

Live-demo actions (charge, receive PDO, confirm, record DFT, allocate, replay, dispatch …) are kept in the browser's localStorage so they stay consistent across pages; **Reset demo** in the header clears them.

## Data

- `data/khp-data.js` — one object `window.KHP` used by the pages.
- `data/json/<entity>.json` + `data/README.md` — the same data per entity with a data dictionary, for the AI-support chatbot team.
- `tools/generate_data.py` — deterministic generator (seed 2609). Edit the generator, never the outputs. `python tools/generate_data.py` rewrites both.
- **Dates follow the as-of day, which defaults to today.** Run the generator (and push) before a demo so the schedule, delays, alerts and incidents sit around the current date; ids and the story do not change within a month. Pin a date with `python tools/generate_data.py --asof 2026-09-15`. `data/khp-meta.js` carries the as-of stamp for the header.

Golden-thread anchors: SO **4213090017/10** (PPGI, RAL 9002), HR coil **HRC-VJ-2608-0471** (Vijayanagar heat H26-VJ-7731), defects DEF-2609-0001/0002/0003, incidents INC-26-0412 (resolved by the agent) and INC-26-0413 (awaiting approval).

The line schedules carry a **forward line-load plan** (`campaigns`): the balance-to-produce of every open order as ~20 t campaign coils sequenced per line over a 10-day horizon (campaign family, changeover minutes, transfer times, WIP), around the recorded coils. Routes & Schedules shows the full line load and the selected order's own schedule as two gantts; the dashboard's on-track / behind counts include the campaign coils.

More than one order runs through the live flows: every running line carries a different sales order, and four finished coils wait in the FG yard (two colour-coated coils with a pending lab result, one galvanized coil, plus the hero coil), so the Quality → Packing → Dispatch steps of Scenario 1 can be repeated on a second order. The certificate selector on Quality and the coil selector on Packing pick the coil.

## Presenter scripts

`docs/scenario-1-demo-script.html` and `docs/scenario-2-demo-script.html` are the step-by-step presenter scripts (Annexure A steps → page, click, what to say). They are rendered to PDF in the hand-off folder.

## Verify

```
python tools/verify.py     # headless Chrome (Playwright): zero JS errors, no missing assets, screenshot per page
```

## Layout

```
index.html                tab host (sidebar, tabs, reset)
home / orders / planning / allocation / execution / packing / quality / genealogy / integration / support .html
assets/khp-shell.css      shared shell styles
assets/khp-core.js        lookups, genealogy traversal, gantt, badges, demo state
assets/khp-chrome.js      standalone header + sidebar (hidden when embedded)
assets/khp-embed.js       iframe shim: routes links to host tabs
assets/vendor/            Roboto, Font Awesome, ECharts (offline)
data/                     generated dataset (JS + JSON + dictionary)
tools/                    generator package + verifier
```
