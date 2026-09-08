"""Integration layer: interface catalogue (SAP 30+, L2, APS, others), 48-hour middleware message log with the scripted
failures (stuck PDI queue, malformed IDoc, contract-version mismatch), alerts, interface contracts with version history."""
from datetime import datetime, timedelta
from .common import R, ASOF, iso, h, m, pick, between, SEQ, at as AT, dstr

SAP = [("Sales order create", "SAP→MES", "IDoc ORDERS05", "Event", "CT-ORDERS05"), ("Sales order amendment", "SAP→MES", "IDoc ORDERS05", "Event", "CT-ORDERS05"), ("Sales order closure", "SAP→MES", "IDoc ORDERS05", "Event", "CT-ORDERS05"),
       ("HR coil requirement", "MES→SAP", "RFC", "Daily 06:00", None), ("RM requirement (zinc, paint, primer)", "MES→SAP", "RFC", "Daily 06:00", None), ("Batch attributes — WIP", "MES→SAP", "IDoc BATMAS", "Event", None),
       ("Batch attributes — FG", "MES→SAP", "IDoc BATMAS", "Event", None), ("Storage location update", "MES→SAP", "IDoc MBGMCR", "Event", None), ("Transfer posting (IDT / repack)", "MES→SAP", "IDoc MBGMCR", "Event", None),
       ("Production confirmation", "MES→SAP", "BAPI COR", "Event", "CT-PRODCONF"), ("Dispatch confirmation", "MES→SAP", "IDoc DELVRY07", "Event", "CT-DISPATCH"), ("Quality update / usage decision", "MES→SAP", "IDoc QMQIN", "Event", None),
       ("FG recall", "SAP→MES", "IDoc", "Event", None), ("Reprocessing order", "SAP→MES", "IDoc LOIPRO", "Event", None), ("Batch allocation / reallocation", "MES→SAP", "RFC", "Event", None),
       ("GRN — HR coils", "SAP→MES", "IDoc MBGMCR", "Event", None), ("GRN — zinc", "SAP→MES", "IDoc MBGMCR", "Event", None), ("GRN — paint & primer", "SAP→MES", "IDoc MBGMCR", "Event", None),
       ("Fuel & utilities consumption", "MES→SAP", "RFC", "Shift-end", None), ("Transit batch information", "SAP→MES", "IDoc", "Event", None), ("GRN transfer — vendor batch replace", "MES→SAP", "RFC", "Event", None),
       ("GRN reversal", "SAP→MES", "IDoc", "Event", None), ("GRN weight — HRS / pickling", "MES→SAP", "RFC", "Event", None), ("Zinc consumption posting", "MES→SAP", "BAPI", "Shift-end", None),
       ("Paint consumption posting", "MES→SAP", "BAPI", "Shift-end", None), ("Consumables posting (acid, guard film)", "MES→SAP", "BAPI", "Shift-end", None), ("PM maintenance orders / windows", "SAP PM→MES", "IDoc", "Event", None),
       ("Downtime notification", "MES→SAP PM", "RFC", "Event", None), ("Vendor packing bill", "MES→SAP MM", "RFC", "Weekly", None), ("Inter-plant transfer", "SAP→MES", "IDoc", "Event", None),
       ("Sales return", "SAP→MES", "IDoc", "Event", None), ("Job work order", "SAP→MES", "IDoc", "Event", None), ("HR batch characteristics (VJNR / DLV)", "SAP→MES", "RFC", "Event", None), ("Dispatched batch information", "SAP→MES", "IDoc", "Event", None)]
L2 = [("SCH", "Line schedule", "MES→L2"), ("PDI", "Production data input (PDI)", "MES→L2"), ("PDIACK", "PDI confirmation / change", "L2→MES"), ("BIP", "Batch in progress", "L2→MES"), ("DT", "Downtime message", "L2→MES"), ("PDO", "Production data output (PDO)", "L2→MES")]
OTHERS = [("IF-APS-FPIN", "Factory Planner input file", "MES→APS", "File (SFTP)", "Daily 04:00", None), ("IF-APS-FPOUT", "Factory Planner output (routes, schedule lines)", "APS→MES", "File (SFTP)", "Daily 05:30", None),
          ("IF-APS-MAIN", "Material Allocator input file", "MES→APS", "File (SFTP)", "Every 4 h", None), ("IF-APS-MAOUT", "Material Allocator output (free stock vs SO)", "APS→MES", "File (SFTP)", "Every 4 h", None),
          ("IF-APS-RUSH", "Rush order flag", "APS→MES", "REST", "Event", None), ("IF-ANA-01", "Anaplan MBP production targets", "Anaplan→MES", "REST", "Monthly", None),
          ("IF-UTL-01", "Utilities meters (power, RLNG, water, H2/N2)", "Utilities→MES", "OPC-UA", "15 min", None), ("IF-SIS-01", "Surface inspection defects", "SIS→MES", "REST", "Event", None)]


