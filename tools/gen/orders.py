"""COMMERCIAL & PLANNING: sales orders (SAP schedule-line level), TDC (variant configuration), SAP vs FP routes."""
from datetime import datetime, timedelta
from .common import R, BASE, ASOF, iso, day, pick, between, r1
from .assets_specs import CUSTOMERS, GRADES, COATINGS, PAINTS, RALS

# product templates: (product, grade, thk options, width options, coating, paint) — weights = mix
TEMPLATES = [
    ("PPGI", "DX51D+Z", [0.45, 0.50, 0.60, 0.80], [1000, 1220, 1250], "Z120", True, 30),
    ("PPGL", "SGLCC", [0.45, 0.50], [1220, 1250], "AZ150", True, 6),
    ("GI", "DX51D+Z", [0.50, 0.80, 1.00, 1.20], [1220, 1250, 1500], "Z120", False, 22),
    ("GI", "DX53D+Z", [0.80, 1.00], [1250, 1500], "Z120", False, 6),
    ("GI", "S350GD+Z", [0.80, 1.00, 1.20], [1250], "Z275", False, 6),
    ("GI", "CQ-IS277", [0.35, 0.40, 0.50], [1000, 1220], "Z80", False, 8),
    ("GL", "SGLCC", [0.45, 0.50], [1220], "AZ150", False, 6),
    ("CRFH", "CR4-CRFH", [0.50, 0.60, 0.80], [1250], None, False, 8),
    ("HRPO", "HRPO-E250", [2.0, 2.5, 3.0, 4.0], [1250, 1500], None, False, 8),
]
ROUTES = {"PPGI": ["PKL", "CRM", "CGL", "CCL", "SLT", "PKG"], "PPGL": ["PKL", "CRM", "CGL", "CCL", "SLT", "PKG"],
          "GI": ["PKL", "CRM", "CGL", "SLT", "PKG"], "GL": ["PKL", "CRM", "CGL", "SLT", "PKG"],
          "CRFH": ["PKL", "CRM", "RWL", "PKG"], "HRPO": ["PKL", "SLT", "PKG"]}
YIELDS = {"HRS": 0.985, "PKL": 0.985, "CRM": 0.96, "CGL": 0.975, "CCL": 0.98, "SLT": 0.95, "RWL": 0.97, "PKG": 1.0}
STAGE_PRODUCT = {"PKL": "HRPO", "CRM": "CRFH", "CGL": None, "CCL": None, "SLT": "SLIT", "RWL": "TRIMMED", "PKG": "PACK", "HRS": "HRC"}

HERO_SO, HERO_ITEM = "4213090017", "4213090017/10"
DOWNGRADE_SO_ITEM = "4213090024/10"
RUSH_ITEM = "4213090031/10"
SWAP_A, SWAP_B = "4213090008/10", "4213090012/10"
AMEND_ITEM = "4213090022/10"


def _tmpl():
    tot = sum(t[6] for t in TEMPLATES); x = R.random() * tot
    for t in TEMPLATES:
        x -= t[6]
        if x <= 0: return t
    return TEMPLATES[0]


def _item(so, n, t, qty=None, fixed=None):
    prod, grade, thks, widths, coat, painted, _ = t
    thk, width = pick(thks), pick(widths)
    it = dict(id=f"{so}/{n}", soId=so, item=n, product=prod, gradeId=grade, thk=thk, width=width, coatingId=coat,
              paintId=(pick(["RMP", "RMP", "SMP", "PVDF"]) if painted else None), ral=(pick(RALS)[0] if painted else None),
              qtyMT=qty or pick([40, 60, 80, 100, 120, 150, 200, 250, 300]), packing=pick(["DOM", "DOM", "DOM", "EXP"]),
              slitWidths=None, status="OPEN", ontologyDomain="COMMERCIAL & PLANNING")
    if fixed: it.update(fixed)
    if it["paintId"]:
        p = next(x for x in PAINTS if x["id"] == it["paintId"]); it["dftTop"], it["dftTol"], it["dftBack"] = p["topUm"], p["topTol"], p["backUm"]
    if prod in ("GI", "PPGI", "GL", "PPGL") and R.random() < 0.45 and not it.get("slitWidths"):
        k = pick([2, 3]); w = (it["width"] - 20) // k; it["slitWidths"] = [w] * k
    return it


