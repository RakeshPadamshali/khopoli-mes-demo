"""ASSETS + SPECIFICATION + master data (ontology domains: ASSETS, SPECIFICATION, QUALITY taxonomy)."""

PLANT = {"id": "KHP", "name": "JSW Steel Coated Products — Khopoli", "shortName": "Khopoli", "state": "Maharashtra",
         "company": "JSW Steel Coated Products Ltd.", "ontologyDomain": "ASSETS",
         "upstreamPlants": [{"id": "VJNR", "name": "JSW Vijayanagar — Hot Strip Mill"}, {"id": "DLV", "name": "JSW Dolvi — Hot Strip Mill"}]}

# Existing lines (RFP §2.1) + upcoming lines onboarded by configuration only
LINES = [
    dict(id="HRS", name="HR Slitter", type="SLITTING", l2=False, tph=45, targetTpd=800, status="ACTIVE", inputs=["HRC"], outputs=["HRC"], seq=1),
    dict(id="PKL", name="Pickling Line", type="PICKLING", l2=True, tph=45, targetTpd=900, status="ACTIVE", inputs=["HRC"], outputs=["HRPO"], seq=2),
    dict(id="CRM", name="Cold Roll Mill", type="COLD_ROLLING", l2=True, tph=32, targetTpd=650, status="ACTIVE", inputs=["HRPO"], outputs=["CRFH"], seq=3),
    dict(id="CGL", name="Continuous Galvanizing Line", type="GALVANIZING", l2=True, tph=22, targetTpd=450, status="ACTIVE", inputs=["CRFH"], outputs=["GI", "GL"], seq=4),
    dict(id="CCL", name="Colour Coating Line", type="COLOUR_COATING", l2=True, tph=12, targetTpd=240, status="ACTIVE", inputs=["GI", "GL"], outputs=["PPGI", "PPGL"], seq=5),
    dict(id="SLT", name="Slitter", type="SLITTING", l2=False, tph=35, targetTpd=600, status="ACTIVE", inputs=["HRPO", "CRFH", "GI", "GL", "PPGI", "PPGL"], outputs=["SLIT"], seq=6),
    dict(id="RWL", name="Rewinding + Trimming Line", type="REWINDING", l2=False, tph=30, targetTpd=400, status="ACTIVE", inputs=["CRFH", "GI"], outputs=["TRIMMED"], seq=7),
    dict(id="PKG", name="Packing Line", type="PACKING", l2=False, tph=30, targetTpd=600, status="ACTIVE", inputs=["*"], outputs=["PACK"], seq=8),
    dict(id="PKL2", name="Pickling Line 2 (upcoming)", type="PICKLING", l2=True, tph=50, targetTpd=1000, status="PLANNED", inputs=["HRC"], outputs=["HRPO"], seq=9),
    dict(id="CRM2", name="Cold Roll Mill 2 (upcoming)", type="COLD_ROLLING", l2=True, tph=35, targetTpd=700, status="PLANNED", inputs=["HRPO"], outputs=["CRFH"], seq=10),
    dict(id="CGL2", name="CGL 2 (upcoming)", type="GALVANIZING", l2=True, tph=25, targetTpd=500, status="PLANNED", inputs=["CRFH"], outputs=["GI", "GL"], seq=11),
    dict(id="CGL3", name="CGL 3 (upcoming)", type="GALVANIZING", l2=True, tph=25, targetTpd=500, status="PLANNED", inputs=["CRFH"], outputs=["GI", "GL"], seq=12),
]