def build_interfaces():
    rows = []
    for i, (name, d, proto, trig, ct) in enumerate(SAP, 1):
        rows.append(dict(id=f"IF-SAP-{i:02d}", name=name, system="SAP ECC/S4", direction=d, protocol=proto, trigger=trig, contractId=ct, version=ct and "1.2" or "1.0", slaSec=30, owner="Integration CoE", status="ACTIVE", channel="MES ↔ ESB (middleware) ↔ SAP PI/PO"))
    for code, name, d in L2:
        rows.append(dict(id=f"IF-L2-{code}", name=name, system="L2 process automation", direction=d, protocol="OPC-UA / MQTT via L2 gateway", trigger="Event", contractId="CT-PDI" if code == "PDI" else "CT-PDO" if code == "PDO" else None,
                         version="1.2" if code in ("PDI",) else "1.3" if code == "PDO" else "1.0", slaSec=30, owner="Plant IT / L2 vendor", status="ACTIVE", lines=["PKL", "CRM", "CGL", "CCL"], channel="L2 gateway ↔ middleware ↔ MES"))
    for iid, name, d, proto, trig, ct in OTHERS:
        rows.append(dict(id=iid, name=name, system=iid.split("-")[1], direction=d, protocol=proto, trigger=trig, contractId=ct, version="1.0", slaSec=300 if "File" in proto else 30, owner="Integration CoE", status="ACTIVE", channel="middleware"))
    return rows


