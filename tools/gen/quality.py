"""QUALITY: defects (detectedOn material, attributedTo equipment), downstream propagation, quality decisions (UD codes),
downgrade suggestions validated against sales-order parameters, test certificates with the DFT dispatch gate, holds."""
from datetime import datetime, timedelta
from .common import R, ASOF, iso, h, m, pick, between, r1, r2, SEQ
from .assets_specs import DEFECT_CODES, COATINGS, PAINTS, GRADES

DC = {d["code"]: d for d in DEFECT_CODES}
FG = ("GI", "GL", "PPGI", "PPGL", "CRFH", "HRPO")


def downstream(unit_id, edges):
    """all units that (transitively) consumesInput the given unit"""
    kids = {}
    for rel, a, b in edges:
        if rel == "consumesInput": kids.setdefault(b, []).append(a)
    out, stack = [], [unit_id]
    while stack:
        x = stack.pop()
        for k in kids.get(x, []):
            if k not in out: out.append(k); stack.append(k)
    return out


def build_quality(materials, stages, items, edges, hero_thread):
    by_unit = {u["id"]: u for u in materials}; by_item = {it["id"]: it for it in items}
    defects, decisions, suggestions, certs, holds = [], [], [], [], []
    hero_units = {by_unit[u]["product"]: by_unit[u] for u in hero_thread["units"] if by_unit[u]["product"] in ("HRC", "GI", "PPGI")}
    hero_hr, hero_gi, hero_pp = hero_units["HRC"], hero_units["GI"], hero_units["PPGI"]

    def defect(code, unit, at, source, equip=None, sev=None, pos=None, note=None, hero=False, extra=None):
        d = DC[code]; eq = equip or (f"{d['line']}-{d['attrib']}" if "-" not in d["attrib"] else d["attrib"])
        line = unit.get("producedOn") if code not in ("SCL", "RST") else "PKL"
        rec = dict(id=f"DEF-2609-{SEQ.next('def'):04d}", code=code, name=d["name"], severity=sev or d["severity"], detectedOn=unit["id"], detectedProduct=unit["product"],
                   detectedAtLine=line, detectedAt=iso(at), source=source, attributedTo=eq, attributedLine=eq.rsplit("-", 1)[0] if eq.count("-") >= 2 else eq.split("-")[0],
                   attributedPlant="VJNR" if eq.startswith("VJNR") else "DLV" if eq.startswith("DLV") else "KHP", positionM=pos or R.randint(40, 900), side=pick(["Top", "Bottom", "Both"]),
                   lengthM=R.randint(2, 60), imageRef=f"sis/{unit['id']}-{code}.jpg" if source == "SIS" else None, note=note, status="OPEN", hero=hero,
                   downstreamAffected=downstream(unit["id"], edges), ontologyDomain="QUALITY")
        if extra: rec.update(extra)
        edges.append(("detectedOn", rec["id"], unit["id"])); edges.append(("attributedTo", rec["id"], eq))
        defects.append(rec); return rec
    # hero defects (same coil family used across S1 / S4)
    defect("SCL", hero_hr, datetime(2026, 9, 9, 6, 45), "SIS", equip="VJNR-HSM-DSB", sev="Major", pos=312, note="Rolled-in scale streaks on OD wraps, entry SIS at pickling; cross-plant root cause (Vijayanagar HSM descaling box)", hero=True, extra={"status": "CLOSED", "disposition": "Accepted — removed by pickling"})
    defect("DRS", hero_gi, datetime(2026, 9, 14, 22, 15), "SIS", sev="Major", pos=188, note="Zinc-pot dross inclusions, 3 clusters 0.4–0.8 mm, entry inspection at CCL", hero=True, extra={"status": "OPEN", "disposition": "Under review — propagation to colour-coated coil"})
    defect("DFT", hero_pp, datetime(2026, 9, 15, 1, 42), "PDO auto-comparison", sev="Major", pos=0, note="PDO DFT top 16.8 µm vs PDI target 20 ±3 (min 17.0) — lab confirmation pending", hero=True,
           extra={"status": "AUTO_FLAGGED", "labTest": "PENDING", "disposition": None})
    # random defects on produced units
    produced = [u for u in materials if u.get("producedAt") and u["product"] != "PACK" and not u.get("threadId") == hero_thread["id"]]
    R.shuffle(produced)
    for u in produced[:37]:
        codes = [d for d in DEFECT_CODES if d["line"] == u.get("producedOn")] or [DC["SCR"]]
        d = pick(codes); at = datetime.fromisoformat(u["producedAt"]) + m(R.randint(2, 40))
        rec = defect(d["code"], u, at, pick(["SIS", "SIS", "Manual (line inspector)", "Lab"]))
        rec["status"] = pick(["CLOSED", "CLOSED", "OPEN", "CLOSED"]); rec["disposition"] = pick(["Accepted — within customer limit", "Downgraded", "Rework — re-pass", "Accepted after re-inspection", None])
    # quality decisions (UD) on finished units
    ud_map = {"PRIME": "Prime — cleared for dispatch", "DOWNGRADE": "Downgrade — secondary grade", "HOLD": "Hold — QA review", "REWORK": "Rework — replan", "SCRAP": "Scrap"}
    for u in materials:
        if u["product"] not in FG or not u.get("producedAt"): continue
        if u["id"] == hero_pp["id"]:
            ud = "HOLD"
        else:
            ud = R.choices(["PRIME", "DOWNGRADE", "HOLD", "REWORK", "SCRAP"], weights=[85, 6, 5, 3, 1])[0]
        dec = dict(id=f"UD-{SEQ.next('ud'):04d}", unitId=u["id"], product=u["product"], itemId=u.get("allocatedTo"), udCode=ud, description=ud_map[ud], decidedAt=iso(datetime.fromisoformat(u["producedAt"]) + m(R.randint(30, 240))),
                   decidedBy="Auto-clearance (surface + lab pass)" if ud == "PRIME" and R.random() < 0.7 else pick(["QC — S. Deshmukh", "QC — N. Rao", "QC — A. Kulkarni"]), mode="AUTO" if ud == "PRIME" else "MANUAL",
                   segment="Prime" if ud == "PRIME" else "Secondary" if ud == "DOWNGRADE" else None, hero=(u["id"] == hero_pp["id"]))
        if u["id"] == hero_pp["id"]: dec.update(decidedAt="2026-09-15T02:05:00", decidedBy="Auto-hold (PDO deviation)", mode="AUTO", reason="DFT deviation — lab test pending")
        u["udCode"] = ud; u["qualityStatus"] = {"PRIME": "CLEARED", "DOWNGRADE": "DOWNGRADED", "HOLD": "ON_HOLD", "REWORK": "REWORK", "SCRAP": "SCRAPPED"}[ud]
        if ud == "HOLD": u["status"] = "ON_HOLD"
        decisions.append(dec)
    # downgrade suggestions: hero (DFT) validated param-by-param against open SO items
    def validate(u, it, dft_top=None):
        rows = []
        rows.append(("Grade", it["gradeId"], u["gradeId"], it["gradeId"] == u["gradeId"]))
        rows.append(("Thickness (mm)", f"{it['thk']:.2f}", f"{u['thk']:.2f}", abs(it["thk"] - u["thk"]) < 0.001))
        rows.append(("Width (mm)", f"{it['width']} (+trim ≤ 60)", str(u["width"]), it["width"] <= u["width"] <= it["width"] + 60))
        rows.append(("Coating", it.get("coatingId") or "—", u.get("coatingId") or "—", it.get("coatingId") == u.get("coatingId")))
        if it.get("paintId"):
            rows.append(("Paint system", it["paintId"], u.get("paintId") or "—", it["paintId"] == u.get("paintId")))
            rows.append(("Colour RAL", it["ral"], u.get("ral") or "—", it["ral"] == u.get("ral")))
            if dft_top is not None: rows.append(("DFT top (µm)", f"{it['dftTop']} ±{it['dftTol']}", f"{dft_top}", abs(dft_top - it["dftTop"]) <= it["dftTol"]))
        return [dict(param=a, required=b, actual=c, ok=d) for a, b, c, d in rows]
    cands = [it for it in items if it["product"] == "PPGI" and it["id"] != hero_pp["allocatedTo"]]
    cands.sort(key=lambda it: (it["id"] != "4213090024/10", it["reqDate"]))
    sug = dict(id=f"DGS-{SEQ.next('dgs'):04d}", unitId=hero_pp["id"], trigger="DEF: DFT deviation (PDO auto-comparison)", reason="DFT top 16.8 µm below 17.0 µm minimum of SO 4213090017/10 (20 ±3)",
               suggestedAt="2026-09-15T01:45:00", suggestion="Re-allocate to an open order whose DFT spec accepts 16.8 µm; else downgrade to secondary (RAL 9002 stock)",
               candidates=[dict(itemId=it["id"], customerName=it["customerName"], reqDate=it["reqDate"], validation=validate(hero_pp, it, 16.8), ok=all(v["ok"] for v in validate(hero_pp, it, 16.8))) for it in cands[:4]],
               fallback=dict(segment="Secondary — RAL 9002 stock", priceImpactPct=-6), status="SUGGESTED", override=None, hero=True)
    suggestions.append(sug)
    for d in [x for x in defects if x["code"] in ("CWD", "CLR") and not x["hero"]][:2]:
        u = by_unit[d["detectedOn"]]
        suggestions.append(dict(id=f"DGS-{SEQ.next('dgs'):04d}", unitId=u["id"], trigger=f"DEF: {d['name']}", reason=d["name"] + " outside sales-order tolerance", suggestedAt=d["detectedAt"],
                                suggestion="Downgrade to secondary grade", candidates=[], fallback=dict(segment="Secondary", priceImpactPct=-8), status=pick(["ACCEPTED", "OVERRIDDEN"]),
                                override=dict(by="QC — N. Rao", decision="Accepted as prime after re-inspection", at=d["detectedAt"]) if R.random() < 0.5 else None, hero=False))
    # test certificates (FG units)
    for u in materials:
        if u["product"] not in ("GI", "GL", "PPGI", "PPGL") or not u.get("producedAt"): continue
        g = next(x for x in GRADES if x["id"] == u["gradeId"]); c = next((x for x in COATINGS if x["id"] == u.get("coatingId")), None)
        tests = [dict(test="Coating weight — triple spot (g/m²)", value=r1(between(c["bandMin"], c["bandMax"])), spec=f"{c['bandMin']}–{c['bandMax']}", result="PASS")] if c else []
        if c: tests.append(dict(test="Coating weight — single spot (g/m²)", value=r1(tests[0]["value"] * 0.9), spec=f"≥ {round(c['gsm'] * 0.85)}", result="PASS"))
        def rng(lo, hi, span):
            lo = lo or (hi - span if hi else 180); hi = (hi - 10) if hi else lo + span
            return R.randint(lo, max(hi, lo + 20))
        tests += [dict(test="Yield strength (MPa)", value=rng(g["ysMin"], g["ysMax"], 80), spec=f"{g['ysMin'] or '—'}–{g['ysMax'] or '—'}", result="PASS"),
                  dict(test="Tensile strength (MPa)", value=rng(g["utsMin"], g["utsMax"], 90), spec=f"{g['utsMin'] or '—'}–{g['utsMax'] or '—'}", result="PASS"),
                  dict(test="Elongation A80 (%)", value=R.randint((g["elMin"] or 20), (g["elMin"] or 20) + 8), spec=f"≥ {g['elMin'] or '—'}", result="PASS"),
                  dict(test="Bend test (180°)", value="No crack", spec="No crack", result="PASS")]
        if u["product"] in ("PPGI", "PPGL"):
            p = next(x for x in PAINTS if x["id"] == u["paintId"]); it = by_item.get(u["allocatedTo"], {})
            if u["id"] == hero_pp["id"]:
                tests += [dict(test="DFT top (µm)", value=None, spec=f"{it.get('dftTop')} ±{it.get('dftTol')}", result="PENDING"), dict(test="DFT back (µm)", value=None, spec=f"{it.get('dftBack')} ±2", result="PENDING"),
                          dict(test="T-bend adhesion", value="2T", spec="≤ 3T", result="PASS"), dict(test="Gloss 60°", value=34, spec=f"{p['glossMin']}–{p['glossMax']}", result="PASS")]
            else:
                dt = r1(it.get("dftTop", p["topUm"]) + between(-1.5, 1.5))
                tests += [dict(test="DFT top (µm)", value=dt, spec=f"{it.get('dftTop', p['topUm'])} ±{it.get('dftTol', 3)}", result="PASS"), dict(test="DFT back (µm)", value=r1(it.get("dftBack", 7) + between(-0.8, 0.8)), spec=f"{it.get('dftBack', 7)} ±2", result="PASS"),
                          dict(test="T-bend adhesion", value=pick(["1T", "2T"]), spec="≤ 3T", result="PASS"), dict(test="Gloss 60°", value=R.randint(p["glossMin"], p["glossMax"]), spec=f"{p['glossMin']}–{p['glossMax']}", result="PASS")]
        pending = any(t["result"] == "PENDING" for t in tests); fail = any(t["result"] == "FAIL" for t in tests)
        certs.append(dict(id=f"TC-{u['id']}", unitId=u["id"], product=u["product"], gradeId=u["gradeId"], standard="EN 10204 3.1", heatId=u["heatId"], hrCoilId=u["hrCoilId"], tests=tests,
                          status="PENDING" if pending else "FAIL" if fail else "PASS", dftGate=(not pending and not fail) if u["product"] in ("PPGI", "PPGL") else None,
                          issuedAt=None if pending else iso(datetime.fromisoformat(u["producedAt"]) + h(between(2, 8))), hero=(u["id"] == hero_pp["id"])))
    # holds
    holds.append(dict(id=f"HLD-{SEQ.next('hld'):04d}", unitId=hero_pp["id"], level="BATCH", reason="QA — DFT deviation flagged by PDO auto-comparison; lab test pending", heldAt="2026-09-15T02:05:00", heldBy="System (parameter-based hold)",
                      releasedAt=None, releasedBy=None, status="ACTIVE", hero=True))
    for dec in [d for d in decisions if d["udCode"] == "HOLD" and not d["hero"]][:4]:
        rel = R.random() < 0.5
        holds.append(dict(id=f"HLD-{SEQ.next('hld'):04d}", unitId=dec["unitId"], level="BATCH", reason=pick(["Surface inspection review", "Customer sample approval awaited", "Coating weight re-test", "Width tolerance query"]),
                          heldAt=dec["decidedAt"], heldBy=dec["decidedBy"], releasedAt=iso(datetime.fromisoformat(dec["decidedAt"]) + h(between(4, 30))) if rel else None,
                          releasedBy="QC Head — M. Iyer" if rel else None, status="RELEASED" if rel else "ACTIVE", hero=False))
    return dict(defects=defects, decisions=decisions, downgradeSuggestions=suggestions, certificates=certs, holds=holds)
