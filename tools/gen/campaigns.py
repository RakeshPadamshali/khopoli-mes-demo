"""COMMERCIAL & PLANNING: forward line-load plan (schedule-only rows).
The balance-to-produce of every open sales-order item is split into ~20 t campaign coils and inserted coil by coil, forward in
time, into the free windows left by the recorded coils: every step of a coil is placed as early as possible after the previous
step plus a transfer time (continuous flow, precedence guaranteed), releases into the plant are paced by the CGL bottleneck takt
so upstream lines do not run days ahead, and the coil order groups an order's coils together and same-family orders (coating +
thickness + paint) within the same due-date window so campaigns emerge on every line with changeover minutes between families.
WIP coils of in-progress orders sit in the yard already past the first lines and go first.
No material record exists for these coils yet: the Material Allocator assigns HR coils at release."""
import random
from datetime import datetime, timedelta, date
from .common import ASOF, iso, h, m, r2, YM
from .assets_specs import LINES

LINE = {l["id"]: l for l in LINES}
HORIZON_DAYS = 10
RC = random.Random(2611)          # own stream so the rest of the dataset stays byte-identical
SETUP = {"HRS": 0.2, "PKL": 0.15, "CRM": 0.2, "CGL": 0.2, "CCL": 0.3, "SLT": 0.2, "RWL": 0.15, "PKG": 0.1}                 # h per coil: threading, sampling
TRANSFER = {"HRS": (1, 3), "PKL": (1, 3), "CRM": (1, 4), "CGL": (1, 4), "CCL": (2, 6), "SLT": (0.5, 2), "RWL": (0.5, 2)}   # h to the next line (cooling, crane, yard)
RAL_RANK = {"9010": 0, "9002": 1, "1015": 2, "7035": 3, "5012": 4, "6005": 5, "6018": 5, "3009": 6, "7016": 7, "8017": 8, "9005": 9}
SAME = {"CGL": 10, "CCL": 10, "CRM": 10, "PKL": 5, "SLT": 10, "RWL": 10, "PKG": 5, "HRS": 10}                                 # min between coils of one family
DIFF = {"CRM": 30, "PKL": 15, "SLT": 35, "RWL": 15, "PKG": 5, "HRS": 20}
TAKT_H = (20 / LINE["CGL"]["tph"] + SETUP["CGL"]) * 1.05 + 0.1                                                                 # ≈ 1.27 h per coil: the bottleneck's takt incl. an average changeover share


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
    """minutes lost between two consecutive coils on a line (prev = None: unknown recorded coil -> family change)"""
    if prev is None: return DIFF.get(ln, 30)
    if family(ln, prev) == family(ln, c): return SAME[ln]
    if ln == "CGL": return 30 if (prev["coatingId"] or "") == (c["coatingId"] or "") else 60
    if ln == "CCL":
        if (prev["paintId"] or "") != (c["paintId"] or ""): return 45
        return 20 if RAL_RANK.get(c["ral"] or "", 5) >= RAL_RANK.get(prev["ral"] or "", 5) else 40   # light -> dark is cheap, dark -> light needs a clean
    return DIFF[ln]