def build_messages(pdis, pdos, confs, disps, items):
    msgs, alerts = [], []
    t0 = ASOF - h(48)
    def add(iid, d, at, status, corr, excerpt, err=None, lat=None, hist=None, **kw):
        mm = dict(id=f"MSG-{SEQ.next('msg'):05d}", interfaceId=iid, direction=d, at=iso(at), status=status, latencyMs=lat if lat is not None else R.randint(120, 2800), correlation=corr, payloadExcerpt=excerpt,
                  error=err, retries=0, history=hist or [dict(at=iso(at), status=status, by="middleware")]); mm.update(kw); msgs.append(mm); return mm
    # L2 traffic from execution records within the window
    for p in pdis:
        at = datetime.fromisoformat(p["sentAt"])
        if at < t0: continue
        if p.get("stuck"):
            add("IF-L2-PDI", "MES→L2", at, "IN_QUEUE", dict(po=p["po"], unit=p["unitId"], so=p["soId"], line=p["line"], pdi=p["id"]), {"pdiId": p["id"], "line": p["line"], "targets": p["targets"]},
                err="No consumer on queue L2.CGL.PDI.OUT since 09:41 — L2 gateway subscriber disconnected", lat=None, queue="L2.CGL.PDI.OUT", ageMin=int((ASOF - at).total_seconds() / 60), stuck=True, hero=True)
        else:
            add("IF-L2-PDI", "MES→L2", at, "OK", dict(po=p["po"], unit=p["unitId"], so=p["soId"], line=p["line"], pdi=p["id"]), {"pdiId": p["id"], "line": p["line"], "targets": p["targets"]})
            if p["status"] == "ACKED": add("IF-L2-PDIACK", "L2→MES", datetime.fromisoformat(p["ackAt"]), "OK", dict(po=p["po"], unit=p["unitId"], line=p["line"], pdi=p["id"]), {"pdiId": p["id"], "ack": "ACCEPTED"})
    for p in pdos:
        at = datetime.fromisoformat(p["receivedAt"])
        if at < t0: continue
        if p["line"] == "CCL" and AT(-1, 22, 30) < at < AT(0, 0, 30) and not p["hero"]:
            hist = [dict(at=iso(at), status="FAILED", by="middleware schema validator"), dict(at=iso(AT(-1, 23, 20)), status="CONTRACT_UPDATED", by="Integration CoE — CT-PDO v1.3 activated"), dict(at=iso(AT(-1, 23, 31)), status="REPLAYED", by="AI agent (approved by shift IT lead)")]
            add("IF-L2-PDO", "L2→MES", at, "REPLAYED", dict(po=p["po"], unit=p["unitIn"], so=p["soId"], line="CCL", pdo=p["id"]), {"pdoId": p["id"], "actuals": p["actuals"]},
                err="Schema validation failed: unknown field 'dftBackMeasured' (payload v1.3 vs contract CT-PDO v1.2)", hist=hist, retries=1, contractIssue=True)
            continue
        add("IF-L2-PDO", "L2→MES", at, "OK", dict(po=p["po"], unit=p["unitIn"], so=p["soId"], line=p["line"], pdo=p["id"]), {"pdoId": p["id"], "actuals": p["actuals"], "deviations": p["deviations"]}, hero=p["hero"])
        add("IF-L2-BIP", "L2→MES", at - m(R.randint(10, 60)), "OK", dict(po=p["po"], unit=p["unitIn"], line=p["line"]), {"event": "BATCH_IN_PROGRESS", "unit": p["unitIn"], "pctDone": R.randint(30, 90)})
    for c in confs:
        at = datetime.fromisoformat(c["end"]) + m(R.randint(2, 9))
        if at < t0: continue
        if R.random() < 0.06 and not c["hero"]:
            hist = [dict(at=iso(at), status="FAILED", by="SAP"), dict(at=iso(at + m(R.randint(6, 25))), status="OK", by="AI agent auto-retry (autonomous action A-04)")]
            add("IF-SAP-10", "MES→SAP", at, "REPLAYED", dict(po=c["po"], unit=c["unitIn"], so=c["soId"], line=c["line"], pc=c["id"]), {"pc": c["id"], "yieldPct": c["yieldPct"], "outMT": c["outWeightMT"]},
                err="SAP COR: order locked by user PPC_KHP01 (transaction CO02) — posting rejected", hist=hist, retries=1)
        else:
            add("IF-SAP-10", "MES→SAP", at, "OK", dict(po=c["po"], unit=c["unitIn"], so=c["soId"], line=c["line"], pc=c["id"]), {"pc": c["id"], "yieldPct": c["yieldPct"], "outMT": c["outWeightMT"], "sapDoc": c["sapDoc"]}, hero=c["hero"])
            add("IF-SAP-06" if c["line"] not in ("CGL", "CCL", "PKG") else "IF-SAP-07", "MES→SAP", at + m(1), "OK", dict(po=c["po"], unit=c["unitsOut"][0], so=c["soId"]), {"batch": c["unitsOut"][0], "attributes": "thk/width/weight/coating"})
    for d in disps:
        if d["status"] != "DISPATCHED": continue
        at = datetime.fromisoformat(d["dispatchedAt"]) + m(3)
        if at >= t0: add("IF-SAP-11", "MES→SAP", at, "OK", dict(dispatch=d["id"], so=d["soId"], pack=d["packId"]), {"dispatchId": d["id"], "vehicle": d["vehicle"], "netMT": d["weightMT"]})
    # background SAP / APS / utilities traffic
    for i in range(70):
        at = t0 + h(between(0, 47.5)); iid = pick(["IF-SAP-01", "IF-SAP-08", "IF-SAP-16", "IF-SAP-24", "IF-SAP-25", "IF-SAP-19", "IF-SAP-33", "IF-UTL-01", "IF-SIS-01", "IF-APS-MAOUT", "IF-APS-FPOUT", "IF-L2-DT", "IF-L2-SCH"])
        it = pick(items)
        add(iid, "SAP→MES" if iid in ("IF-SAP-01", "IF-SAP-16", "IF-SAP-33") else "MES→SAP" if iid.startswith("IF-SAP") else "→MES", at, "OK", dict(so=it["soId"]), {"ref": it["id"], "note": "routine"})
    # scripted: malformed sales-order amendment IDoc (S5 / S7)
    add("IF-SAP-02", "SAP→MES", AT(0, 8, 12), "FAILED", dict(so="4213090022", item="10", idoc="0000001187734"), {"idoc": "ORDERS05", "E1EDK01": {"BELNR": "4213090022"}, "E1EDP01": {"POSEX": "000010", "MENGE": "210.000"}, "E1EDP20": {"EDATU": "2026-13-02", "WMENG": "210.000"}},
        err="IDoc 0000001187734 segment E1EDP20 field EDATU '2026-13-02' is not a valid date (expected YYYY-MM-DD) — status 51 (application error)", lat=None, retries=2, hero=True, idoc="0000001187734",
        hist=[dict(at=iso(AT(0, 8, 12, 4)), status="FAILED", by="middleware mapping"), dict(at=iso(AT(0, 8, 15)), status="RETRY_FAILED", by="auto-retry"), dict(at=iso(AT(0, 8, 30)), status="RETRY_FAILED", by="auto-retry")])
    if not any(x.get("contractIssue") for x in msgs):
        # guarantee the contract-version scenario even if no CCL PDO fell in that window
        ref = next((p for p in pdos if p["line"] == "CCL" and not p["hero"]), None) or dict(po="PO-KHP-2609-0000", unitIn="GIC-KHP-2609-0000", soId="4213090005", id="PDO-CCL-0000", actuals={})
        hist = [dict(at=iso(AT(-1, 23, 5)), status="FAILED", by="middleware schema validator"), dict(at=iso(AT(-1, 23, 20)), status="CONTRACT_UPDATED", by="Integration CoE — CT-PDO v1.3 activated"), dict(at=iso(AT(-1, 23, 31)), status="REPLAYED", by="AI agent (approved by Integration CoE on-call)")]
        add("IF-L2-PDO", "L2→MES", AT(-1, 23, 5), "REPLAYED", dict(po=ref["po"], unit=ref["unitIn"], so=ref["soId"], line="CCL", pdo=ref["id"]), {"pdoId": ref["id"], "actuals": ref.get("actuals", {}), "dftBackMeasured": 7.2},
            err="Schema validation failed: unknown field 'dftBackMeasured' (payload v1.3 vs contract CT-PDO v1.2)", hist=hist, retries=1, contractIssue=True)
    msgs.sort(key=lambda x: x["at"])
    stuck = [x for x in msgs if x.get("stuck")]
    alerts.append(dict(id="ALR-0001", severity="S1", interfaceId="IF-L2-PDI", raisedAt=iso(AT(0, 9, 43)), status="OPEN", title="PDI queue L2.CGL.PDI.OUT stuck",
                       detail=f"Queue depth {len(stuck)} > 0 for 120 s; oldest message age exceeds 30 s SLA; no consumer heartbeat since 09:41", messageIds=[x["id"] for x in stuck], incidentId="INC-26-0412", channel="Monitoring → ITSM → Teams"))
    bad = next(x for x in msgs if x.get("idoc"))
    alerts.append(dict(id="ALR-0002", severity="S2", interfaceId="IF-SAP-02", raisedAt=iso(AT(0, 8, 31)), status="OPEN", title="Sales-order amendment IDoc failed after 2 retries",
                       detail="IDoc 0000001187734 for SO 4213090022/10 in status 51 — order quantity change 180 → 210 t not applied in MES", messageIds=[bad["id"]], incidentId="INC-26-0413", channel="Monitoring → ITSM → Teams"))
    rep = next((x for x in msgs if x.get("contractIssue")), None)
    if rep: alerts.append(dict(id="ALR-0003", severity="S2", interfaceId="IF-L2-PDO", raisedAt=iso(AT(-1, 23, 6)), status="RESOLVED", resolvedAt=iso(AT(-1, 23, 32)), title="PDO rejected — contract version mismatch",
                              detail="CCL L2 upgraded to PDO payload v1.3 (adds dftBackMeasured) while MES contract CT-PDO was v1.2; v1.3 activated and message replayed", messageIds=[rep["id"]], incidentId="INC-26-0409", channel="Monitoring → ITSM"))
    return msgs, alerts


