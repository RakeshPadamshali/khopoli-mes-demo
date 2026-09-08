"""MATERIAL + PROCESS: simulate coil 'threads' HR coil -> ... -> pack through the line routes (the digital thread),
line schedules, MES production orders, allocations (BTA/BTP), free HR stock and Material-Allocator suggestions."""
from datetime import datetime, timedelta
from .common import R, BASE, ASOF, iso, day, h, pick, between, r1, r2, status_vs_asof, SEQ, at as AT, YM, YM_PREV
from .assets_specs import LINES, COATINGS
from .orders import HERO_ITEM, RUSH_ITEM, SWAP_A, SWAP_B, YIELDS

LINE = {l["id"]: l for l in LINES}
PREFIX = {"HRC": "HRC", "HRPO": "HPO", "CRFH": "CRF", "GI": "GIC", "GL": "GLC", "PPGI": "PPG", "PPGL": "PPL", "SLIT": "SLC", "TRIMMED": "TRC", "PACK": "PK"}
HR_GRADE = {"DX51D+Z": "JSW-HR-DD", "DX53D+Z": "JSW-HR-DD", "SGCC": "JSW-HR-CQ", "CQ-IS277": "JSW-HR-CQ", "SGLCC": "JSW-HR-CQ", "S350GD+Z": "JSW-HR-HS",
            "CR4-CRFH": "JSW-HR-CQ", "HRPO-E250": "JSW-HR-E250"}
busy = {l["id"]: [] for l in LINES}   # per-line busy intervals


def _slot(line, ready, dur):
    """earliest start >= ready on a single-capacity line, skipping busy intervals"""
    s = ready
    while True:
        e = s + dur; clash = None
        for a, b in busy[line]:
            if s < b and e > a: clash = b; break
        if clash is None:
            busy[line].append((s, e)); return s, e
        s = clash + h(0.15)


def _unit_id(product, src=None):
    n = SEQ.next("unit-" + product)
    return f"{PREFIX[product]}-{src or 'KHP'}-{YM}-{n:04d}"


def _hr_coil(it, src=None, thk=None):
    src = src or pick(["VJ", "VJ", "VJ", "DL"]); plant = "VJNR" if src == "VJ" else "DLV"
    heat = f"H26-{src}-{R.randint(7100, 7900)}"; slab = f"SLB-{heat[4:]}-{R.randint(1, 4):02d}"
    if thk is None:
        thk = it["thk"] if it["product"] == "HRPO" else r1(it["thk"] * between(3.6, 6.2))
        thk = max(1.8, min(4.0, thk))
    width = it["width"] + pick([20, 30, 40, 60])
    return dict(id=_unit_id("HRC", src), product="HRC", gradeId=HR_GRADE.get(it["gradeId"], "JSW-HR-CQ"), thk=thk, width=width,
                weightMT=r2(between(18, 24)), heatId=heat, slabId=slab, sourcePlant=plant, hsmLine=f"{plant}-HSM",
                receivedAt=iso(BASE - timedelta(days=R.randint(2, 30), hours=R.randint(0, 23))), location=f"HR Yard bay {pick('ABCD')}-{R.randint(1, 12):02d}",
                status="AVAILABLE", ontologyDomain="MATERIAL", stage="HRC")