# Equipment per line — (code, name, type, criticality). Defects are attributedTo equipment (ontology QUALITY→ASSETS).
EQUIP = {
    "HRS": [("UNC", "Uncoiler", "MECH", "M"), ("SLH", "HR slitter head", "MECH", "H"), ("REC", "Recoiler", "MECH", "M")],
    "PKL": [("UNC", "Uncoiler", "MECH", "M"), ("WLD", "Coil welder", "MECH", "H"), ("SBK", "Scale breaker", "MECH", "M"), ("AT1", "Acid tank 1", "PROCESS", "H"),
            ("AT2", "Acid tank 2", "PROCESS", "H"), ("AT3", "Acid tank 3", "PROCESS", "H"), ("RNS", "Rinse section", "PROCESS", "M"), ("DRY", "Dryer", "PROCESS", "M"),
            ("STR", "Side trimmer", "MECH", "H"), ("OIL", "Oiler", "PROCESS", "L"), ("REC", "Recoiler", "MECH", "M")],
    "CRM": [("PAY", "Pay-off reel", "MECH", "M"), ("STD", "6-Hi reversing mill stand", "MECH", "H"), ("AGC", "Automatic gauge control", "CONTROL", "H"),
            ("TRL", "Tension reel left", "MECH", "M"), ("TRR", "Tension reel right", "MECH", "M"), ("CLT", "Coolant system", "UTILITY", "M"), ("XRG", "X-ray thickness gauge", "INSTRUMENT", "H")],
    "CGL": [("EAC", "Entry accumulator", "MECH", "M"), ("CLN", "Cleaning section", "PROCESS", "M"), ("FUR", "Annealing furnace", "PROCESS", "H"), ("ZPT", "Zinc pot", "PROCESS", "H"),
            ("AKN", "Air knife", "PROCESS", "H"), ("CTW", "Cooling tower", "PROCESS", "M"), ("SPM", "Skin pass mill", "MECH", "H"), ("TLV", "Tension leveller", "MECH", "M"),
            ("PAS", "Chromate / passivation", "PROCESS", "M"), ("XAC", "Exit accumulator", "MECH", "M"), ("CWG", "Coating weight gauge", "INSTRUMENT", "H")],
    "CCL": [("EAC", "Entry accumulator", "MECH", "M"), ("PRT", "Pre-treatment section", "PROCESS", "M"), ("PCT", "Primer coater", "PROCESS", "H"), ("POV", "Primer oven", "PROCESS", "H"),
            ("TCT", "Top coater", "PROCESS", "H"), ("FOV", "Finish oven", "PROCESS", "H"), ("QCH", "Quench", "PROCESS", "M"), ("DFG", "DFT gauge", "INSTRUMENT", "H"), ("XAC", "Exit accumulator", "MECH", "M")],
    "SLT": [("UNC", "Uncoiler", "MECH", "M"), ("SLH", "Slitter head", "MECH", "H"), ("SCW", "Scrap winder", "MECH", "L"), ("TPD", "Tension pad", "MECH", "M"), ("REC", "Recoiler", "MECH", "M")],
    "RWL": [("UNC", "Uncoiler", "MECH", "M"), ("TRM", "Edge trimmer", "MECH", "H"), ("REC", "Rewind reel", "MECH", "M")],
    "PKG": [("STP", "Strapping machine", "MECH", "M"), ("WRP", "Wrapping station", "MECH", "L"), ("SCL", "Weigh scale", "INSTRUMENT", "H"), ("PRN", "Label printer", "IT", "M")],
}
UPSTREAM_EQUIP = [("VJNR-HSM-DSB", "Descaling box", "VJNR-HSM", "VJNR"), ("VJNR-HSM-F6", "Finishing stand F6", "VJNR-HSM", "VJNR"),
                  ("DLV-HSM-F5", "Finishing stand F5", "DLV-HSM", "DLV")]

GRADES = [
    dict(id="DX51D+Z", std="EN 10346", family="GI", ysMin=140, ysMax=300, utsMin=270, utsMax=500, elMin=22, use="Forming / appliance"),
    dict(id="DX53D+Z", std="EN 10346", family="GI", ysMin=140, ysMax=260, utsMin=270, utsMax=380, elMin=30, use="Deep drawing"),
    dict(id="S350GD+Z", std="EN 10346", family="GI", ysMin=350, ysMax=None, utsMin=420, utsMax=None, elMin=16, use="Structural / PEB"),
    dict(id="CQ-IS277", std="IS 277", family="GI", ysMin=None, ysMax=None, utsMin=None, utsMax=None, elMin=20, use="Commercial roofing"),
    dict(id="SGCC", std="JIS G3302", family="GI", ysMin=None, ysMax=None, utsMin=270, utsMax=None, elMin=20, use="Commercial"),
    dict(id="SGLCC", std="JIS G3321", family="GL", ysMin=None, ysMax=None, utsMin=270, utsMax=None, elMin=20, use="Galvalume roofing"),
    dict(id="CR4-CRFH", std="IS 513", family="CRFH", ysMin=None, ysMax=None, utsMin=None, utsMax=None, elMin=None, use="Full-hard for re-rolling"),
    dict(id="HRPO-E250", std="IS 2062", family="HRPO", ysMin=250, ysMax=None, utsMin=410, utsMax=None, elMin=23, use="Pickled & oiled"),
]
# GSM = total both sides. Band = what the CGL must hit; target aims 5% above nominal minimum.
COATINGS = [
    dict(id="Z80", family="GI", gsm=80, target=84, bandMin=80, bandMax=94, spangle="Minimized"),
    dict(id="Z120", family="GI", gsm=120, target=126, bandMin=120, bandMax=138, spangle="Regular"),
    dict(id="Z180", family="GI", gsm=180, target=189, bandMin=180, bandMax=205, spangle="Regular"),
    dict(id="Z275", family="GI", gsm=275, target=288, bandMin=275, bandMax=310, spangle="Regular"),
    dict(id="AZ150", family="GL", gsm=150, target=157, bandMin=150, bandMax=172, spangle="Aluzinc"),
]
PAINTS = [
    dict(id="RMP", name="Regular Modified Polyester", primerUm=5, topUm=20, topTol=3, backUm=7, backTol=2, glossMin=30, glossMax=40, pmtC=232),
    dict(id="SMP", name="Silicone Modified Polyester", primerUm=5, topUm=25, topTol=3, backUm=7, backTol=2, glossMin=25, glossMax=35, pmtC=241),
    dict(id="PVDF", name="Polyvinylidene Fluoride", primerUm=5, topUm=25, topTol=3, backUm=10, backTol=2, glossMin=25, glossMax=35, pmtC=249),
]
RALS = [("9002", "Grey White"), ("5012", "Light Blue"), ("3009", "Oxide Red"), ("6005", "Moss Green"), ("7016", "Anthracite Grey"), ("9010", "Pure White"), ("1015", "Light Ivory")]

