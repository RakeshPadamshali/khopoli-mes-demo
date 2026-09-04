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
        check("quality: re-allocation decision stored", pg.evaluate("!!(KHPState.get('dft')||{}).decision"))
        # record a new defect and check propagation count in toast/table
        pg.click("#r-add"); pg.wait_for_timeout(300)
        check("quality: live defect recorded", "NEW" in txt())
        # 4. packing: slit -> pack -> dispatch (gate open after decision)
        go("packing.html"); pg.click("#b-slit"); pg.wait_for_timeout(200); pg.click("#b-pack"); pg.wait_for_timeout(200); pg.click("#b-disp"); pg.wait_for_timeout(400)
        check("packing: slit, pack, dispatch + SAP message", "MES_DISPATCH_CONFIRMATION" in txt() and "Dispatched" in txt())
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
        go("orders.html"); pg.click("#feed"); pg.wait_for_timeout(300); check("orders: simulated SAP feed adds order", "4213090041/10" in txt())
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
