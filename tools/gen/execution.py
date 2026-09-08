"""Shop-floor execution transactions from the simulated stages: PDI/PDO (L2 via middleware), production confirmations
with mass balance, slit plans, packing units + vendor bills, dispatches (+ SAP dispatch message)."""
from datetime import datetime, timedelta
from .common import R, ASOF, BASE, iso, day, h, m, pick, between, r1, r2, shift_of, SEQ, at as AT
from .assets_specs import COATINGS, PAINTS, PACK_VENDORS
from .threads import LINE

L2_LINES = ("PKL", "CRM", "CGL", "CCL")
OPERATORS = ["R. Patil", "S. Kadam", "A. Shinde", "M. Jadhav", "P. More", "V. Gaikwad", "D. Pawar", "K. Sawant"]


def _targets(line, it, unit):
    if line == "PKL":
        return dict(acidConcPct=[12, 16], stripSpeedMpm=90 if unit["thk"] > 3 else 120, bathTempC=80, oilingGsm=1.2, sideTrimMm=10)
    if line == "CRM":
        return dict(exitThkMm=it["thk"], thkTolMm=0.03 if it["thk"] < 1 else 0.05, passes=5 if it["thk"] < 0.6 else 4, reductionPct=r1((1 - it["thk"] / unit["thk"]) * 100), rollForceKN=[9500, 11500])
    if line == "CGL":
        c = next(x for x in COATINGS if x["id"] == it["coatingId"])
        return dict(coatingId=c["id"], coatingTargetGsm=c["target"], coatingBandGsm=[c["bandMin"], c["bandMax"]], spangle=c["spangle"], lineSpeedMpm=110 if it["thk"] < 0.6 else 90,
                    furnaceSoakC=720, zincBathAlPct=[0.18, 0.24], bathTempC=460, skinPassElongPct=[0.8, 1.2], passivation="Chromate")
    if line == "CCL":
        p = next(x for x in PAINTS if x["id"] == it["paintId"])
        return dict(paintId=p["id"], ral=it["ral"], primerUm=p["primerUm"], dftTopUm=it["dftTop"], dftTopTolUm=it["dftTol"], dftBackUm=it["dftBack"], dftBackTolUm=2,
                    pmtC=p["pmtC"], lineSpeedMpm=60, glossRange=[p["glossMin"], p["glossMax"]], guardFilm=True)
    return {}


def _actuals(line, tg, hero, dev):
    """actual PDO values around targets; 'dev' forces one flagged deviation"""
    a, flags = {}, []
    if line == "PKL":
        a = dict(acidConcPct=r1(between(12.5, 15.5)), stripSpeedMpm=tg["stripSpeedMpm"] - R.randint(0, 8), bathTempC=R.randint(78, 83), oilingGsm=r2(between(1.0, 1.4)))
        if dev: a["acidConcPct"] = 11.2; flags.append(("acidConcPct", "below 12 % band"))
    elif line == "CRM":
        a = dict(exitThkMm=r2(tg["exitThkMm"] + between(-0.01, 0.01)), passes=tg["passes"], reductionPct=tg["reductionPct"], rollForceKN=R.randint(9600, 11400))
        if dev: a["exitThkMm"] = r2(tg["exitThkMm"] + tg["thkTolMm"] + 0.02); flags.append(("exitThkMm", f"outside ±{tg['thkTolMm']} mm"))
    elif line == "CGL":
        lo, hi = tg["coatingBandGsm"]
        a = dict(coatingTopGsm=r1(between(lo, hi) / 2 + between(-1, 1)), coatingBottomGsm=None, lineSpeedMpm=tg["lineSpeedMpm"] - R.randint(0, 12),
                 furnaceSoakC=R.randint(714, 726), zincBathAlPct=r2(between(0.19, 0.23)), bathTempC=R.randint(458, 463), skinPassElongPct=r2(between(0.85, 1.15)))
        a["coatingBottomGsm"] = r1(a["coatingTopGsm"] + between(-3, 3)); a["coatingTotalGsm"] = r1(a["coatingTopGsm"] + a["coatingBottomGsm"])
        if hero: a.update(coatingTopGsm=63.6, coatingBottomGsm=63.2, coatingTotalGsm=126.8, zincBathAlPct=0.21, lineSpeedMpm=96, furnaceSoakC=719)
        if a["coatingTotalGsm"] < lo or a["coatingTotalGsm"] > hi: flags.append(("coatingTotalGsm", f"outside band {lo}–{hi} g/m²"))
        if dev and not flags: a["coatingTotalGsm"] = r1(lo - between(3, 8)); flags.append(("coatingTotalGsm", f"below band min {lo} g/m²"))
        if hero: flags.append(("lineSpeedMpm", "12% below target speed (throughput only, not a spec deviation)"))
    elif line == "CCL":
        a = dict(dftTopUm=r1(tg["dftTopUm"] + between(-1.5, 1.5)), dftBackUm=r1(tg["dftBackUm"] + between(-1, 1)), pmtC=tg["pmtC"] + R.randint(-4, 4),
                 lineSpeedMpm=tg["lineSpeedMpm"] - R.randint(0, 6), gloss60=R.randint(tg["glossRange"][0], tg["glossRange"][1]), dE=r2(between(0.2, 0.9)))
        if hero: a.update(dftTopUm=16.8, dftBackUm=7.1, pmtC=231, lineSpeedMpm=58, gloss60=34, dE=0.6)
        if abs(a["dftTopUm"] - tg["dftTopUm"]) > tg["dftTopTolUm"]: flags.append(("dftTopUm", f"outside {tg['dftTopUm']} ±{tg['dftTopTolUm']} µm"))
        if dev and not flags: a["dE"] = 1.8; flags.append(("dE", "colour difference > 1.2"))
    return a, [dict(field=f, note=n, severity="WARN" if "throughput" in n else "DEVIATION") for f, n in flags]