def build_orders():
    orders, items, tdcs, routes = [], [], [], []
    for i in range(1, 41):
        so = f"42130900{i:02d}"
        cust = pick(CUSTOMERS)
        created = BASE - timedelta(days=R.randint(5, 40), hours=R.randint(0, 20))
        o = dict(id=so, customerId=cust["id"], customerName=cust["name"], segment=cust["segment"], createdAt=iso(created), status="OPEN",
                 routeSource=pick(["FP", "FP", "SAP"]), rush=False, rushAt=None, priority=pick([1, 2, 2, 3, 3, 3]), sapDocType="ZOR", plantId="KHP",
                 ontologyDomain="COMMERCIAL & PLANNING")
        n_items = pick([1, 1, 2, 2, 3])
        for k in range(n_items):
            t = _tmpl(); it = _item(so, 10 * (k + 1), t)
            req = created + timedelta(days=R.randint(25, 60)); it["reqDate"] = day(req); it["fpCommit"] = day(req - timedelta(days=R.randint(0, 4)))
            it["customerId"], it["customerName"], it["segment"] = cust["id"], cust["name"], cust["segment"]
            items.append(it)
        orders.append(o)
    # ---- scripted orders for the golden thread & scenarios ----
    def fix(item_id, cust_id, prod, grade, thk, width, coat, paint, ral, qty, req, commit, slits=None, packing="DOM", extra=None):
        it = next(x for x in items if x["id"] == item_id); c = next(x for x in CUSTOMERS if x["id"] == cust_id)
        o = next(x for x in orders if x["id"] == it["soId"]); o.update(customerId=c["id"], customerName=c["name"], segment=c["segment"])
        it.update(customerId=c["id"], customerName=c["name"], segment=c["segment"], product=prod, gradeId=grade, thk=thk, width=width, coatingId=coat,
                  paintId=paint, ral=ral, qtyMT=qty, reqDate=req, fpCommit=commit, slitWidths=slits, packing=packing)
        if paint:
            p = next(x for x in PAINTS if x["id"] == paint); it["dftTop"], it["dftTol"], it["dftBack"] = p["topUm"], p["topTol"], p["backUm"]
        else:
            it.pop("dftTop", None); it.pop("dftTol", None); it.pop("dftBack", None)
        if extra: it.update(extra)
        return it, o
    fix(HERO_ITEM, "C001", "PPGI", "DX51D+Z", 0.50, 1220, "Z120", "RMP", "9002", 120, "2026-09-20", "2026-09-18", slits=[610, 610])
    fix(DOWNGRADE_SO_ITEM, "C004", "PPGI", "DX51D+Z", 0.50, 1220, "Z120", "RMP", "9002", 90, "2026-09-28", "2026-09-26", slits=[610, 610],
        extra={"dftTop": 15, "dftTol": 3, "dftBack": 7})
    it, o = fix(RUSH_ITEM, "C003", "GI", "DX53D+Z", 0.80, 1250, "Z120", None, None, 60, "2026-09-18", "2026-09-17")
    o.update(rush=True, rushAt=iso(datetime(2026, 9, 14, 9, 0)), priority=1, rushReason="APS rush flag — customer line stoppage at Chakan")
    fix(SWAP_A, "C007", "GI", "DX51D+Z", 0.80, 1250, "Z120", None, None, 100, "2026-09-22", "2026-09-20")
    fix(SWAP_B, "C010", "GI", "DX51D+Z", 0.80, 1250, "Z120", None, None, 80, "2026-09-16", "2026-09-15")
    it, o = fix(AMEND_ITEM, "C006", "GI", "S350GD+Z", 1.00, 1250, "Z275", None, None, 180, "2026-10-05", "2026-10-02")
    o.update(amendment=dict(at=iso(datetime(2026, 9, 15, 8, 10)), field="qtyMT", old=180, new=210, source="SAP IDoc ORDERS05", status="FAILED_IDOC"))
    # schedule lines (SAP): split qty into 1-2 schedule lines
    for it in items:
        q = it["qtyMT"]; lines = [q] if q <= 100 or R.random() < 0.5 else [round(q * 0.6), q - round(q * 0.6)]
        d0 = datetime.strptime(it["reqDate"], "%Y-%m-%d")
        it["scheduleLines"] = [dict(id=f"{it['id']}/{n + 1:04d}", qtyMT=ql, date=day(d0 + timedelta(days=7 * n)), status="OPEN") for n, ql in enumerate(lines)]
        it["tdcId"] = "TDC-" + it["id"].replace("/", "-")
        tdcs.append(_tdc(it))
        routes.append(_route(it))
    return orders, items, tdcs, routes


