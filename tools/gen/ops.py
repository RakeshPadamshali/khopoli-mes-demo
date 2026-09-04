"""Operations: delays (manual/auto stoppages with delay + equipment defect codes), daily OEE per line, live shop-floor snapshot, OTIF."""
from datetime import datetime, timedelta
from .common import R, BASE, ASOF, iso, day, h, m, pick, between, r1, r2, shift_of, SEQ
from .assets_specs import LINES, DELAY_CODES, EQUIP

ACTIVE = [l for l in LINES if l["status"] == "ACTIVE"]
EQ_DEFECTS = {"CGL": [("AKN", "Air knife nozzle choke"), ("ZPT", "Zinc pot roll bearing seizure"), ("FUR", "Furnace zone-3 burner trip"), ("SPM", "Skin pass roll change")],
              "CCL": [("TCT", "Top coater roll change"), ("FOV", "Finish oven fan trip"), ("PCT", "Primer pump failure")],
              "CRM": [("STD", "Work roll change"), ("AGC", "AGC hydraulic leak"), ("XRG", "X-ray gauge fault")],
              "PKL": [("WLD", "Welder electrode failure"), ("AT2", "Acid pump trip"), ("STR", "Trimmer knife change")],
              "SLT": [("SLH", "Slitter knife change"), ("REC", "Recoiler mandrel jam")], "RWL": [("TRM", "Trimmer blade change")],
              "PKG": [("STP", "Strapping head jam"), ("PRN", "Label printer offline")], "HRS": [("SLH", "Knife change")]}


def build_delays():
    delays = []
    for ln in ACTIVE:
        n = R.randint(8, 13)
        for _ in range(n):
            t = BASE + timedelta(days=R.randint(0, 13), hours=R.randint(0, 23), minutes=R.randint(0, 59))
            dc = R.choices(DELAY_CODES, weights=[8, 18, 10, 10, 22, 12, 6, 8, 4, 2])[0]
            dur = R.randint(8, 45) if dc["category"] == "Operational" else R.randint(20, 240) if dc["category"] == "Unplanned" else R.randint(60, 480) if dc["category"] == "Planned" else R.randint(10, 90)
            eq = pick(EQ_DEFECTS[ln["id"]]) if dc["code"].startswith("BD") or dc["category"] == "Planned" else None
            delays.append(dict(id=f"DLY-{SEQ.next('dly'):04d}", line=ln["id"], start=iso(t), end=iso(t + m(dur)), durationMin=dur, delayCode=dc["code"], delayName=dc["name"], category=dc["category"],
                               equipmentId=f"{ln['id']}-{eq[0]}" if eq else None, equipmentDefect=eq[1] if eq else None, capture=pick(["AUTO (L2 downtime message)", "MANUAL"]) if ln["l2"] else "MANUAL",
                               shift=shift_of(t), remarks=eq[1] if eq else dc["name"], status="CLOSED", sapPmNotification=f"PM-{R.randint(100000, 199999)}" if dc["code"].startswith("BD") and R.random() < 0.6 else None))
    # active stoppages right now (demo hooks for S3 / dashboard)
    delays.append(dict(id=f"DLY-{SEQ.next('dly'):04d}", line="CGL", start="2026-09-15T09:52:00", end=None, durationMin=None, delayCode="BD-MECH", delayName="Mechanical breakdown", category="Unplanned",
                       equipmentId="CGL-AKN", equipmentDefect="Air knife nozzle choke — top side", capture="AUTO (L2 downtime message)", shift="A", remarks="Nozzle cleaning in progress; zinc pot on hold temp", status="ACTIVE", sapPmNotification=None))
    delays.append(dict(id=f"DLY-{SEQ.next('dly'):04d}", line="SLT", start="2026-09-15T10:05:00", end=None, durationMin=None, delayCode="OP-CHG", delayName="Size / product changeover", category="Operational",
                       equipmentId="SLT-SLH", equipmentDefect=None, capture="MANUAL", shift="A", remarks="Knife set change 3-cut → 2-cut for 610 mm", status="ACTIVE", sapPmNotification=None))
    delays.sort(key=lambda d: d["start"])
    return delays


