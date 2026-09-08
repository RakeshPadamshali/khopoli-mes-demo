"""Scenario 7 data feed (AI-agent L1/L2 support): incidents, runbooks / known errors, action catalogue, agent audit log, MI metrics."""
from datetime import datetime, timedelta
from .common import R, ASOF, iso, h, m, pick, between, r1, SEQ, at as AT, dstr

RUNBOOKS = [
    dict(id="RB-001", title="Stuck PDI queue on L2 gateway", symptoms=["Queue depth > 0 for > 120 s", "No consumer heartbeat", "PDI status IN_QUEUE, line cannot charge"], category="Interface / L2",
         diagnosis=["Check consumer heartbeat on L2 gateway", "Confirm MES publisher healthy (last publish time)", "Inspect queue age and depth", "Correlate with L2 downtime message"],
         remediation=["Restart L2 gateway subscriber service (autonomous)", "Replay queued PDI messages oldest-first (approval if > 5 messages)", "Validate ACK received per PDI"], autonomy="AUTONOMOUS_RESTART + APPROVAL_FOR_REPLAY", knownErrorId="KE-0031", owner="Plant IT"),
    dict(id="RB-002", title="SAP IDoc ORDERS05 in status 51 (application error)", symptoms=["IDoc failed after retries", "Amendment not reflected in MES order", "Alert from middleware mapping"], category="Interface / SAP",
         diagnosis=["Read IDoc status text", "Identify offending segment/field", "Check if mapping or source data error"], remediation=["If source data error: request SAP re-send with corrected values (approval: SAP SD key user)", "If mapping error: raise change to Integration CoE", "Never patch dates manually in MES"], autonomy="APPROVAL", knownErrorId="KE-0014", owner="SAP SD key user"),
    dict(id="RB-003", title="PDO rejected — contract version mismatch", symptoms=["Schema validation failed: unknown field", "L2 vendor upgrade without CAB"], category="Interface / L2", diagnosis=["Compare payload version vs active contract", "Check contract registry"], remediation=["Activate compatible contract version (CAB approval)", "Replay rejected messages"], autonomy="APPROVAL", knownErrorId="KE-0027", owner="Integration CoE"),
    dict(id="RB-004", title="Production confirmation posting failure (SAP COR)", symptoms=["BAPI returns order locked / period closed"], category="Interface / SAP", diagnosis=["Read BAPI return", "Check lock owner"], remediation=["Auto-retry after 5 min up to 3 times (autonomous)", "Escalate lock owner if persists"], autonomy="AUTONOMOUS_RETRY", knownErrorId="KE-0008", owner="Plant IT"),
    dict(id="RB-005", title="Data load NULL / constraint error on batch attributes", symptoms=["Batch attribute interface fails with NOT NULL"], category="Data", diagnosis=["Identify missing attribute", "Check master mapping"], remediation=["Data correction under approval workflow", "Fix master mapping"], autonomy="APPROVAL", knownErrorId="KE-0019", owner="MES functional"),
    dict(id="RB-006", title="User access / role assignment request", symptoms=["User cannot see page/button"], category="Access", diagnosis=["Check role + unit/line assignment"], remediation=["Assign role per policy (autonomous within policy)"], autonomy="AUTONOMOUS_WITHIN_POLICY", knownErrorId=None, owner="MES admin"),
    dict(id="RB-007", title="Label printer offline at packing", symptoms=["Sticker print fails", "Printer status OFFLINE"], category="Shop-floor IT", diagnosis=["Ping printer", "Check spooler"], remediation=["Restart spooler (autonomous)", "Switch to backup printer", "Dispatch field engineer"], autonomy="AUTONOMOUS", knownErrorId="KE-0022", owner="Plant IT"),
    dict(id="RB-008", title="Mass balance mismatch reconciliation", symptoms=["Confirmation flagged IMBALANCE"], category="Data / process", diagnosis=["Compare scale readings", "Check crop/scrap entries"], remediation=["Reconcile with shift in-charge; data correction under approval"], autonomy="APPROVAL", knownErrorId=None, owner="PPC"),
]
ACTIONS = [
    dict(id="A-01", action="Read application / middleware / L2 logs", level="AUTONOMOUS", scope="Read-only"), dict(id="A-02", action="Correlate messages by batch / PO / SO id", level="AUTONOMOUS", scope="Read-only"),
    dict(id="A-03", action="Run read-only diagnostic queries", level="AUTONOMOUS", scope="Read-only DB role"), dict(id="A-04", action="Retry a failed SAP posting (≤ 3 attempts)", level="AUTONOMOUS", scope="Parameterised"),
    dict(id="A-05", action="Restart L2 gateway subscriber / print spooler", level="AUTONOMOUS", scope="Parameterised, non-production-data"), dict(id="A-06", action="Notify user / update ticket / close with confirmation", level="AUTONOMOUS", scope="ITSM"),
    dict(id="A-07", action="Replay queued or failed interface messages (> 5)", level="APPROVAL", scope="Shift IT lead"), dict(id="A-08", action="Activate a new interface contract version", level="APPROVAL", scope="Integration CoE / CAB"),
    dict(id="A-09", action="Data correction on batch attributes / weights", level="APPROVAL", scope="MES functional + PPC"), dict(id="A-10", action="Configuration change (masters, rules)", level="APPROVAL", scope="Change control"),
    dict(id="A-11", action="Restart MES core service", level="APPROVAL", scope="Plant IT lead"), dict(id="A-12", action="Direct write to production database", level="PROHIBITED", scope="—"),
    dict(id="A-13", action="Delete or back-date production / quality records", level="PROHIBITED", scope="—"), dict(id="A-14", action="Change SAP master data or disable an interface", level="PROHIBITED", scope="—"),
]
TITLES = [("Interface / L2", "PDI not acknowledged on {line}", "RB-001", "S2"), ("Interface / SAP", "Production confirmation rejected by SAP (order locked)", "RB-004", "S3"), ("Interface / SAP", "Batch attribute IDoc failed — NULL coating value", "RB-005", "S3"),
          ("Access", "New shift in-charge cannot open Delay entry page", "RB-006", "S4"), ("Shop-floor IT", "Label printer offline at packing line", "RB-007", "S3"), ("How-to", "How to record offline production entry", None, "S4"),
          ("Data / process", "Mass balance flagged on CRM confirmation", "RB-008", "S3"), ("Interface / L2", "PDO missing for coil on CGL", "RB-003", "S2"), ("Interface / SAP", "GRN weight mismatch HRS", "RB-005", "S3"), ("How-to", "Query: batch swap between two SOs", None, "S4")]