def build_campaigns(items, routes, schedules):
    route_of = {r["itemId"]: r for r in routes}
    end = ASOF + timedelta(days=HORIZON_DAYS)
    # 1. coils: the balance-to-produce of every open item in ~20 t coils
    coils = []
    for it in items:
        btp = it.get("btpMT", 0)
        if btp < 8 or it["status"] == "DISPATCHED": continue
        n = max(1, round(btp / 20)); w = r2(btp / n); path = list(route_of[it["id"]]["path"])
        wip_n = min(2, n // 3) if (it["status"] in ("IN_PROGRESS", "PARTIALLY_DISPATCHED") and len(path) >= 3) else 0   # a coil or two already pickled / cold-rolled
        fam = f"{it.get('coatingId') or 'bare'}·{_band(it['thk'])}·{it.get('paintId') or ''}"
        for k in range(n):
            s0 = min(RC.choice([1, 1, 2, 2, 3]), len(path) - 2) if k < wip_n else 0
            coils.append(dict(itemId=it["id"], soId=it["soId"], product=it["product"], thk=it["thk"], width=it["width"], ral=it.get("ral"), coatingId=it.get("coatingId"), paintId=it.get("paintId"),
                              slitWidths=it.get("slitWidths"), qtyMT=w, seq=k + 1, of=n, path=path, s0=s0, due=it["reqDate"], fam=fam, hero=bool(it.get("hero")), ends={}))
    # 2. insertion order: the golden-thread order first, then by due-date window (2 days) -> campaign family -> order -> coil,
    #    so an order's coils are consecutive and same-family orders adjacent (WIP coils simply skip the steps already done)
    coils.sort(key=lambda c: (0 if c["hero"] else 1, date.fromisoformat(c["due"]).toordinal() // 2, c["fam"], c["itemId"], c["seq"]))
    # smooth the colour line: alternate painted and unpainted orders in the sequence (CCL is slower than the CGL takt, so a run of
    # colour-coated orders would pile up in front of it); each order's coils stay consecutive
    order_seq = []; seen = set()
    for c in coils:
        if c["itemId"] not in seen: seen.add(c["itemId"]); order_seq.append(c["itemId"])
    painted = {c["itemId"] for c in coils if "CCL" in c["path"]}
    pq = [o for o in order_seq if o in painted]; nq = [o for o in order_seq if o not in painted]; merged = []
    while pq or nq:
        if nq: merged.append(nq.pop(0))
        if pq: merged.append(pq.pop(0))
    rank = {o: i for i, o in enumerate(merged)}
    # coils already past cold rolling (waiting in the CGL yard) take the first windows, then the golden-thread order, then the merged sequence
    coils.sort(key=lambda c: (0 if c["s0"] >= 2 else 1, 0 if c["hero"] else 1, rank[c["itemId"]], c["seq"]))
    for i, c in enumerate(coils): c["id"] = f"PLC-{YM}-{i + 1:04d}"
    # takt-based release: coil k owns the bottleneck slot ASOF + 1 h + k × takt; it enters the plant one upstream lead time earlier,
    # so pickling and cold rolling run from now on and every coil reaches CGL about when its slot opens (continuous flow, small queues)
    for k, c in enumerate(coils):
        rem = c["path"][c["s0"]:]; up = rem[:rem.index("CGL")] if "CGL" in rem else rem[:-1]
        lead = sum(c["qtyMT"] / LINE[ln]["tph"] + SETUP[ln] + sum(TRANSFER[ln]) / 2 for ln in up)
        c["release"] = max(ASOF + h(0.5), ASOF + h(1 + k * TAKT_H + RC.uniform(0, 0.3)) - h(lead))
    # 3. forward insertion into the free windows of every line (recorded coils are fixed)
    busy = {ln: [(datetime.fromisoformat(s["plannedStart"]), datetime.fromisoformat(s["plannedEnd"])) for s in schedules if s["line"] == ln] for ln in LINE}
    placed = {ln: [] for ln in LINE}                                                          # (start, end, coil, stage index) — campaign bars only

    def free_from(ln, s, dur):
        while True:
            e = s + dur; nxt = None
            for a, b in busy[ln]:
                if s < b and e > a and (nxt is None or b < nxt): nxt = b
            if nxt is None: return s
            s = nxt + m(8)

    def prev_bar(ln, s):
        best = None
        for p in placed[ln]:
            if p[1] <= s and (best is None or p[1] > best[1]): best = p
        return best

    def insert(ln, ready, c):
        dur = h(c["qtyMT"] / LINE[ln]["tph"] + SETUP[ln] + RC.uniform(-0.05, 0.1)); s = ready
        for _ in range(6):                                                                     # settle: free window + changeover after whatever runs before it
            s = free_from(ln, s, dur); p = prev_bar(ln, s)
            gap = changeover(ln, p[2] if p else None, c) if (p or any(b <= s for _, b in busy[ln])) else 0
            lim = (p[1] if p else max([b for _, b in busy[ln] if b <= s] or [s])) + m(gap)
            if s >= lim: break
            s = lim
        e = s + dur; busy[ln].append((s, e)); return s, e, gap

    for c in coils:
        t = c["release"]
        for si in range(c["s0"], len(c["path"])):
            ln = c["path"][si]
            if si > c["s0"]:
                lo, hi = TRANSFER[c["path"][si - 1]]; t = c["ends"][c["path"][si - 1]] + h(RC.uniform(lo, hi))
            s, e, gap = insert(ln, t, c)
            if s >= end: busy[ln].pop(); break                                                # beyond the horizon: this coil stops here
            c["ends"][ln] = e; placed[ln].append((s, e, c, si, gap))
    # 4. rows with campaign ids per line (consecutive same-family bars)
    rows = []; n = 0
    for ln in placed:
        camp = 0; fam = None
        for s, e, c, si, gap in sorted(placed[ln], key=lambda p: p[0]):
            f = family(ln, c)
            if f != fam: camp += 1; fam = f
            n += 1
            rows.append(dict(id=f"CSCH-{n:04d}", line=ln, unitId=c["id"], coilSeq=c["seq"], coilsOf=c["of"], itemId=c["itemId"], soId=c["soId"], product=c["product"], qtyMT=c["qtyMT"],
                             stage=si + 1, stages=len(c["path"]), wip=c["s0"] > 0, plannedStart=iso(s), plannedEnd=iso(e), status="PLANNED", campaign=f"CMP-{ln}-{camp:03d}", family=f,
                             changeoverMin=gap, po=None, rush=False, hero=False, source="campaign"))
    # 5. per-item summary for the pages
    per = {}
    for c in coils:
        p = per.setdefault(c["itemId"], dict(planCoils=0, horizonCoils=0, horizonMT=0.0))
        p["planCoils"] += 1
        if c["ends"]: p["horizonCoils"] += 1; p["horizonMT"] = r2(p["horizonMT"] + c["qtyMT"])
    for it in items:
        it.update(per.get(it["id"], dict(planCoils=0, horizonCoils=0, horizonMT=0.0)))
    rows.sort(key=lambda r: (r["plannedStart"], r["line"]))
    return rows