def build_threads(items, routes):
    materials, edges, stages, pos, allocations, schedules = [], [], [], [], [], []
    route_of = {r["itemId"]: r for r in routes}
    threads = []
    # pick items that get physical threads (some items get 1-3 coils depending on qty)
    scripted = {RUSH_ITEM: AT(-2, 14, 0), SWAP_A: AT(-10, 8, 0), SWAP_B: AT(-9, 10, 0)}
    cand = [it for it in items if it["id"] not in (HERO_ITEM,) and it["id"] not in scripted]
    R.shuffle(cand)
    plan = [(HERO_ITEM, AT(-7, 14, 0), True)] + [(k, v, False) for k, v in scripted.items()]
    starts = [BASE - timedelta(days=5) + timedelta(hours=x * 20) for x in range(48)]   # ~5 Aug-27 .. ~21 Sep: done / in-progress / planned mix
    for k, it in enumerate(cand[:31]):
        plan.append((it["id"], starts[k] + timedelta(minutes=R.randint(0, 300)), False))
    plan.sort(key=lambda x: x[1])
    for tid_n, (item_id, t0, hero) in enumerate(plan, 1):
        it = next(x for x in items if x["id"] == item_id); rt = route_of[item_id]
        th = dict(id=f"TH-{tid_n:03d}", itemId=item_id, soId=it["soId"], product=it["product"], hero=hero, path=rt["path"], units=[])
        hr = _hr_coil(it, src="VJ" if hero else None, thk=(2.5 if hero else None))
        if hero: hr.update(id=f"HRC-VJ-{YM_PREV}-0471", heatId="H26-VJ-7731", slabId="SLB-VJ-7731-02", weightMT=21.4, width=1250, location="HR Yard bay B-07", receivedAt=iso(AT(-18, 16, 20)))
        hr["allocatedTo"] = item_id; hr["allocatedAt"] = iso(t0 - h(between(6, 30))); hr["status"] = "ALLOCATED"
        materials.append(hr); edges.append(("allocatedTo", hr["id"], item_id)); th["units"].append(hr["id"])
        allocations.append(dict(id=f"ALC-{SEQ.next('alc'):04d}", unitId=hr["id"], itemId=item_id, at=hr["allocatedAt"], by="Material Allocator" if R.random() < 0.7 else "PPC (manual)",
                                ppcApproval="APPROVED", qcApproval="APPROVED", status="ACTIVE", reason="MA suggestion accepted" if hero else pick(["MA suggestion accepted", "Free-stock reallocation by priority", "Manual allocation"])))
        cur_unit, cur_w, ready = hr, hr["weightMT"], t0
        hero_times = {"PKL": (AT(-6, 6, 40), AT(-6, 7, 25)), "CRM": (AT(-5, 14, 10), AT(-5, 15, 5)),
                      "CGL": (AT(-3, 9, 30), AT(-3, 10, 40)), "CCL": (AT(-1, 22, 10), AT(0, 1, 40)),
                      "SLT": (AT(1, 8, 0), AT(1, 8, 50)), "PKG": (AT(1, 13, 0), AT(1, 13, 40))}
        for si, ln in enumerate(th["path"]):
            dur = h(cur_w / LINE[ln]["tph"] + between(0.25, 0.5))
            if hero:
                s, e = hero_times[ln]; busy[ln].append((s, e))
            else:
                s, e = _slot(ln, ready + h(between(3, 26)), dur)
            st = status_vs_asof(s, e)
            out_prod = {"PKL": "HRPO", "CRM": "CRFH", "CGL": it["product"] if it["product"] in ("GI", "GL") else ("GL" if it["product"] == "PPGL" else "GI"),
                        "CCL": it["product"], "SLT": "SLIT", "RWL": "TRIMMED", "PKG": "PACK", "HRS": "HRC"}[ln]
            po = f"PO-KHP-{YM}-{SEQ.next('po'):04d}"
            yld = YIELDS[ln]; out_w = r2(cur_w * yld); scrap = r2(cur_w - out_w)
            stage = dict(id=f"STG-{th['id']}-{si + 1}", threadId=th["id"], itemId=item_id, soId=it["soId"], line=ln, seq=si + 1, po=po, inUnit=cur_unit["id"],
                         start=iso(s), end=iso(e), status=st, inWeight=cur_w, outWeight=out_w if st == "DONE" else None, scrap=scrap if st == "DONE" else None,
                         plannedOut=out_w, hero=hero, product=out_prod)
            pos.append(dict(id=po, itemId=item_id, soId=it["soId"], line=ln, unitIn=cur_unit["id"], plannedQtyMT=cur_w, plannedStart=iso(s), plannedEnd=iso(e),
                            status={"DONE": "CONFIRMED", "IN_PROGRESS": "IN_PROGRESS", "PLANNED": "RELEASED" if s < ASOF + h(48) else "PLANNED"}[st], source=rt["chosen"] + " route",
                            fpMfgOrder=rt["fpRoute"]["fpMfgOrder"] if rt["chosen"] == "FP" else None, ontologyDomain="PROCESS"))
            # output unit(s)
            outs = []
            if ln == "SLT":
                ws = it.get("slitWidths") or [(it["width"] - 20) // 2] * 2
                for wi, w in enumerate(ws):
                    u = dict(id=f"{_unit_id('SLIT')}", product="SLIT", parentProduct=cur_unit["product"], gradeId=it["gradeId"], thk=it["thk"], width=w,
                             weightMT=r2(out_w * w / sum(ws)), coatingId=it.get("coatingId"), paintId=it.get("paintId"), ral=it.get("ral"), slitIndex=wi + 1)
                    outs.append(u)
            else:
                thk = it["thk"] if ln in ("CRM", "CGL", "CCL") else (cur_unit["thk"] if ln in ("PKL", "HRS", "RWL", "PKG") else it["thk"])
                width = cur_unit["width"] - (10 if ln == "PKL" else 0) - (16 if ln == "RWL" else 0)
                if ln in ("CGL", "CCL", "PKG"): width = cur_unit["width"]
                u = dict(id=_unit_id(out_prod), product=out_prod, gradeId=it["gradeId"], thk=thk, width=width, weightMT=out_w,
                         coatingId=it.get("coatingId") if ln in ("CGL", "CCL", "PKG", "RWL") else None, paintId=it.get("paintId") if ln in ("CCL", "PKG") else None,
                         ral=it.get("ral") if ln in ("CCL", "PKG") else None)
                outs.append(u)
            for u in outs:
                u.update(stage=ln, producedOn=ln, po=po, producedAt=iso(e) if st == "DONE" else None, plannedAt=iso(e), allocatedTo=item_id, soId=it["soId"],
                         customerName=it["customerName"], heatId=hr["heatId"], slabId=hr["slabId"], hrCoilId=hr["id"], threadId=th["id"], ontologyDomain="MATERIAL",
                         status={"DONE": "AVAILABLE", "IN_PROGRESS": "IN_PROCESS", "PLANNED": "PLANNED"}[st], parentId=cur_unit["id"])
                edges.append(("consumesInput", u["id"], cur_unit["id"])); edges.append(("producedOn", u["id"], ln)); edges.append(("allocatedTo", u["id"], item_id))
                if u.get("coatingId"): edges.append(("hasCoatingSpec", u["id"], u["coatingId"]))
                edges.append(("conformsTo", u["id"], it["tdcId"]))
                materials.append(u); th["units"].append(u["id"])
            stage["outUnits"] = [u["id"] for u in outs]
            if st == "DONE":
                cur_unit["status"] = "CONSUMED"; cur_unit["consumedAt"] = iso(s); cur_unit["consumedOn"] = ln
            elif st == "IN_PROGRESS":
                cur_unit["status"] = "IN_PROCESS"; cur_unit["consumedOn"] = ln
            stages.append(stage)
            schedules.append(dict(id=f"SCH-{ln}-{SEQ.next('sch-' + ln):03d}", line=ln, threadId=th["id"], itemId=item_id, soId=it["soId"], customerName=it["customerName"],
                                  unitId=cur_unit["id"], po=po, product=out_prod, gradeId=it["gradeId"], thk=it["thk"], width=it["width"], ral=it.get("ral"), coatingId=it.get("coatingId"),
                                  plannedStart=iso(s), plannedEnd=iso(e), status=st, hero=hero, rush=(item_id == RUSH_ITEM), qtyMT=cur_w))
            if ln == "SLT":
                # slit children continue as a group; the pack stage consumes all of them (weight sum)
                cur_unit = dict(id=outs[0]["id"], product="SLIT", thk=it["thk"], width=it["width"], siblings=[u["id"] for u in outs]); cur_w = out_w
            else:
                cur_unit = outs[0]; cur_w = out_w
            ready = e
            if st != "DONE" and si < len(th["path"]) - 1:
                # remaining stages stay planned; keep simulating for schedule visibility
                pass
        th["hrCoilId"] = hr["id"]; th["stageDone"] = sum(1 for s in stages if s["threadId"] == th["id"] and s["status"] == "DONE")
        threads.append(th)
    _fix_pack_units(materials, stages)
    _make_in_progress(stages, schedules, pos, materials)
    return dict(threads=threads, materials=materials, edges=edges, stages=stages, productionOrders=pos, allocations=allocations, schedules=schedules)


def _make_in_progress(stages, schedules, pos, materials):
    """The as-of instant should catch a coil running on the L2 lines and packing: pull each line's next planned stage
    back so it straddles ASOF (CGL is mid-coil when its air-knife stoppage hits; SLT is between coils)."""
    by_id = {u["id"]: u for u in materials}; sch = {s["po"]: s for s in schedules}; po = {p["id"]: p for p in pos}
    for ln in ("PKL", "CRM", "CGL", "CCL", "PKG"):
        cand = sorted([s for s in stages if s["line"] == ln and s["status"] == "PLANNED" and not s["hero"] and s["itemId"] != RUSH_ITEM], key=lambda s: s["start"])
        if not cand: continue
        st = cand[0]; s0, e0 = datetime.fromisoformat(st["start"]), datetime.fromisoformat(st["end"]); dur = e0 - s0
        last_done = max([datetime.fromisoformat(x["end"]) for x in stages if x["line"] == ln and x["status"] == "DONE"] or [ASOF - h(3)])
        s = max(ASOF - dur * between(0.35, 0.7), last_done + h(0.1)); e = s + dur
        delta = e - e0
        st.update(start=iso(s), end=iso(e), status="IN_PROGRESS"); sch[st["po"]].update(plannedStart=iso(s), plannedEnd=iso(e), status="IN_PROGRESS"); po[st["po"]]["status"] = "IN_PROGRESS"
        inp = by_id.get(st["inUnit"])
        if inp: inp["status"] = "IN_PROCESS"; inp["consumedOn"] = ln
        for uid in st["outUnits"]:
            by_id[uid]["status"] = "IN_PROCESS"; by_id[uid]["plannedAt"] = iso(e)
        # keep the thread's later stages after this one
        for x in stages:
            if x["threadId"] == st["threadId"] and x["seq"] > st["seq"]:
                xs = datetime.fromisoformat(x["start"])
                if xs < e + h(2):
                    ns = e + h(between(3, 8)); ne = ns + (datetime.fromisoformat(x["end"]) - xs)
                    x.update(start=iso(ns), end=iso(ne)); sch[x["po"]].update(plannedStart=iso(ns), plannedEnd=iso(ne)); po[x["po"]].update(plannedStart=iso(ns), plannedEnd=iso(ne))


def _fix_pack_units(materials, stages):
    """PKG stage consumes every slit child of its parent: make consumesInput edges explicit on the pack unit."""
    by_id = {u["id"]: u for u in materials}
    for st in stages:
        if st["line"] != "PKG": continue
        pk = by_id[st["outUnits"][0]]; inp = by_id.get(st["inUnit"])
        sibs = [u["id"] for u in materials if u.get("parentId") == (inp or {}).get("parentId") and u["product"] == "SLIT"] if inp and inp["product"] == "SLIT" else [st["inUnit"]]
        pk["packsUnits"] = sibs
        pk["vendorId"] = pick(["V01", "V02", "V03"])


def build_free_stock(items):
    """Free HR coils in the yard (not allocated), a few on hold / in transit, and Material-Allocator suggestions for open items."""
    free, sugg = [], []
    open_items = [it for it in items if it["product"] in ("GI", "PPGI", "GL", "PPGL", "CRFH")]
    R.shuffle(open_items)
    targets = open_items[:12]
    for i in range(26):
        it = pick(targets) if R.random() < 0.7 else pick(items)
        u = _hr_coil(it); u["ageDays"] = (ASOF - datetime.strptime(u["receivedAt"][:10], "%Y-%m-%d")).days
        u["status"] = "AVAILABLE"; u["stockType"] = "FREE"; free.append(u)
    for i in range(3):
        u = _hr_coil(pick(items)); u.update(status="ON_HOLD", stockType="HOLD", holdReason=pick(["Rust patches on OD wraps", "Weight mismatch vs SAP GRN", "Heat certificate awaited"]),
                                            ageDays=R.randint(5, 40)); free.append(u)
    for i in range(2):
        u = _hr_coil(pick(items)); u.update(status="IN_TRANSIT", stockType="TRANSIT", vendorBatch=f"VB-{R.randint(100000, 999999)}", eta=day(ASOF + timedelta(days=R.randint(1, 4))),
                                            location="In transit — rake from Vijayanagar", ageDays=0); free.append(u)
    # MA suggestions: top-3 free coils per open target item, scored
    for it in targets[:8]:
        cands = []
        for u in free:
            if u["status"] != "AVAILABLE": continue
            gm = HR_GRADE.get(it["gradeId"]) == u["gradeId"]
            wm = 0 <= u["width"] - it["width"] <= 120
            tm = it["product"] == "HRPO" or 3.5 <= u["thk"] / it["thk"] <= 6.5
            if not (gm and wm and tm): continue
            score = 100 - (u["width"] - it["width"]) / 6 + min(u["ageDays"], 30) * 0.8 - abs(u["weightMT"] - 21) * 1.5
            cands.append((round(score, 1), u["id"]))
        cands.sort(reverse=True)
        for rank, (sc, uid) in enumerate(cands[:3], 1):
            sugg.append(dict(id=f"MAS-{SEQ.next('mas'):04d}", itemId=it["id"], soId=it["soId"], customerName=it["customerName"], unitId=uid, rank=rank, score=sc,
                             ppcApproval="PENDING" if rank > 1 else pick(["APPROVED", "PENDING"]), qcApproval="PENDING", status="SUGGESTED",
                             reasons=["grade family match", "width fits with trim", "reduction feasible" if it["product"] != "HRPO" else "gauge match", "FIFO age"]))
    return free, sugg