def build_kpis(delays, confirmations):
    """daily OEE per active line 1–14 Sep + today partial, from confirmations (output MT) and delays (availability)."""
    rows = []
    for ln in ACTIVE:
        for dn in range(15):
            d0 = BASE + timedelta(days=dn); d1 = d0 + timedelta(days=1); key = day(d0)
            planned = 1440 if dn < 14 else (ASOF - d0).total_seconds() / 60
            dl = sum(min(datetime.fromisoformat(x["end"]) if x["end"] else ASOF, d1).timestamp() - max(datetime.fromisoformat(x["start"]), d0).timestamp() for x in delays if x["line"] == ln["id"]
                     and datetime.fromisoformat(x["start"]) < d1 and (x["end"] is None or datetime.fromisoformat(x["end"]) > d0)) / 60
            out = sum(c["outWeightMT"] for c in confirmations if c["line"] == ln["id"] and c["end"][:10] == key)
            # confirmations only cover the simulated threads; scale to a realistic line day
            scale = ln["targetTpd"] / max(out, 1) * between(0.72, 1.02) if out else between(0.75, 1.0)
            prod = r1(out * scale) if out else r1(ln["targetTpd"] * scale * (planned / 1440))
            cap = ln["targetTpd"] * planned / 1440 * (0.97 if dn == 14 else 1.03); prod = r1(min(prod, cap * between(0.9, 1.0)))
            avail = max(0.5, 1 - dl / planned) if planned else 1
            perf = min(1.0, r2(between(0.82, 0.97))); qual = r2(between(0.955, 0.995))
            rows.append(dict(line=ln["id"], date=key, plannedMin=int(planned), delayMin=int(dl), productionMT=prod, targetMT=r1(ln["targetTpd"] * planned / 1440),
                             availability=r2(avail), performance=perf, quality=qual, oee=r2(avail * perf * qual), primeYieldPct=r1(qual * 100 - between(0, 1.5)), partial=(dn == 14)))
    return rows


def live_snapshot(schedules, delays, holds_active, kpis):
    lines = []
    for ln in ACTIVE:
        cur = [s for s in schedules if s["line"] == ln["id"] and s["status"] == "IN_PROGRESS"]
        nxt = [s for s in schedules if s["line"] == ln["id"] and s["status"] == "PLANNED"]; nxt.sort(key=lambda s: s["plannedStart"])
        act = [d for d in delays if d["line"] == ln["id"] and d["status"] == "ACTIVE"]
        today = next((k for k in kpis if k["line"] == ln["id"] and k["partial"]), None)
        rate = 0 if act else r1(ln["tph"] * between(0.78, 0.98))
        lines.append(dict(line=ln["id"], name=ln["name"], state="STOPPED" if act else "RUNNING" if cur else "IDLE", currentBatch=cur[0]["unitId"] if cur else None, currentPo=cur[0]["po"] if cur else None,
                          currentSo=cur[0]["soId"] if cur else None, rateTph=rate, targetTph=ln["tph"], next=[dict(unitId=s["unitId"], po=s["po"], plannedStart=s["plannedStart"], soId=s["soId"], rush=s["rush"]) for s in nxt[:3]],
                          activeDelay=act[0] if act else None, todayMT=today["productionMT"] if today else 0, todayTargetMT=today["targetMT"] if today else 0, oeeToday=today["oee"] if today else None))
    stopped = {l["line"] for l in lines if l["state"] == "STOPPED"}
    behind = sum(1 for s in schedules if s["status"] == "PLANNED" and s["line"] in stopped and datetime.fromisoformat(s["plannedStart"]) <= ASOF + h(3)) \
        + sum(1 for s in schedules if s["status"] == "IN_PROGRESS" and (s["line"] in stopped or datetime.fromisoformat(s["plannedEnd"]) < ASOF))
    on_track = sum(1 for s in schedules if s["status"] in ("PLANNED", "IN_PROGRESS")) - behind
    for s in schedules:
        if s["status"] in ("PLANNED", "IN_PROGRESS"):
            s["track"] = "BEHIND" if (s["line"] in stopped and (s["status"] == "IN_PROGRESS" or datetime.fromisoformat(s["plannedStart"]) <= ASOF + h(3))) or (s["status"] == "IN_PROGRESS" and datetime.fromisoformat(s["plannedEnd"]) < ASOF) else "ON_TRACK"
    return dict(asOf=iso(ASOF), shift="A", lines=lines, batchesOnTrack=on_track, batchesBehind=behind, activeDelays=sum(1 for d in delays if d["status"] == "ACTIVE"), qualityHolds=holds_active,
                otifWeekly=[dict(week="2026-W33", pct=91.5), dict(week="2026-W34", pct=93.8), dict(week="2026-W35", pct=90.2), dict(week="2026-W36", pct=94.6), dict(week="2026-W37", pct=92.1)])