def build_support(alerts):
    incidents, audit = [], []
    t0 = ASOF - timedelta(days=30)
    for i in range(28):
        cat, title, rb, sev = pick(TITLES)
        at = t0 + h(between(0, 29 * 24)); title = title.replace("{line}", pick(["PKL", "CRM", "CGL", "CCL"]))
        agent = R.random() < (0.72 if rb else 0.55); needs_appr = rb in ("RB-002", "RB-003", "RB-005", "RB-008")
        mttr = {"S1": R.randint(8, 40), "S2": R.randint(15, 90), "S3": R.randint(30, 300), "S4": R.randint(20, 480)}[sev]
        if not agent: mttr = int(mttr * between(1.6, 3.2))
        incidents.append(dict(id=f"INC-26-{380 + i:04d}", title=title, category=cat, severity=sev, channel=pick(["Teams chat", "ITSM portal", "Monitoring alert", "Email"]), openedAt=iso(at), openedBy="Monitoring" if R.random() < 0.4 else pick(["Shift in-charge", "PPC", "QC", "Packing supervisor"]),
                              classification=dict(by="AI agent", confidence=round(between(0.82, 0.98), 2), category=cat), enrichment=dict(batchIds=[f"GIC-KHP-2609-{R.randint(1, 60):04d}"] if "coil" in title.lower() or "PDI" in title or "PDO" in title else [], interfaceLogs=R.randint(0, 6), line=pick(["PKL", "CRM", "CGL", "CCL", "SLT", "PKG"])),
                              knowledgeSource=rb, proposedAction=(next(r for r in RUNBOOKS if r["id"] == rb)["remediation"][0] if rb else "Guided answer from SOP"), approvalRequired=needs_appr, approvedBy=("Shift IT lead" if needs_appr else None),
                              resolvedBy="AI agent" if agent else "Human L2 engineer", validation="Automated post-fix check passed" if agent else "Manual verification", resolvedAt=iso(at + m(mttr)), mttrMin=mttr, status="RESOLVED",
                              falseAction=(R.random() < 0.04 and agent), csat=pick([4, 5, 5, 5, 3]), hero=False))
    # hero incident 1: stuck PDI queue — resolved by agent with human approval for replay
    a1 = next(a for a in alerts if a["id"] == "ALR-0001")
    incidents.append(dict(id="INC-26-0412", title="Stuck PDI queue L2.CGL.PDI.OUT — CGL cannot charge next coil", category="Interface / L2", severity="S1", channel="Monitoring alert → ITSM → Teams", openedAt=iso(AT(0, 9, 43)), openedBy="Monitoring (ALR-0001)",
                          classification=dict(by="AI agent", confidence=0.96, category="Interface / L2 — stuck queue"), enrichment=dict(batchIds=[], interfaceLogs=3, line="CGL", queue="L2.CGL.PDI.OUT", messageIds=a1["messageIds"], relatedDelay="CGL air-knife stoppage 09:52 (independent)"),
                          knowledgeSource="RB-001", knownError="KE-0031", proposedAction="Restart L2 gateway subscriber (autonomous A-05); replay 3 queued PDIs oldest-first (A-07, approval required)", approvalRequired=True, approvedBy="Shift IT lead — P. Nair (09:51)",
                          resolvedBy="AI agent (human-approved replay)", validation="Queue depth 0; 3/3 PDI ACKs received within 30 s SLA; CGL charge screen live", resolvedAt=iso(AT(0, 9, 55)), mttrMin=12, status="RESOLVED", falseAction=False, csat=5, hero=True, alertId="ALR-0001"))
    # hero incident 2: malformed IDoc — agent diagnosed, waiting for SAP key-user approval (live for the chatbot demo)
    incidents.append(dict(id="INC-26-0413", title="Sales-order amendment IDoc 0000001187734 failed (SO 4213090022/10 qty 180 → 210 t)", category="Interface / SAP", severity="S2", channel="Monitoring alert → ITSM", openedAt=iso(AT(0, 8, 31)), openedBy="Monitoring (ALR-0002)",
                          classification=dict(by="AI agent", confidence=0.93, category="Interface / SAP — IDoc status 51"), enrichment=dict(batchIds=[], interfaceLogs=3, line=None, idoc="0000001187734", segment="E1EDP20", field="EDATU", value="2026-13-02", soItem="4213090022/10"),
                          knowledgeSource="RB-002", knownError="KE-0014", proposedAction="Source data error (invalid schedule-line date). Request SAP SD key user to correct EDATU and re-send IDoc; MES will process on replay. No manual patch in MES (prohibited A-13).",
                          approvalRequired=True, approvedBy=None, resolvedBy=None, validation=None, resolvedAt=None, mttrMin=None, status="AWAITING_APPROVAL", falseAction=False, csat=None, hero=True, alertId="ALR-0002"))
    incidents.append(dict(id="INC-26-0409", title="PDO rejected on CCL — contract version mismatch", category="Interface / L2", severity="S2", channel="Monitoring alert → ITSM", openedAt=iso(AT(-1, 23, 6)), openedBy="Monitoring (ALR-0003)",
                          classification=dict(by="AI agent", confidence=0.91, category="Interface / L2 — schema"), enrichment=dict(batchIds=[], interfaceLogs=2, line="CCL", contract="CT-PDO", payloadVersion="1.3", contractVersion="1.2"), knowledgeSource="RB-003", knownError="KE-0027",
                          proposedAction="Activate CT-PDO v1.3 (approval: Integration CoE) then replay rejected PDO", approvalRequired=True, approvedBy="Integration CoE on-call — R. Menon (23:20)", resolvedBy="AI agent (human-approved)", validation="Replayed message accepted; PDO stored", resolvedAt=iso(AT(-1, 23, 32)), mttrMin=26, status="RESOLVED", falseAction=False, csat=4, hero=False, alertId="ALR-0003"))
    incidents.sort(key=lambda x: x["openedAt"])
    steps = [("09:43:05", "AI agent", "Ticket created from alert ALR-0001; severity S1 classified (confidence 0.96)", "A-06", None, "OK"),
             ("09:43:20", "AI agent", "Read middleware + L2 gateway logs; correlated 3 IN_QUEUE PDIs by PO / coil id", "A-01, A-02", None, "OK"),
             ("09:44:10", "AI agent", "Diagnosis: subscriber heartbeat lost 09:41 — matches RB-001 / KE-0031", "A-03", None, "OK"),
             ("09:44:30", "AI agent", "Restarted L2 gateway subscriber service (autonomous)", "A-05", None, "OK — heartbeat restored 09:45:02"),
             ("09:45:30", "AI agent", "Proposed replay of 3 queued PDIs; approval requested from shift IT lead (A-07 > threshold? no — policy requires approval for production-line messages)", "A-07", "Requested", "PENDING"),
             ("09:51:12", "Human — P. Nair (Shift IT lead)", "Approved replay via Teams card", "A-07", "APPROVED", "OK"),
             ("09:52:00", "AI agent", "Replayed PDI messages oldest-first", "A-07", "APR-2609-118", "3/3 ACK within 28 s"),
             ("09:55:00", "AI agent", "Post-remediation validation: queue depth 0, CGL charge screen live; ticket resolved, user confirmation requested", "A-06", None, "RESOLVED")]
    for i, (t, actor, what, act, appr, res) in enumerate(steps, 1):
        audit.append(dict(id=f"AUD-0412-{i:02d}", incidentId="INC-26-0412", at=f"{dstr(0)}T{t}", actor=actor, action=what, catalogueRef=act, approvalRef=appr, result=res, immutable=True))
    res = [x for x in incidents if x["status"] == "RESOLVED"]
    agent = [x for x in res if x["resolvedBy"].startswith("AI")]
    def mttr(sev): v = [x["mttrMin"] for x in res if x["severity"] == sev]; return round(sum(v) / len(v)) if v else None
    weeks = []
    for w in range(5):
        ws = t0 + timedelta(days=7 * w); we = ws + timedelta(days=7)
        wk = [x for x in res if ws <= datetime.fromisoformat(x["openedAt"]) < we]
        weeks.append(dict(week=ws.strftime("W%V"), tickets=len(wk), agentResolvedPct=round(100 * sum(1 for x in wk if x["resolvedBy"].startswith("AI")) / len(wk)) if wk else 0))
    metrics = dict(periodDays=30, tickets=len(incidents), resolved=len(res), open=len(incidents) - len(res), agentResolvedPct=round(100 * len(agent) / len(res)), humanResolvedPct=round(100 * (len(res) - len(agent)) / len(res)),
                   mttrMinBySeverity={s: mttr(s) for s in ("S1", "S2", "S3", "S4")}, deflectionPct=38, falseActionRatePct=r1(100 * sum(1 for x in agent if x["falseAction"]) / max(len(agent), 1)),
                   automationCoveragePct=round(100 * sum(1 for x in res if x["knowledgeSource"]) / len(res)), slaCompliancePct=96.4, csatAvg=r1(sum(x["csat"] for x in res if x["csat"]) / len([x for x in res if x["csat"]])),
                   weekly=weeks, targets=dict(agentResolvedL1Pct=60, month12Pct=80, l2DiagnosticPct=40))
    return dict(incidents=incidents, runbooks=RUNBOOKS, actionCatalogue=ACTIONS, agentAudit=audit, supportMetrics=metrics)
