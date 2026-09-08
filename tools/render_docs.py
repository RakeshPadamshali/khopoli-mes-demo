"""Render the presenter scripts in docs/ to A4-landscape PDFs (Playwright, headless Chrome).
Output folder: KHP_PDF_OUT env var, else the hand-off folder; pass a prefix (e.g. scenario-2) to render one script."""
import sys, os
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
OUT = os.environ.get("KHP_PDF_OUT") or r"D:\Rakesh Padamshali\Projects\POC\JSW_Khopoli"
JOBS = [("scenario-1-demo-script.html", "Scenario1_Golden_Thread_Demo_Script.pdf"),
        ("scenario-2-demo-script.html", "Scenario2_Planning_Batch_Allocation_Demo_Script.pdf")]
jobs = [j for j in JOBS if len(sys.argv) < 2 or j[0].startswith(sys.argv[1])]
os.makedirs(OUT, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    for src, dst in jobs:
        pg.goto("file:///" + os.path.join(DOCS, src).replace("\\", "/"), wait_until="load"); pg.wait_for_timeout(300)
        out = os.path.join(OUT, dst)
        pg.pdf(path=out, format="A4", landscape=True, print_background=True, prefer_css_page_size=True)
        try:
            import fitz
            doc = fitz.open(out); pages = len(doc)
            if os.environ.get("KHP_PDF_PREVIEW"):
                for i in range(pages): doc[i].get_pixmap(dpi=70).save(os.path.join(os.environ["KHP_PDF_PREVIEW"], f"{src[:10]}-p{i + 1}.png"))
        except ImportError:
            pages = "?"
        print(f"{dst}: {pages} pages, {os.path.getsize(out) // 1024} KB -> {OUT}")
    b.close()
