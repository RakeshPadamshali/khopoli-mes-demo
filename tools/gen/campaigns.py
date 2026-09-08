"""COMMERCIAL & PLANNING: forward line-load plan (schedule-only rows).
The balance-to-produce of every open sales-order item is split into ~20 t campaign coils and sequenced per line around the
recorded thread coils, from now to the end of a 10-day horizon: campaign affinity (coating + thickness family on CGL, light -> dark
colour on CCL, gauge on CRM, knife set on the slitter), changeover gaps, transfer times between lines, WIP already past the first
lines for in-progress orders, and releases sized to the CGL bottleneck so upstream lines run in campaigns rather than a trickle.
No material record exists for these coils yet: the Material Allocator assigns HR coils at release."""
import random
from datetime import datetime, timedelta
from .common import ASOF, iso, h, m, r2, YM
from .assets_specs import LINES

LINE = {l["id"]: l for l in LINES}
HORIZON_DAYS = 10
RC = random.Random(2611)          # own stream so the rest of the dataset stays byte-identical
ORDER = ["HRS", "PKL", "CRM", "CGL", "CCL", "SLT", "RWL", "PKG"]
SETUP = {"HRS": 0.2, "PKL": 0.15, "CRM": 0.2, "CGL": 0.2, "CCL": 0.3, "SLT": 0.2, "RWL": 0.15, "PKG": 0.1}                 # h per coil: threading, sampling
TRANSFER = {"HRS": (2, 6), "PKL": (2, 8), "CRM": (3, 10), "CGL": (3, 10), "CCL": (12, 30), "SLT": (2, 8), "RWL": (2, 8)}   # h to the next line (cooling, yard)
RAL_RANK = {"9010": 0, "9002": 1, "1015": 2, "7035": 3, "5012": 4, "6005": 5, "6018": 5, "3009": 6, "7016": 7, "8017": 8, "9005": 9}
SAME = {"CGL": 10, "CCL": 10, "CRM": 10, "PKL": 5, "SLT": 10, "RWL": 10, "PKG": 5, "HRS": 10}                                 # min between coils of one family
DIFF = {"CRM": 30, "PKL": 15, "SLT": 35, "RWL": 15, "PKG": 5, "HRS": 20}


def _band(t): return "≤ 0.5" if t <= 0.5 else "0.6–0.8" if t <= 0.8 else "1.0–1.2" if t <= 1.2 else "> 1.2"


def family(ln, c):
    """the campaign key per line — coils of one family run back to back"""
    if ln == "CGL": return f"{c['coatingId'] or 'bare'} · {_band(c['thk'])} mm"
    if ln == "CCL": return f"{c['paintId'] or 'paint'} · RAL {c['ral'] or '—'}"
    if ln == "CRM": return f"gauge {c['thk']:.2f} mm"
    if ln == "PKL": return f"{c['width']} mm · {_band(c['thk'])} mm"
    if ln in ("SLT", "RWL"): return ("knife " + " + ".join(str(w) for w in c["slitWidths"])) if c.get("slitWidths") else f"full width {c['width']}"
    if ln == "HRS": return f"{c['width']} mm"
    return "packing"


def changeover(ln, prev, c):
    """minutes lost between two consecutive coils on a line"""
    if prev is None: return 0
    if family(ln, prev) == family(ln, c): return SAME[ln]
    if ln == "CGL": return 30 if (prev["coatingId"] or "") == (c["coatingId"] or "") else 60
    if ln == "CCL":
        if (prev["paintId"] or "") != (c["paintId"] or ""): return 45
        return 20 if RAL_RANK.get(c["ral"] or "", 5) >= RAL_RANK.get(prev["ral"] or "", 5) else 40   # light -> dark is cheap, dark -> light needs a clean
    return DIFF[ln]