# Line-wise defect taxonomy (ontology QUALITY). severity default; 'attrib' = typical causing equipment code.
DEFECT_CODES = [
    dict(code="DRS", name="Dross (zinc-pot inclusion)", line="CGL", attrib="ZPT", severity="Major"),
    dict(code="PNH", name="Pinhole", line="CGL", attrib="AKN", severity="Major"),
    dict(code="CWD", name="Coating weight deviation", line="CGL", attrib="AKN", severity="Major"),
    dict(code="UCS", name="Uncoated spot", line="CGL", attrib="CLN", severity="Critical"),
    dict(code="WRS", name="White rust", line="CGL", attrib="PAS", severity="Minor"),
    dict(code="DFT", name="DFT deviation", line="CCL", attrib="TCT", severity="Major"),
    dict(code="BLS", name="Paint blister", line="CCL", attrib="FOV", severity="Major"),
    dict(code="ORP", name="Orange peel", line="CCL", attrib="TCT", severity="Minor"),
    dict(code="CLR", name="Colour variation (dE)", line="CCL", attrib="TCT", severity="Major"),
    dict(code="GAU", name="Gauge deviation", line="CRM", attrib="AGC", severity="Major"),
    dict(code="CHM", name="Chatter marks", line="CRM", attrib="STD", severity="Minor"),
    dict(code="EDG", name="Edge wave", line="CRM", attrib="STD", severity="Minor"),
    dict(code="SCR", name="Scratch", line="SLT", attrib="TPD", severity="Minor"),
    dict(code="RST", name="Rust / scale patches", line="PKL", attrib="AT2", severity="Major"),
    dict(code="SCL", name="Scale pits (rolled-in scale)", line="PKL", attrib="VJNR-HSM-DSB", severity="Major"),
    dict(code="TEL", name="Telescoping", line="PKG", attrib="STP", severity="Minor"),
]
DELAY_CODES = [
    dict(code="PM", name="Planned maintenance", category="Planned"), dict(code="BD-MECH", name="Mechanical breakdown", category="Unplanned"),
    dict(code="BD-ELEC", name="Electrical breakdown", category="Unplanned"), dict(code="BD-INST", name="Instrumentation / L2 fault", category="Unplanned"),
    dict(code="OP-CHG", name="Size / product changeover", category="Operational"), dict(code="OP-WLD", name="Strip weld / threading", category="Operational"),
    dict(code="QL-HOLD", name="Quality hold / inspection", category="Quality"), dict(code="MT-NOCOIL", name="No input coil available", category="Material"),
    dict(code="UT-POWER", name="Power / utility interruption", category="Utility"), dict(code="UT-GAS", name="Furnace gas / H2-N2 supply", category="Utility"),
]
CUSTOMERS = [
    dict(id="C001", name="Apex Appliances Ltd", segment="Appliance", city="Pune", state="MH"),
    dict(id="C002", name="Meridian Roofing Solutions", segment="Construction", city="Nagpur", state="MH"),
    dict(id="C003", name="Kestrel Auto Components", segment="Automotive", city="Chakan", state="MH"),
    dict(id="C004", name="Sunbeam Panels Pvt Ltd", segment="Prefab / Sandwich panels", city="Vadodara", state="GJ"),
    dict(id="C005", name="Horizon Ducting Works", segment="HVAC", city="Mumbai", state="MH"),
    dict(id="C006", name="NorthStar Pre-Engineered Buildings", segment="PEB", city="Hyderabad", state="TS"),
    dict(id="C007", name="Vega Consumer Durables", segment="Appliance", city="Noida", state="UP"),
    dict(id="C008", name="Blue Ridge Infra", segment="Construction", city="Bengaluru", state="KA"),
    dict(id="C009", name="Orbit Metal Forming", segment="General Engineering", city="Kolhapur", state="MH"),
    dict(id="C010", name="Pinnacle Sheet Metal", segment="Automotive", city="Aurangabad", state="MH"),
]
PACK_VENDORS = [dict(id="V01", name="Shree Packers", rateDom=450, rateExp=950), dict(id="V02", name="Coastal Packaging Co.", rateDom=470, rateExp=980),
                dict(id="V03", name="Metro Wrap Services", rateDom=440, rateExp=930)]
SHIFTS = [dict(id="A", start="06:00", end="14:00"), dict(id="B", start="14:00", end="22:00"), dict(id="C", start="22:00", end="06:00")]


def equipment_rows():
    rows = []
    for ln, items in EQUIP.items():
        for code, name, typ, crit in items:
            rows.append(dict(id=f"{ln}-{code}", lineId=ln, plantId="KHP", name=name, type=typ, criticality=crit, status="RUNNING"))
    for eid, name, line, plant in UPSTREAM_EQUIP:
        rows.append(dict(id=eid, lineId=line, plantId=plant, name=name, type="MECH", criticality="H", status="RUNNING"))
    return rows
