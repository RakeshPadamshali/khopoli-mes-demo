"""Drives the live-demo actions end to end in one browser context (shared localStorage), the way a presenter would:
allocate a coil, charge/PDO on CGL, record the failing DFT, re-allocate, slit/pack/dispatch, restart + replay the stuck PDI queue,
show defect propagation. Fails on any JS error or missing expected text."""
import sys, time, subprocess, os
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8111
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name + (("  " + extra) if extra and not cond else ""))
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        errs = []
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        def go(page, hash=""):
            for i in range(20):
                try:
                    pg.goto(f"http://localhost:{PORT}/{page}" + (("#" + hash) if hash else ""), wait_until="load"); break
                except Exception:
                    time.sleep(0.4)
            pg.wait_for_timeout(600)
        def txt(): return pg.evaluate("document.body.innerText")
        go("index.html"); pg.evaluate("localStorage.removeItem('khp-demo-state')")
        # 1. allocation: PPC -> QC -> allocate on the hero item
        go("allocation.html", "4213090017/10")
        pg.click("[data-ppc]"); pg.wait_for_timeout(200); pg.click("[data-qc]"); pg.wait_for_timeout(200); pg.click("[data-alloc]:not([disabled])"); pg.wait_for_timeout(400)
        check("allocation: two-step approval then allocate", "ALLOCATED" in txt() and pg.evaluate("Object.keys(KHPState.get('alloc',{})).length") == 1)
        # 2. execution CGL: receive PDO on the running coil, then confirm with balanced numbers
        go("execution.html", "CGL")
        check("execution: stuck PDI banner", "PDI queue stuck" in txt())
        pg.click("[data-act=pdo]"); pg.wait_for_timeout(300)
        check("execution: PDO received panel", "pdo received from l2" in txt().lower())
        pg.click("[data-act=confirm]"); pg.wait_for_timeout(200); pg.click("#f-post"); pg.wait_for_timeout(300)
        check("execution: balanced confirmation posted", "Balanced" in txt())
        check("execution: next coil now chargeable", pg.evaluate("!!document.querySelector('[data-act=charge]:not([disabled])')"))
        go("execution.html", "SLT"); pg.click("[data-act=charge]:not([disabled])"); pg.wait_for_timeout(200)
        check("execution: PDI generated on SLT charge", "pdi generated" in txt().lower())
        # 3. quality: record failing DFT -> suggestion -> re-allocate
        go("quality.html"); pg.click("#l-post"); pg.wait_for_timeout(400)
        check("quality: DFT fail evaluated", "FAIL" in txt() and "ACCEPTS COIL" in txt())
        pg.click("[data-dec=realloc]"); pg.wait_for_timeout(300)
        check("quality: re-allocation decision stored", pg.evaluate("!!((KHPState.get('lab')||{})[KHP.meta.hero.units.filter(function(u){return u.indexOf('PPG')===0;})[0]]||{}).decision"))
        # 3b. multi-order: a second colour-coated coil with a pending lab result -> PASS -> gate open (no decision needed)
        pend = pg.evaluate("KHP.materials.filter(function(u){return u.labPending;}).map(function(u){return u.id;})")
        check("quality: lab-pending coils exist besides the hero", len(pend) >= 2, str(pend))
        pg.select_option("#unitsel", pend[0]); pg.wait_for_timeout(300); pg.click("#l-post"); pg.wait_for_timeout(400)
        check("quality: second coil lab PASS opens dispatch gate", "dispatch linkage allowed" in txt() and pg.evaluate("KHPState.get('lab')['" + pend[0] + "'].result") == "PASS")
        # 3c. a third coil fails the lab -> live defect + hold + downgrade suggestion -> downgrade to secondary
        pg.select_option("#unitsel", pend[1]); pg.wait_for_timeout(300); pg.fill("#l-top", "26.5"); pg.click("#l-post"); pg.wait_for_timeout(400)
        t3 = txt(); card_on = pg.evaluate("document.getElementById('dgcard').style.display") == ""; holds_n = pg.evaluate("KHPState.get('holdsLive').length")
        check("quality: third coil lab FAIL -> suggestion + hold", card_on and ("ACCEPTS COIL" in t3 or "REJECTS" in t3) and holds_n == 1, f"card={card_on} holds={holds_n}")
        pg.click("[data-dec=secondary]"); pg.wait_for_timeout(300)
        check("quality: downgrade decision stored", "Downgraded to secondary" in pg.evaluate("KHPState.get('lab')['" + pend[1] + "'].decision"))
        # record a new defect and check propagation count in toast/table
        pg.click("#r-add"); pg.wait_for_timeout(300)
        check("quality: live defect recorded", "NEW" in txt())
        # 4. packing: slit -> pack -> dispatch (gate open after decision)
        go("packing.html"); pg.click("#b-slit"); pg.wait_for_timeout(200); pg.click("#b-pack"); pg.wait_for_timeout(200); pg.click("#b-disp"); pg.wait_for_timeout(400)
        check("packing: slit, pack, dispatch + SAP message", "MES_DISPATCH_CONFIRMATION" in txt() and "Dispatched" in txt())
        # 4b. multi-order: the second coil (lab PASS, full width) packs and dispatches with a synthesized pack/dispatch; the third (downgraded) slits first
        pg.select_option("#flowsel", pend[0]); pg.wait_for_timeout(300)
        check("packing: second coil selectable and gate open", pg.evaluate("!document.getElementById('b-pack').disabled"))
        pg.click("#b-pack"); pg.wait_for_timeout(200); pg.click("#b-disp"); pg.wait_for_timeout(400)
        check("packing: second coil packed + dispatched", pg.evaluate("Object.keys(KHPState.get('packFlow')).length") == 2 and txt().count("DISPATCHED") >= 2)
        pg.select_option("#flowsel", pend[1]); pg.wait_for_timeout(300)
        slit_btn = pg.evaluate("!!document.querySelector('#b-slit')")
        if slit_btn: pg.click("#b-slit"); pg.wait_for_timeout(200)
        pg.click("#b-pack"); pg.wait_for_timeout(200); pg.click("#b-disp"); pg.wait_for_timeout(400)
        check("packing: third coil (decision recorded) dispatched", pg.evaluate("Object.keys(KHPState.get('packFlow')).length") == 3)
        check("packing: live packs appear in the packing-unit table", pg.evaluate("document.getElementById('packs').innerText").count("PACKED") >= 3)
        # 5. integration: restart -> replay -> approve; resend IDoc
        go("integration.html", "queue")
        check("integration: queue filter shows 3 IN_QUEUE", txt().count("IN QUEUE") >= 3)
        pg.click("[data-act=restart]"); pg.wait_for_timeout(200); pg.click("[data-act=replay]"); pg.wait_for_timeout(200); pg.click("[data-act=approve]"); pg.wait_for_timeout(400)
        check("integration: queue replayed after approval", pg.evaluate("KHPState.get('replayed')") is True and "0" in pg.evaluate("document.querySelectorAll('.kpi')[3].innerText"))
        pg.click("[data-act=resend]"); pg.wait_for_timeout(300)
        check("integration: IDoc re-sent", pg.evaluate("KHPState.get('idocResent')") is True)
        go("execution.html", "CGL"); check("execution: stuck banner gone after replay", "PDI queue stuck" not in txt())
        # 6. genealogy propagation
        go("genealogy.html"); pg.click("[data-prop]"); pg.wait_for_timeout(300)
        check("genealogy: propagation highlights downstream", pg.evaluate("document.querySelectorAll('.node.bad').length") >= 1 and pg.evaluate("document.querySelectorAll('.node.src').length") == 1)
        # 7. planning rush toggle + orders feed
        go("planning.html"); pg.click("#rushbtn"); pg.wait_for_timeout(200); check("planning: rush toggle", "Apply rush flag" in txt())
        # 7b. Scenario 2 step 1: leftover feed -> clubbing proposals -> accept one (multi-slit plan)
        pg.click("#leftbtn"); pg.wait_for_timeout(300)
        check("planning: leftover feed produces clubbing proposals", "6 leftover orders received" in txt() and pg.evaluate("document.querySelectorAll('[data-club]').length") >= 2)
        pg.click("[data-club]"); pg.wait_for_timeout(300)
        check("planning: proposal accepted -> multi-slit plan", "MSP-" in txt() and pg.evaluate("KHPState.get('clubbed').length") == 1)
        # 7b'. full line load + selected-order gantt + schedule search
        check("planning: full line load shows campaign bars", pg.evaluate("document.querySelectorAll('#gantt .g-bar.cmp').length") >= 150)
        check("planning: selected-order gantt shows the hero coil steps", pg.evaluate("document.querySelectorAll('#ogantt .g-bar').length") >= 3)
        other = pg.evaluate("KHP.items.filter(function(i){return !i.hero&&i.horizonCoils>0;})[0].id")
        pg.select_option("#gsel", other); pg.wait_for_timeout(300)
        check("planning: order selector syncs the route card and shows campaign coils", pg.evaluate("document.getElementById('itemsel').value") == other and pg.evaluate("document.querySelectorAll('#ogantt .g-bar.cmp').length") >= 2, other)
        slt_coil = pg.evaluate("(KHP.schedules.filter(function(s){return s.line==='SLT'&&s.status==='PLANNED'&&!s.hero;})[0]||KHP.campaigns.filter(function(s){return s.line==='SLT';})[0]).unitId")
        pg.fill("#ssearch", slt_coil); pg.wait_for_timeout(200)
        check("planning: schedule search filters to the coil", pg.evaluate("document.querySelectorAll('#sched tbody tr').length") == 1, slt_coil)
        pg.fill("#ssearch", ""); pg.wait_for_timeout(200)
        # 7c. Scenario 2 step 4: reroute a planned slitter coil to the recoiling line, then a rework PO on CGL
        pg.click("#sched tr:not(.hero) [data-rr]"); pg.wait_for_timeout(300); pg.select_option("#rropt", "REROUTE:RWL"); pg.click("#rrgo"); pg.wait_for_timeout(400)
        check("planning: coil rerouted SLT -> RWL", pg.evaluate("document.getElementById('linesel').value") == "RWL" and pg.evaluate("KHPState.get('reroutes')[0].kind") == "REROUTE" and "REROUTE from SLT" in txt())
        check("planning: reroute generated a rework production order", "-R001" in pg.evaluate("KHPState.get('reroutes')[0].newPo") and "R001" in txt())
        pg.select_option("#linesel", "CGL"); pg.wait_for_timeout(300); pg.click("#sched tr:not(.hero) [data-rr]"); pg.wait_for_timeout(300); pg.select_option("#rropt", "REWORK:CGL"); pg.click("#rrgo"); pg.wait_for_timeout(400)
        check("planning: same-line rework production order generated", "-R002" in pg.evaluate("KHPState.get('reroutes')[1].newPo") and "REWORK" in txt())
        check("planning: rerouted bar on the gantt", pg.evaluate("document.querySelectorAll('#gantt .g-bar[title*=\"REROUTE\"], #gantt .g-bar[title*=\"REWORK\"]').length") >= 1)
        check("planning: EST check stays at zero violations after reroute + rework", "0 precedence violations" in pg.evaluate("document.getElementById('gload').innerText"))
        check("planning: bars coloured per order (several colours on the full load)", pg.evaluate("new Set(Array.from(document.querySelectorAll('#gantt .g-bar')).map(function(b){return b.style.background||b.style.backgroundColor;})).size") >= 5)
        go("orders.html"); pg.click("#feed"); pg.wait_for_timeout(300); check("orders: simulated SAP feed adds order", "4213090041/10" in txt())
        check("orders: BTA follows the live allocation from the Material Allocator", "allocated live" in txt() and "after batch swap" in txt())
        pg.evaluate("KHPState.set('swapped', false)"); go("orders.html"); check("orders: BTA follows the batch-swap toggle", "before batch swap" in txt()); pg.evaluate("KHPState.set('swapped', true)")
        # 7d. Coil Plan report (same dataset as the full-load gantt): rows with route chips, hero expanded, expand another, search, order filter, reroute reflected
        go("coilplan.html")
        check("coil plan: lists the coils of the load with route chips", pg.evaluate("document.querySelectorAll('#cplan tbody tr[data-exp]').length") >= 100 and pg.evaluate("document.querySelectorAll('#cplan .rchip').length") >= 400)
        check("coil plan: hero coil pre-expanded with its operation schedule", pg.evaluate("document.querySelectorAll('#cplan tr.detail').length") == 1 and "operation schedule" in txt().lower())
        pg.click("(//tr[@data-exp])[3]"); pg.wait_for_timeout(300)
        check("coil plan: clicking a coil row expands its steps", pg.evaluate("document.querySelectorAll('#cplan tr.detail').length") == 2 and pg.evaluate("document.querySelectorAll('#cplan .ops tbody tr').length") >= 8)
        pg.fill("#cpsearch", slt_coil); pg.wait_for_timeout(200)
        check("coil plan: search narrows to the coil", pg.evaluate("document.querySelectorAll('#cplan tbody tr[data-exp]').length") == 1, slt_coil)
        pg.fill("#cpsearch", ""); pg.wait_for_timeout(200)
        check("coil plan: reroute recorded on Routes & Schedules is reflected", "REROUTED" in pg.evaluate("document.getElementById('cplan').innerText"))
        pg.select_option("#f-order", "4213090017/10"); pg.wait_for_timeout(200)
        check("coil plan: order filter keeps only the hero order's coils", pg.evaluate("document.querySelectorAll('#cplan tbody tr[data-exp]').length") >= 5 and pg.evaluate("Array.from(document.querySelectorAll('#cplan tbody tr[data-exp]')).every(function(r){return r.innerText.indexOf('4213090017/10')>=0;})"))
        pg.select_option("#f-order", ""); pg.select_option("#f-kind", "running"); pg.wait_for_timeout(200)
        check("coil plan: running filter shows the coils on the lines now", pg.evaluate("document.querySelectorAll('#cplan tbody tr[data-exp]').length") == 5)
        # 8. reset from host clears everything
        go("index.html"); pg.click("#reset"); pg.wait_for_timeout(300)
        check("host: reset clears demo state", pg.evaluate("Object.keys(JSON.parse(localStorage.getItem('khp-demo-state')||'{}')).length") == 0)
        check("zero JS errors across the flow", not errs, str(errs[:3]))
        b.close()
    ok = all(r[1] for r in results)
    print("FLOWS", "PASS" if ok else "FAIL", f"({sum(1 for r in results if r[1])}/{len(results)})")
    sys.exit(0 if ok else 1)
finally:
    srv.kill()