def _tdc(it):
    g = next(x for x in GRADES if x["id"] == it["gradeId"])
    ch = [("Product", it["product"]), ("Grade / standard", f"{g['id']} ({g['std']})"), ("Thickness (mm)", f"{it['thk']:.2f} ±{0.03 if it['thk'] < 1 else 0.05}"),
          ("Width (mm)", f"{it['width']} +5/-0"), ("Coil ID (mm)", "508"), ("Max coil weight (t)", "22")]
    if it["coatingId"]:
        c = next(x for x in COATINGS if x["id"] == it["coatingId"])
        ch += [("Coating", f"{c['id']} — {c['gsm']} g/m² total, band {c['bandMin']}–{c['bandMax']}"), ("Spangle", c["spangle"]), ("Passivation", "Chromate, oiled"),]
    if it.get("paintId"):
        p = next(x for x in PAINTS if x["id"] == it["paintId"]); rn = next(x[1] for x in RALS if x[0] == it["ral"])
        ch += [("Paint system", f"{p['id']} — {p['name']}"), ("Colour (top)", f"RAL {it['ral']} {rn}"), ("DFT top (µm)", f"{it['dftTop']} ±{it['dftTol']}"),
               ("DFT back (µm)", f"{it['dftBack']} ±2"), ("Gloss (60°)", f"{p['glossMin']}–{p['glossMax']}"), ("Guard film", "Yes, top side")]
    if it.get("slitWidths"): ch.append(("Slitting", " + ".join(str(w) for w in it["slitWidths"]) + " mm"))
    ch += [("Packing", "Export seaworthy" if it["packing"] == "EXP" else "Domestic, VCI + stretch wrap"), ("Test certificate", "EN 10204 3.1"), ("Marking", "Customer logo + batch QR")]
    return dict(id=it["tdcId"], itemId=it["id"], source="SAP Variant Configuration", characteristics=[dict(name=n, value=v) for n, v in ch])


def _route(it):
    path = ROUTES[it["product"]][:]
    if it["product"] == "HRPO" and R.random() < 0.3: path = ["HRS"] + [p for p in path if p != "SLT"]
    if it["product"] in ("GI", "GL") and not it.get("slitWidths"): path = [p for p in path if p != "SLT"]
    if it["product"] in ("PPGI", "PPGL") and not it.get("slitWidths"): path = [p for p in path if p != "SLT"]
    ys = [YIELDS[p] for p in path]
    tree = ["HRC"] + [STAGE_PRODUCT[p] or it["product"] for p in path]
    fp_path = path[:]
    fp_alt = None
    if "SLT" in path and R.random() < 0.25: fp_alt = "RWL"  # FP proposes rewinding+trim instead of slitting for narrow trims
    return dict(itemId=it["id"], sapRoute=dict(processPath=">".join(path), yieldString=">".join(f"{y:.3f}" for y in ys), routeString="-".join(f"R{p}" for p in path)),
                fpRoute=dict(processPath=">".join(fp_path), yieldString=">".join(f"{YIELDS[p]:.3f}" for p in fp_path), routeString="-".join(f"F{p}" for p in fp_path),
                             fpMfgOrder="FPM-" + it["id"].replace("/", "-"), altWorkCentre=fp_alt),
                materialTree=tree, path=path, chosen=("FP" if R.random() < 0.7 else "SAP"))