def build_execution(stages, materials, items, threads):
    by_unit = {u["id"]: u for u in materials}; by_item = {it["id"]: it for it in items}
    pdis, pdos, confs, slits, packs, bills, disps = [], [], [], [], [], [], []
    imbalance_done = False
    for st in stages:
        it = by_item[st["itemId"]]; ln = st["line"]; unit = by_unit.get(st["inUnit"]) or dict(thk=it["thk"], width=it["width"])
        s, e = datetime.fromisoformat(st["start"]), datetime.fromisoformat(st["end"])
        if ln in L2_LINES and (st["status"] != "PLANNED" or s <= ASOF + h(48)):
            tg = _targets(ln, it, unit)
            pdi = dict(id=f"PDI-{ln}-{SEQ.next('pdi-' + ln):04d}", line=ln, po=st["po"], unitId=st["inUnit"], itemId=it["id"], soId=it["soId"], threadId=st["threadId"],
                       sentAt=iso(s - m(R.randint(20, 90))), targets=tg, status="ACKED" if st["status"] != "PLANNED" else "SENT", ackAt=None, hero=st["hero"], via="Middleware (L2 gateway)")
            if pdi["status"] == "ACKED": pdi["ackAt"] = iso(datetime.fromisoformat(pdi["sentAt"]) + m(R.randint(1, 4)))
            if ln == "CGL" and st["status"] == "PLANNED" and ASOF + h(0.5) <= s <= ASOF + h(9):
                pdi.update(status="IN_QUEUE", sentAt=iso(ASOF - m(R.randint(30, 49))), stuck=True, queue="L2.CGL.PDI.OUT")   # stuck PDI queue (S5 / S7)
            st["pdiId"] = pdi["id"]; pdis.append(pdi)
            if st["status"] == "DONE":
                dev = (R.random() < 0.08) and not st["hero"]
                act, flags = _actuals(ln, tg, st["hero"], dev)
                pdo = dict(id=f"PDO-{ln}-{SEQ.next('pdo-' + ln):04d}", pdiId=pdi["id"], line=ln, po=st["po"], unitIn=st["inUnit"], unitsOut=st["outUnits"], itemId=it["id"], soId=it["soId"],
                           threadId=st["threadId"], receivedAt=iso(e + m(R.randint(1, 3))), actuals=act, deviations=flags, status="ACCEPTED" if not [f for f in flags if f["severity"] == "DEVIATION"] else "ACCEPTED_WITH_DEVIATION",
                           inWeightMT=st["inWeight"], outWeightMT=st["outWeight"], lengthM=int(st["outWeight"] * 1000 / (7.85 * it["thk"] * (it["width"] / 1000)) ) if it["thk"] else None, hero=st["hero"], via="Middleware (L2 gateway)")
                st["pdoId"] = pdo["id"]; pdos.append(pdo)
        if st["status"] == "DONE":
            inw, outw, scrap = st["inWeight"], st["outWeight"], st["scrap"]
            loss = 0.0
            if ln == "CRM" and not st["hero"] and not imbalance_done and s > BASE + timedelta(days=2):
                loss = 0.62; outw = r2(outw - loss); imbalance_done = True   # deliberate unaccounted loss -> flagged
            conf = dict(id=f"PC-{ln}-{SEQ.next('pc-' + ln):04d}", line=ln, po=st["po"], unitIn=st["inUnit"], unitsOut=st["outUnits"], itemId=it["id"], soId=it["soId"], threadId=st["threadId"],
                        start=st["start"], end=st["end"], shift=shift_of(s), operator=pick(OPERATORS), inWeightMT=inw, outWeightMT=outw, scrapMT=scrap,
                        scrapBreakup={"headTailCrop": r2(scrap * 0.55), "edgeTrim": r2(scrap * 0.35), "sampling": r2(scrap * 0.10)} if ln in ("PKL", "CRM", "SLT", "RWL") else {"headTailCrop": r2(scrap * 0.7), "rejectWraps": r2(scrap * 0.3)},
                        unaccountedMT=r2(loss), massBalance="IMBALANCE" if loss > 0.1 else "OK", yieldPct=r1(outw / inw * 100), postedToSAP=True, sapDoc=f"COR-{R.randint(4000000, 4999999)}",
                        hero=st["hero"], ontologyDomain="PROCESS")
            if ln == "PKG": conf["postedToSAP"] = True
            confs.append(conf)
    # guarantee the stuck-queue scenario: at least 3 CGL PDIs waiting in L2.CGL.PDI.OUT
    stuck = [p for p in pdis if p.get("stuck")]
    if len(stuck) < 3:
        have = {p["po"] for p in pdis}
        cand = sorted([s for s in stages if s["line"] == "CGL" and s["status"] == "PLANNED"], key=lambda s: s["start"])
        k = len(stuck)
        for st in cand:
            if k >= 3: break
            p = next((x for x in pdis if x["po"] == st["po"]), None)
            if p is None:
                it = by_item[st["itemId"]]; unit = by_unit.get(st["inUnit"]) or dict(thk=it["thk"], width=it["width"])
                p = dict(id=f"PDI-CGL-{SEQ.next('pdi-CGL'):04d}", line="CGL", po=st["po"], unitId=st["inUnit"], itemId=it["id"], soId=it["soId"], threadId=st["threadId"], targets=_targets("CGL", it, unit), ackAt=None, hero=st["hero"], via="Middleware (L2 gateway)")
                st["pdiId"] = p["id"]; pdis.append(p)
            if p.get("stuck"): continue
            p.update(status="IN_QUEUE", sentAt=iso(ASOF - m(49 - 6 * k)), stuck=True, queue="L2.CGL.PDI.OUT"); k += 1
    # slit plans
    for st in stages:
        if st["line"] != "SLT": continue
        it = by_item[st["itemId"]]; ws = it.get("slitWidths") or [(it["width"] - 20) // 2] * 2
        slits.append(dict(id=f"SLP-{SEQ.next('slp'):04d}", po=st["po"], parentUnit=st["inUnit"], itemId=it["id"], soId=it["soId"], parentWidth=it["width"], widths=ws,
                          trimMm=it["width"] - sum(ws), childUnits=st["outUnits"], status={"DONE": "EXECUTED", "IN_PROGRESS": "RUNNING", "PLANNED": "PLANNED"}[st["status"]],
                          plannedStart=st["start"], knifeSetup=f"{len(ws)} cuts · {ws[0]} mm", hero=st["hero"]))
    # packing units, bills, dispatches
    for st in stages:
        if st["line"] != "PKG": continue
        it = by_item[st["itemId"]]; pk = by_unit[st["outUnits"][0]]; v = next(x for x in PACK_VENDORS if x["id"] == pk.get("vendorId", "V01"))
        packs.append(dict(id=pk["id"], po=st["po"], itemId=it["id"], soId=it["soId"], customerName=it["customerName"], units=pk.get("packsUnits", [st["inUnit"]]), weightMT=pk["weightMT"],
                          packType="Export seaworthy" if it["packing"] == "EXP" else "Domestic VCI + stretch", vendorId=v["id"], vendorName=v["name"], ratePerT=v["rateExp"] if it["packing"] == "EXP" else v["rateDom"],
                          materials=["VCI paper", "Stretch film", "Wooden skid", "PET strap"] + (["Steel outer wrap", "Silica gel"] if it["packing"] == "EXP" else []),
                          packedAt=st["end"] if st["status"] == "DONE" else None, plannedAt=st["end"], status={"DONE": "PACKED", "IN_PROGRESS": "PACKING", "PLANNED": "PLANNED"}[st["status"]],
                          labelQr=f"KHP|{pk['id']}|{it['soId']}|{pk['weightMT']}", hero=st["hero"]))
    for p in packs:
        if p["status"] != "PACKED": continue
        packed = datetime.fromisoformat(p["packedAt"]); dd = packed + h(between(6, 36))
        d = dict(id=f"DSP-{SEQ.next('dsp'):04d}", packId=p["id"], itemId=p["itemId"], soId=p["soId"], customerName=p["customerName"], weightMT=p["weightMT"],
                 vehicle=f"MH-{R.randint(10, 48):02d}-{pick('ABCDEFGH')}{pick('ABCDEFGH')}-{R.randint(1000, 9999)}", plannedAt=iso(dd), dispatchedAt=iso(dd) if dd <= ASOF else None,
                 status="DISPATCHED" if dd <= ASOF else "PLANNED", invoice=f"INV-KHP-{R.randint(260000, 269999)}" if dd <= ASOF else None, hero=p["hero"])
        disps.append(d)
    hero_pack = next((p for p in packs if p["hero"]), None)
    if hero_pack:
        disps.append(dict(id=f"DSP-{SEQ.next('dsp'):04d}", packId=hero_pack["id"], itemId=hero_pack["itemId"], soId=hero_pack["soId"], customerName=hero_pack["customerName"],
                          weightMT=hero_pack["weightMT"], vehicle="MH-12-KT-4471", plannedAt=iso(AT(2, 10, 0)), dispatchedAt=None, status="PLANNED", invoice=None, hero=True))
    # vendor-wise packing bill per ISO week
    agg = {}
    for p in packs:
        if p["status"] != "PACKED": continue
        wk = datetime.fromisoformat(p["packedAt"]).isocalendar()[1]; k = (p["vendorId"], wk)
        a = agg.setdefault(k, dict(vendorId=p["vendorId"], vendorName=p["vendorName"], week=f"2026-W{wk}", packs=0, weightMT=0.0, amountINR=0.0, export=0, domestic=0))
        a["packs"] += 1; a["weightMT"] = r2(a["weightMT"] + p["weightMT"]); a["amountINR"] = round(a["amountINR"] + p["weightMT"] * p["ratePerT"]); a["export" if "Export" in p["packType"] else "domestic"] += 1
    bills = sorted(agg.values(), key=lambda x: (x["week"], x["vendorId"]))
    for b in bills: b["id"] = f"PBILL-{b['vendorId']}-{b['week']}"; b["status"] = "POSTED" if b["week"] < f"2026-W{ASOF.isocalendar()[1]}" else "OPEN"
    return dict(pdi=pdis, pdo=pdos, confirmations=confs, slitPlans=slits, packs=packs, packingBills=bills, dispatches=disps)


def sap_dispatch_message(d, pack, it):
    return {"messageType": "MES_DISPATCH_CONFIRMATION", "interface": "IF-SAP-11", "version": "1.2", "header": {"plant": "KHP", "dispatchId": d["id"], "salesOrder": it["soId"], "soItem": it["item"],
            "scheduleLine": it["scheduleLines"][0]["id"], "customer": it["customerId"], "vehicle": d["vehicle"], "dispatchDate": d["plannedAt"][:10], "shippingPoint": "KHP1", "incoterm": "FOR"},
            "items": [{"batch": pack["id"], "material": f"{it['product']}-{it['gradeId']}-{it['thk']:.2f}x{it['width']}", "qtyMT": pack["weightMT"], "coils": pack["units"], "packType": pack["packType"],
                       "testCertificate": "EN 10204 3.1", "qualityStatus": "CLEARED"}],
            "totals": {"packs": 1, "grossMT": r2(pack["weightMT"] + 0.12), "netMT": pack["weightMT"]}, "middleware": {"channel": "MES->ESB->SAP", "idoc": "DELVRY07 / SHPCON", "correlationId": f"CORR-{d['id']}"}}
