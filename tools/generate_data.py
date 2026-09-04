#!/usr/bin/env python3
"""Deterministic demo dataset for the JSW Khopoli NextGen MES product demo (RFP Annexure A scenarios 1, 2-light, 4, 5, 6 + data feed for 7).
Writes  data/khp-data.js  (window.KHP, used by the pages)  and  data/json/<entity>.json + data/README.md  (for the AI-support team).
Everything is fictional: customers, orders, coils, people, incidents. Only line names, products, rules and the ontology come from the RFP.
Run:  python tools/generate_data.py
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime
from gen.common import ASOF, BASE, iso
from gen import assets_specs as A
from gen.orders import build_orders, HERO_ITEM, HERO_SO, RUSH_ITEM, SWAP_A, SWAP_B, AMEND_ITEM, DOWNGRADE_SO_ITEM
from gen.threads import build_threads, build_free_stock
from gen.execution import build_execution, sap_dispatch_message
from gen.quality import build_quality
from gen.ops import build_delays, build_kpis, live_snapshot
from gen.integration import build_interfaces, build_messages, build_contracts
from gen.support import build_support

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JS, OUT_JSON, OUT_MD = os.path.join(ROOT, "data", "khp-data.js"), os.path.join(ROOT, "data", "json"), os.path.join(ROOT, "data", "README.md")

orders, items, tdcs, routes = build_orders()
T = build_threads(items, routes)
free, sugg = build_free_stock(items)
hero = next(t for t in T["threads"] if t["hero"])
E = build_execution(T["stages"], T["materials"], items, T["threads"])
Q = build_quality(T["materials"], T["stages"], items, T["edges"], hero)
delays = build_delays()
kpis = build_kpis(delays, E["confirmations"])
live = live_snapshot(T["schedules"], delays, sum(1 for x in Q["holds"] if x["status"] == "ACTIVE"), kpis)
interfaces = build_interfaces()
messages, alerts = build_messages(E["pdi"], E["pdo"], E["confirmations"], E["dispatches"], items)
contracts = build_contracts()
S = build_support(alerts)
mats = {u["id"]: u for u in T["materials"]}; by_item = {it["id"]: it for it in items}

# ---- events: rush re-prioritisation (S2-light), batch swap (S2-light), SO amendment (S5) ----
cgl = sorted([s for s in T["schedules"] if s["line"] == "CGL" and s["status"] == "PLANNED"], key=lambda s: s["plannedStart"])
ri = next((i for i, s in enumerate(cgl) if s["itemId"] == RUSH_ITEM), None)
rush_event = None
if ri is not None:
    slots = [(s["plannedStart"], s["plannedEnd"]) for s in cgl]
    before_order = cgl[:ri] + cgl[ri + 1:]; before_order.insert(min(ri + 2, len(before_order)), cgl[ri])   # where it sat before the flag
    rush_event = dict(at="2026-09-14T09:00:00", source="IF-APS-RUSH", itemId=RUSH_ITEM, soId=RUSH_ITEM.split("/")[0], line="CGL", reason="APS rush flag — customer line stoppage at Chakan",
                      before=[dict(seq=i + 1, id=s["id"], unitId=s["unitId"], soId=s["soId"], customerName=s["customerName"], plannedStart=slots[i][0], plannedEnd=slots[i][1], rush=s["itemId"] == RUSH_ITEM) for i, s in enumerate(before_order)],
                      after=[dict(seq=i + 1, id=s["id"], unitId=s["unitId"], soId=s["soId"], customerName=s["customerName"], plannedStart=slots[i][0], plannedEnd=slots[i][1], rush=s["itemId"] == RUSH_ITEM) for i, s in enumerate(cgl)],
                      movedUpBy=2)
    for s in cgl:
        if s["itemId"] == RUSH_ITEM: s["rushAppliedAt"] = "2026-09-14T09:00:00"; s["originalStart"] = slots[min(ri + 2, len(cgl) - 1)][0]
ua = next((u for u in T["materials"] if u.get("allocatedTo") == SWAP_A and u["product"] == "GI"), None)
ub = next((u for u in T["materials"] if u.get("allocatedTo") == SWAP_B and u["product"] == "GI"), None)
swap_event = None
if ua and ub:
    def bt(it_id, before=True):
        it = by_item[it_id]; alloc = sum(u["weightMT"] for u in T["materials"] if u["product"] == "GI" and u.get("allocatedTo") == it_id)
        return dict(itemId=it_id, qtyMT=it["qtyMT"], allocatedMT=round(alloc, 2), btaMT=round(it["qtyMT"] - alloc, 2))
    before = [bt(SWAP_A), bt(SWAP_B)]
    for u, new, old in ((ua, SWAP_B, SWAP_A), (ub, SWAP_A, SWAP_B)):
        u["allocatedTo"] = new; u["swapped"] = dict(at="2026-09-13T15:20:00", fromItem=old, toItem=new, by="PPC — A. Bhosale", reason="Earlier RDD on " + new + "; identical spec (DX51D+Z 0.80×1250 Z120)")
        T["edges"] = [e for e in T["edges"] if not (e[0] == "allocatedTo" and e[1] == u["id"])] + [("allocatedTo", u["id"], new)]
        T["allocations"].append(dict(id=f"ALC-SW-{u['id'][-4:]}", unitId=u["id"], itemId=new, previousItemId=old, at="2026-09-13T15:20:00", by="PPC — A. Bhosale", ppcApproval="APPROVED", qcApproval="APPROVED", status="ACTIVE", reason="Batch swap between sales orders"))
    swap_event = dict(at="2026-09-13T15:20:00", unitA=ua["id"], unitB=ub["id"], itemA=SWAP_A, itemB=SWAP_B, by="PPC — A. Bhosale", reason="SO " + SWAP_B + " has the earlier RDD (16 Sep); both coils meet the identical TDC",
                      btaBefore=before, btaAfter=[bt(SWAP_A), bt(SWAP_B)], sapMessage="IF-SAP-15 batch reallocation sent 15:21 (OK)")
amend = next(o for o in orders if o["id"] == AMEND_ITEM.split("/")[0])["amendment"]
events = dict(rush=rush_event, swap=swap_event, amendment=dict(itemId=AMEND_ITEM, **amend, idoc="0000001187734", alertId="ALR-0002", incidentId="INC-26-0413"))

# ---- per-item roll-up: allocated / produced / dispatched, BTA / BTP, status ----
disp_by_item = {}
for d in E["dispatches"]:
    if d["status"] == "DISPATCHED": disp_by_item[d["itemId"]] = disp_by_item.get(d["itemId"], 0) + d["weightMT"]
for it in items:
    hr = [u for u in T["materials"] if u["product"] == "HRC" and u.get("allocatedTo") == it["id"]]
    fg = [u for u in T["materials"] if u.get("allocatedTo") == it["id"] and u["product"] == it["product"] and u.get("producedAt")]
    it["allocatedMT"] = round(sum(u["weightMT"] for u in hr), 2); it["producedMT"] = round(sum(u["weightMT"] for u in fg), 2); it["dispatchedMT"] = round(disp_by_item.get(it["id"], 0), 2)
    if it["dispatchedMT"] > 0 and it["qtyMT"] <= 60 and not it["id"] in (HERO_ITEM, RUSH_ITEM, SWAP_A, SWAP_B, AMEND_ITEM, DOWNGRADE_SO_ITEM):
        it["qtyMT"] = round(it["dispatchedMT"]); it["scheduleLines"] = [dict(id=it["id"] + "/0001", qtyMT=it["qtyMT"], date=it["scheduleLines"][0]["date"], status="DELIVERED")]   # single-coil orders fully served
    it["btaMT"] = round(max(0, it["qtyMT"] - it["allocatedMT"]), 2); it["btpMT"] = round(max(0, it["qtyMT"] - it["producedMT"]), 2)
    it["status"] = "DISPATCHED" if it["dispatchedMT"] >= it["qtyMT"] * 0.98 else "PARTIALLY_DISPATCHED" if it["dispatchedMT"] > 0 else "IN_PROGRESS" if it["allocatedMT"] > 0 else "OPEN"
    it["hero"] = it["id"] == HERO_ITEM
for o in orders:
    its = [it for it in items if it["soId"] == o["id"]]; o["items"] = [it["id"] for it in its]; o["qtyMT"] = sum(it["qtyMT"] for it in its)
    o["status"] = "DISPATCHED" if all(it["status"] == "DISPATCHED" for it in its) else "IN_PROGRESS" if any(it["status"] != "OPEN" for it in its) else "OPEN"; o["hero"] = o["id"] == HERO_SO
hero_disp = next(d for d in E["dispatches"] if d["hero"]); hero_pack = next(p for p in E["packs"] if p["id"] == hero_disp["packId"])
dispatch_message = sap_dispatch_message(hero_disp, hero_pack, by_item[HERO_ITEM])

# ---- validation ----
def uniq(name, rows):
    ids = [r["id"] for r in rows]; assert len(ids) == len(set(ids)), f"duplicate ids in {name}"
for name, rows in (("materials", T["materials"]), ("stages", T["stages"]), ("productionOrders", T["productionOrders"]), ("pdi", E["pdi"]), ("pdo", E["pdo"]), ("confirmations", E["confirmations"]),
                   ("defects", Q["defects"]), ("messages", messages), ("incidents", S["incidents"]), ("items", items), ("orders", orders), ("packs", E["packs"]), ("dispatches", E["dispatches"])):
    uniq(name, rows)
eq_ids = {e["id"] for e in A.equipment_rows()} | {l["id"] for l in A.LINES}
for rel, a, b in T["edges"]:
    if rel == "consumesInput": assert a in mats and b in mats, f"dangling consumesInput {a}->{b}"
for d in Q["defects"]:
    assert d["detectedOn"] in mats, d["id"]; assert d["attributedTo"] in eq_ids, f"{d['id']} attributedTo {d['attributedTo']}"
for s in T["schedules"]: assert s["unitId"] in mats, s["id"]
assert all(x["itemId"] in by_item for x in T["allocations"])
free_ids = {u["id"] for u in free}
assert all(x["unitId"] in free_ids for x in sugg)

KHP = dict(meta=dict(plant="JSW Steel Coated Products — Khopoli", title="Khopoli NextGen MES — One MES Coated Products template (product demo)", baseDate=iso(BASE), asOf=iso(ASOF), generated="deterministic (seed 2609)",
                     fictional=True, hero=dict(soId=HERO_SO, itemId=HERO_ITEM, hrCoilId=hero["hrCoilId"], threadId=hero["id"], units=hero["units"], downgradeCandidateItem=DOWNGRADE_SO_ITEM, rushItem=RUSH_ITEM, swapItems=[SWAP_A, SWAP_B], amendedItem=AMEND_ITEM)),
           ontology=dict(domains=["ASSETS", "MATERIAL", "SPECIFICATION", "QUALITY", "PROCESS", "COMMERCIAL & PLANNING"],
                         relationships=dict(consumesInput="material → material it was made from (genealogy spine)", producedOn="material → line / equipment", conformsTo="material → TDC / specification", hasCoatingSpec="material → coating spec",
                                            detectedOn="defect → material", attributedTo="defect → causing equipment", allocatedTo="material → sales-order item", fulfils="dispatch → sales-order schedule line")),
           plant=A.PLANT, lines=A.LINES, equipment=A.equipment_rows(), grades=A.GRADES, coatings=A.COATINGS, paints=A.PAINTS, rals=[dict(code=c, name=n) for c, n in A.RALS], defectCodes=A.DEFECT_CODES, delayCodes=A.DELAY_CODES,
           customers=A.CUSTOMERS, packVendors=A.PACK_VENDORS, shifts=A.SHIFTS, orders=orders, items=items, tdcs=tdcs, routes=routes, threads=T["threads"], materials=T["materials"],
           edges=[dict(rel=r, **{"from": a, "to": b}) for r, a, b in T["edges"]], stages=T["stages"], productionOrders=T["productionOrders"], allocations=T["allocations"], schedules=T["schedules"], freeStock=free, maSuggestions=sugg,
           pdi=E["pdi"], pdo=E["pdo"], confirmations=E["confirmations"], slitPlans=E["slitPlans"], packs=E["packs"], packingBills=E["packingBills"], dispatches=E["dispatches"], dispatchMessage=dispatch_message,
           defects=Q["defects"], decisions=Q["decisions"], downgradeSuggestions=Q["downgradeSuggestions"], certificates=Q["certificates"], holds=Q["holds"], delays=delays, kpis=kpis, live=live,
           interfaces=interfaces, messages=messages, alerts=alerts, contracts=contracts, incidents=S["incidents"], runbooks=S["runbooks"], actionCatalogue=S["actionCatalogue"], agentAudit=S["agentAudit"], supportMetrics=S["supportMetrics"], events=events)

DESC = {"plant": "The Khopoli plant and its upstream HSM plants (ASSETS).", "lines": "Manufacturing lines in scope incl. upcoming lines (status PLANNED = configuration-only onboarding).", "equipment": "Equipment per line; defects are attributedTo these ids. Includes upstream HSM equipment for cross-plant root cause.",
        "grades": "Steel grades with mechanical ranges (SPECIFICATION).", "coatings": "Zinc / aluzinc coating specs: nominal GSM, CGL target and allowed band.", "paints": "Paint systems with DFT targets and tolerances (CCL).", "rals": "RAL colour codes used on orders.",
        "defectCodes": "Line-wise defect taxonomy (QUALITY) with the typical causing equipment.", "delayCodes": "Delay reason codes and categories.", "customers": "Fictional customers and segments.", "packVendors": "Packing vendors with rates per tonne (domestic / export).", "shifts": "Shift calendar A/B/C.",
        "orders": "SAP sales orders (header) with route source, rush flag and the scripted amendment.", "items": "Sales-order items with TDC parameters, schedule lines, roll-ups (allocated / produced / dispatched, BTA / BTP).", "tdcs": "Technical Delivery Conditions per item (variant-configuration characteristics).",
        "routes": "SAP route vs Factory-Planner route per item: process path, yield string, route string, material tree, chosen source.", "threads": "One coil 'thread' = the digital thread of one HR coil through its route (MATERIAL spine).",
        "materials": "Every material unit: HR coils, HRPO, CRFH, GI/GL, PPGI/PPGL, slit children, packs — with attributes, status, genealogy keys (parentId, hrCoilId, heatId, slabId).", "edges": "Ontology relationships as triples (rel, from, to).",
        "stages": "Simulated line stages per thread (planned/actual times, in/out weights, PDI/PDO refs).", "productionOrders": "MES production order numbers per stage (PROCESS).", "allocations": "Batch → sales-order allocations incl. the scripted swap (BatchOrderAllocation).",
        "schedules": "Line schedules (campaign sequence per line) with status vs as-of and rush markers.", "freeStock": "Free HR coils in the yard (+ on hold, in transit) available to the Material Allocator.", "maSuggestions": "Material-Allocator suggestions per open item with score, reasons and the two-step PPC / QC approvals.",
        "pdi": "Production Data Input messages MES → L2 (targets); includes the stuck queue messages.", "pdo": "Production Data Output messages L2 → MES (actuals) with auto-comparison deviations.", "confirmations": "Production confirmations with mass balance (one deliberate IMBALANCE).",
        "slitPlans": "Slitting plans parent → children.", "packs": "Packing units with vendor, materials and QR label.", "packingBills": "Vendor-wise packing bills per ISO week.", "dispatches": "Dispatches (done / planned) with vehicle and invoice.", "dispatchMessage": "Structure of the dispatch confirmation sent to SAP for the hero order.",
        "defects": "Defects: detectedOn material, attributedTo equipment, downstreamAffected (propagation via consumesInput).", "decisions": "Usage decisions (UD codes) per finished unit.", "downgradeSuggestions": "Auto downgrade suggestions with param-by-param validation against candidate sales orders and manual override.",
        "certificates": "Test certificates (EN 10204 3.1) incl. the DFT dispatch gate.", "holds": "Batch hold / release events with reasons.", "delays": "Line stoppages with delay code, equipment defect, capture mode; two ACTIVE now.", "kpis": "Daily OEE per line (availability × performance × quality), production vs target, prime yield.",
        "live": "Real-time shop-floor snapshot as of now: line states, rates, next batches, on-track / behind, active delays, holds, OTIF.", "interfaces": "Interface catalogue: 34 SAP + 6 L2 + APS/Anaplan/utilities/SIS with protocol, trigger, contract, version, SLA.",
        "messages": "48-hour middleware message log with statuses OK / FAILED / IN_QUEUE / REPLAYED, errors and history (scripted: stuck PDI queue, malformed ORDERS05 IDoc, PDO contract mismatch).", "alerts": "Monitoring alerts raised to operators, linked to messages and incidents.",
        "contracts": "Interface contracts / schemas with field definitions and version history.", "incidents": "ITSM incidents (30 days) with AI-agent classification, enrichment, knowledge source, proposed action, approval, resolution, MTTR.", "runbooks": "Runbooks / known-error records the agent cites.",
        "actionCatalogue": "AI-agent action catalogue: AUTONOMOUS / APPROVAL / PROHIBITED.", "agentAudit": "Immutable audit log of the hero incident (INC-26-0412).", "supportMetrics": "MI dashboard numbers: agent vs human resolution, MTTR by severity, false-action rate, coverage, weekly trend.",
        "events": "Scripted scenario events: APS rush re-prioritisation (before/after CGL sequence), batch swap (BTA before/after), SAP order amendment (failed IDoc)."}


def write():
    os.makedirs(OUT_JSON, exist_ok=True)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("/* JSW Khopoli NextGen MES demo — GENERATED by tools/generate_data.py (seed 2609). Fictional data. Do not hand-edit. */\nwindow.KHP = ")
        json.dump(KHP, f, ensure_ascii=False, separators=(",", ":")); f.write(";\n")
    for k, v in KHP.items():
        with open(os.path.join(OUT_JSON, f"{k}.json"), "w", encoding="utf-8") as f: json.dump(v, f, ensure_ascii=False, indent=1)
    lines = ["# Khopoli NextGen MES — demo dataset (data dictionary)", "",
             f"Generated by `tools/generate_data.py` (deterministic, seed 2609). As-of: **{iso(ASOF)}**. Plan window from {iso(BASE)[:10]}. All customers, orders, coils, people and incidents are **fictional**.",
             "Same identifiers are used by the demo pages (`data/khp-data.js`, one object `window.KHP`) and by these per-entity JSON files — so the AI-support chatbot and the UI talk about the same coil, order, message and incident ids.", "",
             "## Id conventions", "- Sales order `42130900nn`, item `42130900nn/10`, schedule line `42130900nn/10/0001`, TDC `TDC-42130900nn-10`, FP order `FPM-…`, MES production order `PO-KHP-2609-nnnn`.",
             "- Material units by product: `HRC-VJ|DL-2608-nnnn` (HR coil, source plant), `HPO-` (pickled), `CRF-` (full hard), `GIC-`/`GLC-` (galvanized / galvalume), `PPG-`/`PPL-` (colour coated), `SLC-` (slit child), `PK-` (pack). Suffix `-KHP-2609-` = plant + year/month batch identifier.",
             "- Transactions: `PDI-<line>-nnnn`, `PDO-<line>-nnnn`, `PC-<line>-nnnn` (confirmation), `DLY-`, `DEF-2609-`, `UD-`, `DGS-` (downgrade suggestion), `TC-<unit>` (certificate), `HLD-`, `SLP-`, `DSP-`, `PBILL-`.",
             "- Integration: interfaces `IF-SAP-nn` / `IF-L2-<type>` / `IF-APS-…`, messages `MSG-nnnnn`, alerts `ALR-nnnn`, contracts `CT-…`. Support: incidents `INC-26-nnnn`, runbooks `RB-nnn`, actions `A-nn`, audit `AUD-…`.", "",
             "## Ontology (RFP §5.7) — relationships in `edges.json`", "`consumesInput` (material → its input, the genealogy spine) · `producedOn` (material → line) · `conformsTo` (material → TDC) · `hasCoatingSpec` · `detectedOn` (defect → material) · `attributedTo` (defect → equipment) · `allocatedTo` (material → SO item) · `fulfils` (dispatch → schedule line).",
             "Traverse `consumesInput` backwards for genealogy to HR coil → slab → heat (fields `hrCoilId`, `slabId`, `heatId` on every unit), forwards for defect propagation (`defects[].downstreamAffected` is precomputed).", "",
             "## Golden-thread anchors (`meta.hero`)", f"- Hero order **{HERO_SO}/10** (Apex Appliances, PPGI DX51D+Z 0.50×1220 Z120, RMP RAL 9002, DFT 20 ±3 µm, slit 2×610). Hero HR coil **{hero['hrCoilId']}** (Vijayanagar heat H26-VJ-7731 / slab SLB-VJ-7731-02).",
             f"- Units of the hero thread: {', '.join(hero['units'])}.", f"- Downgrade candidate order {DOWNGRADE_SO_ITEM} (Sunbeam Panels, same spec with DFT 15 ±3). Rush order {RUSH_ITEM}. Batch swap {SWAP_A} ↔ {SWAP_B}. Amended order {AMEND_ITEM} (failed IDoc 0000001187734).",
             "- Scripted integration failures: stuck PDI queue `L2.CGL.PDI.OUT` (alert ALR-0001 → incident INC-26-0412, resolved by the agent with human-approved replay, audit in `agentAudit.json`); malformed ORDERS05 IDoc (ALR-0002 → INC-26-0413, awaiting SAP key-user approval — open for the live chatbot demo); PDO contract mismatch (ALR-0003 → INC-26-0409, resolved).", "",
             "## Files"]
    for k, v in KHP.items():
        n = len(v) if isinstance(v, list) else 1
        sample = v[0] if isinstance(v, list) and v else v if isinstance(v, dict) else None
        fields = ", ".join(f"`{f}`" for f in list(sample.keys())[:18]) if isinstance(sample, dict) else ""
        lines.append(f"### `{k}.json` — {n} record{'s' if n != 1 else ''}"); lines.append(DESC.get(k, "")); lines.append(f"Fields: {fields}" + (" …" if isinstance(sample, dict) and len(sample) > 18 else "")); lines.append("")
    with open(OUT_MD, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    print("written", OUT_JS, f"{os.path.getsize(OUT_JS) / 1024:.0f} KB;", len(KHP), "entities ->", OUT_JSON)
    for k, v in KHP.items():
        if isinstance(v, list): print(f"  {k:22s} {len(v):5d}")
    print("hero units:", hero["units"])


if __name__ == "__main__":
    write()
