"""Headless smoke test for the Khopoli demo pages: zero JS errors, no missing assets, content rendered, screenshot per page.
Usage: python tools/verify.py [page.html ...]   (default: every page + index.html with a click through the sidebar)"""
import sys, time, subprocess, os
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.environ.get("KHP_SHOTS", os.path.join(ROOT, "..", "khp-shots")))
os.makedirs(OUT, exist_ok=True)
PORT = 8110
PAGES = sys.argv[1:] or ["home.html", "orders.html", "planning.html", "coilplan.html", "allocation.html", "execution.html", "quality.html", "genealogy.html", "packing.html", "integration.html", "support.html", "masters.html", "index.html"]
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ok_all = True
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for page in PAGES:
            if not os.path.exists(os.path.join(ROOT, page)):
                print("SKIP " + page + " (missing)"); continue
            pg = b.new_page(viewport={"width": 1600, "height": 1000})
            errs, nf = [], []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("response", lambda r: nf.append(r.url) if r.status == 404 else None)
            for i in range(20):
                try:
                    pg.goto(f"http://localhost:{PORT}/{page}?v={int(time.time())}", wait_until="load"); break
                except Exception:
                    time.sleep(0.4)
            pg.wait_for_timeout(900)
            if page == "index.html":
                for pid in ["home", "orders", "planning", "allocation", "execution", "quality", "genealogy", "packing", "integration", "support", "masters"]:
                    if pg.query_selector(f"[data-page={pid}]") and os.path.exists(os.path.join(ROOT, pid + ".html")):
                        pg.click(f"[data-page={pid}]"); pg.wait_for_timeout(700)
                pg.click("[data-page=home]"); pg.wait_for_timeout(400)
            txt = pg.evaluate("document.body.innerText") or ""
            bad404 = [u for u in nf if not u.endswith("/favicon.ico")]
            ok = not errs and not bad404 and len(txt) > 200
            ok_all = ok_all and ok
            print(("PASS " if ok else "FAIL ") + page + f"  text={len(txt)}" + (f"  errors={errs[:3]}" if errs else "") + (f"  404={bad404[:3]}" if bad404 else ""))
            pg.screenshot(path=os.path.join(OUT, page.replace(".html", "") + ".png"), full_page=False)
            pg.close()
        b.close()
    print("VERIFY", "PASS" if ok_all else "FAIL", "| shots in", os.path.abspath(OUT))
    sys.exit(0 if ok_all else 1)
finally:
    srv.kill()