def build_contracts():
    def f(n, t, req, d): return dict(name=n, type=t, required=req, description=d)
    return [
        dict(id="CT-PDI", name="Production Data Input (MES → L2)", interfaceIds=["IF-L2-PDI"], currentVersion="1.2", format="JSON over MQTT (L2 gateway)",
             versions=[dict(version="1.0", date="2026-03-02", status="RETIRED", changes="Initial: batch, PO, targets per line", approvedBy="Integration CoE"), dict(version="1.1", date="2026-05-18", status="RETIRED", changes="Add zincBathAlPct band (CGL)", approvedBy="Integration CoE"),
                       dict(version="1.2", date="2026-08-04", status="ACTIVE", changes="Add coatingBandGsm [min,max] and passivation; dftBackUm for CCL", approvedBy="Integration CoE / Plant IT")],
             fields=[f("pdiId", "string", True, "MES message id"), f("line", "enum PKL|CRM|CGL|CCL", True, "Target line"), f("po", "string", True, "MES production order"), f("unitId", "string", True, "Input coil id"),
                     f("targets", "object", True, "Line-specific set-points (see per-line sub-schema)"), f("sentAt", "datetime", True, "ISO-8601"), f("version", "string", True, "Contract version")]),
        dict(id="CT-PDO", name="Production Data Output (L2 → MES)", interfaceIds=["IF-L2-PDO"], currentVersion="1.3", format="JSON over MQTT (L2 gateway)",
             versions=[dict(version="1.1", date="2026-05-18", status="RETIRED", changes="Add coatingTop/BottomGsm", approvedBy="Integration CoE"), dict(version="1.2", date="2026-08-04", status="RETIRED", changes="Add dE colour difference (CCL)", approvedBy="Integration CoE"),
                       dict(version="1.3", date=dstr(-1), status="ACTIVE", changes="Add dftBackMeasured (CCL back-coat gauge) — activated 23:20 after L2 upgrade rejected messages", approvedBy="Integration CoE (emergency CAB)")],
             fields=[f("pdoId", "string", True, "L2 message id"), f("pdiId", "string", True, "Correlates to PDI"), f("actuals", "object", True, "Measured values per line"), f("outWeightMT", "number", True, "Weighed output"),
                     f("lengthM", "number", False, "Strip length"), f("dftBackMeasured", "number", False, "v1.3: back-coat DFT µm"), f("receivedAt", "datetime", True, "ISO-8601")]),
        dict(id="CT-ORDERS05", name="Sales order IDoc mapping (SAP → MES)", interfaceIds=["IF-SAP-01", "IF-SAP-02", "IF-SAP-03"], currentVersion="2.1", format="IDoc ORDERS05 → canonical SalesOrder (ISA-95 aligned)",
             versions=[dict(version="2.0", date="2026-02-10", status="RETIRED", changes="Schedule-line level (E1EDP20) mapping", approvedBy="Integration CoE"), dict(version="2.1", date="2026-07-22", status="ACTIVE", changes="TDC / variant-configuration characteristics (E1CUCFG) mapped to MES TDC", approvedBy="Integration CoE")],
             fields=[f("E1EDK01.BELNR", "string", True, "SAP sales order"), f("E1EDP01.POSEX", "string", True, "Item"), f("E1EDP20.EDATU", "date", True, "Schedule line date (YYYY-MM-DD)"), f("E1EDP20.WMENG", "number", True, "Schedule line qty (t)"),
                     f("E1CUCFG.*", "list", False, "VC characteristics → TDC")]),
        dict(id="CT-DISPATCH", name="Dispatch confirmation (MES → SAP)", interfaceIds=["IF-SAP-11"], currentVersion="1.2", format="Canonical DispatchConfirmation → IDoc DELVRY07 / SHPCON",
             versions=[dict(version="1.0", date="2026-03-02", status="RETIRED", changes="Initial", approvedBy="Integration CoE"), dict(version="1.2", date="2026-08-20", status="ACTIVE", changes="Add packType, testCertificate, qualityStatus (dispatch gate)", approvedBy="Integration CoE")],
             fields=[f("header.dispatchId", "string", True, "MES dispatch id"), f("header.salesOrder/soItem/scheduleLine", "string", True, "Fulfils"), f("items[].batch", "string", True, "Pack / batch id"), f("items[].qtyMT", "number", True, "Net weight"),
                     f("items[].qualityStatus", "enum", True, "Must be CLEARED (DFT gate for colour-coated)")]),
        dict(id="CT-PRODCONF", name="Production confirmation (MES → SAP)", interfaceIds=["IF-SAP-10"], currentVersion="1.1", format="BAPI_PRODORDCONF_CREATE_TT",
             versions=[dict(version="1.1", date="2026-06-15", status="ACTIVE", changes="Scrap break-up and unaccounted loss fields", approvedBy="Integration CoE")],
             fields=[f("po", "string", True, "MES/SAP production order"), f("inWeightMT/outWeightMT/scrapMT", "number", True, "Mass balance"), f("unaccountedMT", "number", False, "Flagged when > 0.1 t")]),
    ]