def build_campaigns(items, routes, schedules):
    route_of = {r["itemId"]: r for r in routes}
    end = ASOF + timedelta(days=HORIZON_DAYS)
    # 1. coils: the balance-to-produce of every open item in ~20 t coils, earliest due date first
    coils = []
    for it in sorted(items, key=lambda i: (i["reqDate"], i["id"])):
        btp = it.get("btpMT", 0)
        if btp < 8 or it["status"] == "DISPATCHED": continue
        n = max(1, round(btp / 20)); w = r2(btp / n); path = list(route_of[it["id"]]["path"])
        wip_n = (n + 1) // 2 if it["status"] in ("IN_PROGRESS", "PARTIALLY_DISPATCHED") else 0    # in-progress orders already have coils past the first lines
        for k in range(n):
            s0 = min(RC.choice([1, 1, 2, 2, 3]), len(path) - 2) if (k < wip_n and len(path) >= 3) else 0
            coils.append(dict(itemId=it["id"], soId=it["soId"], product=it["product"], thk=it["thk"], width=it["width"], ral=it.get("ral"), coatingId=it.get("coatingId"), paintId=it.get("paintId"),
                              slitWidths=it.get("slitWidths"), qtyMT=w, seq=k + 1, of=n, path=path, s0=s0, due=it["reqDate"], ends={}))
    for i, c in enumerate(coils): c["id"] = f"PLC-{YM}-{i + 1:04d}"
    # 2. release: WIP coils are ready within the first shift; fresh coils enter the plant in 6-hourly batches of six (what the CGL bottleneck eats)
    fresh = 0
    for c in coils:
        if c["s0"] > 0: c["release"] = ASOF + h(RC.uniform(0.5, 12))
        else: c["release"] = ASOF + h(6 * (fresh // 6)) + h(RC.uniform(0.3, 5.5)); fresh += 1
    # 3. per line, in process order: greedy campaign sequencing into the free intervals left by the recorded coils
    busy = {ln: [(datetime.fromisoformat(s["plannedStart"]), datetime.fromisoformat(s["plannedEnd"])) for s in schedules if s["line"] == ln] for ln in LINE}

    def slot(ln, s, dur):
        while True:
            e = s + dur; nxt = None
            for a, b in busy[ln]:
                if s < b and e > a and (nxt is None or b < nxt): nxt = b
            if nxt is None: busy[ln].append((s, e)); return s, e
            s = nxt + m(8)

    rows = []; n = 0
    for ln in ORDER:
        pend = []
        for c in coils:
            if ln not in c["path"]: continue
            si = c["path"].index(ln)
            if si < c["s0"]: continue                                  # done before the horizon (WIP stock)
            if si == c["s0"]: ready = c["release"]
            else:
                pl = c["path"][si - 1]; pe = c["ends"].get(pl)
                if pe is None: continue                                # upstream stage falls beyond the horizon
                lo, hi = TRANSFER[pl]; ready = pe + h(RC.uniform(lo, hi))
            pend.append((ready, c, si))
        t = ASOF + m(25); prev = None; camp = 0; fam = None
        while pend and t < end:
            look = [p for p in pend if p[0] <= t + h(6)]
            if not look: t = min(p[0] for p in pend); continue
            pk = min(look, key=lambda p: (0 if (t - p[0]) > h(12) else 1, changeover(ln, prev, p[1]), p[1]["due"], p[0], p[1]["id"]))   # aging beats affinity
            pend.remove(pk); ready, c, si = pk
            gap = changeover(ln, prev, c); dur = h(c["qtyMT"] / LINE[ln]["tph"] + SETUP[ln] + RC.uniform(-0.05, 0.1))
            s, e = slot(ln, max(t + m(gap), ready), dur)
            if s >= end: busy[ln].pop(); continue
            f = family(ln, c)
            if f != fam: camp += 1; fam = f
            n += 1; c["ends"][ln] = e; prev = c; t = e
            rows.append(dict(id=f"CSCH-{n:04d}", line=ln, unitId=c["id"], coilSeq=c["seq"], coilsOf=c["of"], itemId=c["itemId"], soId=c["soId"], product=c["product"], qtyMT=c["qtyMT"],
                             stage=si + 1, stages=len(c["path"]), wip=c["s0"] > 0, plannedStart=iso(s), plannedEnd=iso(e), status="PLANNED", campaign=f"CMP-{ln}-{camp:03d}", family=f,
                             changeoverMin=gap, po=None, rush=False, hero=False, source="campaign"))
    # 4. per-item summary for the pages
    per = {}
    for c in coils:
        p = per.setdefault(c["itemId"], dict(planCoils=0, horizonCoils=0, horizonMT=0.0))
        p["planCoils"] += 1
        if c["ends"]: p["horizonCoils"] += 1; p["horizonMT"] = r2(p["horizonMT"] + c["qtyMT"])
    for it in items:
        p = per.get(it["id"], dict(planCoils=0, horizonCoils=0, horizonMT=0.0)); it.update(p)
    rows.sort(key=lambda r: (r["plannedStart"], r["line"]))
    return rows
