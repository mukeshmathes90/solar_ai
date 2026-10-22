# -*- coding: utf-8 -*-
"""Build the VCEW mini-project report (.docx) for the microgrid project.

Run:  "C:\\Program Files\\Python38\\python.exe" build_report.py

Personal / administrative details that only the candidate can supply are left
as ``[TO BE PROVIDED]`` so that nothing is fabricated.  Everything that
describes the project itself (design, code, dataset, models, results) is
written in full.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor, Twips

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = ROOT / "microgrid-ai"
GRAPHS = PROJECT / "reports" / "graphs"
ASSETS = HERE / "assets"
DIAGRAMS = HERE / "diagrams"
OUT_DOCX = HERE / "Microgrid_AI_Mini_Project_Report.docx"

COLLEGE_LOGO = ASSETS / "college_emblem.png"
ANNA_LOGO = ASSETS / "anna_university.jpeg"

TITLE = ("AI-ENABLED PREDICTIVE MONITORING AND ENERGY OPTIMIZATION OF "
         "RENEWABLE MICROGRIDS USING IoT")
P = "[TO BE PROVIDED]"
FONT = "Times New Roman"
BLACK = RGBColor(0x00, 0x00, 0x00)
LEFT = WD_ALIGN_PARAGRAPH.LEFT
CENTER = WD_ALIGN_PARAGRAPH.CENTER
JUSTIFY = WD_ALIGN_PARAGRAPH.JUSTIFY
RIGHT = WD_ALIGN_PARAGRAPH.RIGHT

# Single source of truth for every numbered caption.  The same strings are used
# in the body of the report and in the List of Tables / List of Figures, so they
# can never drift apart.
TBL = {
    "2.1": "Summary of related work and the research gap",
    "3.1": "Hardware components and their roles",
    "3.2": "ESP8266 pin map",
    "3.3": "Ingest payload fields",
    "3.4": "REST API endpoints",
    "3.5": "Database tables and their purpose",
    "3.6": "Features used by the machine learning models",
    "3.7": "Model hyperparameters",
    "3.8": "Energy-allocation tiers and default values",
    "3.9": "Software, libraries and their roles",
    "4.1": "Dataset composition",
    "4.2": "Anomaly-type distribution",
    "4.3": "Generation regressor performance",
    "4.4": "Operating-condition classification report (held-out test set)",
    "4.5": "Anomaly detector performance on the held-out test set",
    "4.6": "Feature importance of the generation regressor",
    "4.7": "Energy-allocation scenarios",
}
TBL_ORDER = ["2.1", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8",
             "3.9", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"]

FIG = {
    "3.1": "System architecture of the IoT microgrid monitoring platform",
    "3.2": "Entity-relationship diagram of the SQLite database",
    "3.3": "Online and offline data pipelines sharing one feature-engineering "
           "implementation",
    "4.1": "Distribution of operating conditions in the dataset",
    "4.2": "Solar voltage and solar power over time",
    "4.3": "Wind voltage and turbine RPM over time",
    "4.4": "Light level versus solar generation",
    "4.5": "Turbine RPM versus wind generation",
    "4.6": "Relative contribution of solar and wind generation",
    "4.7": "Actual versus predicted power on the held-out test set",
    "4.8": "Regression evaluation and residuals",
    "4.9": "Generation trend and forecast",
    "4.10": "Comparison of model scores",
    "4.11": "Confusion matrix for the operating-condition classifier",
    "4.12": "Confusion matrix for the anomaly detector",
    "4.13": "Normal versus anomalous sensor patterns",
    "4.14": "Feature importance of the generation regressor",
}
FIG_ORDER = ["3.1", "3.2", "3.3", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6",
             "4.7", "4.8", "4.9", "4.10", "4.11", "4.12", "4.13", "4.14"]


def tcap(key):
    return "Table %s  %s" % (key, TBL[key])


def fcap(key):
    return "Figure %s  %s" % (key, FIG[key])


# --------------------------------------------------------------------------- #
# Low level helpers
# --------------------------------------------------------------------------- #
def style_run(run, size=None, bold=None, italic=None, name=FONT):
    run.font.name = name
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    run.font.color.rgb = BLACK
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), name)


def para(doc, text="", size=14, bold=False, italic=False, align=JUSTIFY,
         line=1.5, indent=False, before=0, after=0, style=None,
         keep_with_next=False):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if indent:
        pf.first_line_indent = Twips(1134)
    if keep_with_next:
        pf.keep_with_next = True
    if text:
        style_run(p.add_run(text), size, bold, italic)
    return p


def blank(doc, count=1, size=14):
    for _ in range(count):
        para(doc, "", size=size, line=1.15)


def chapter_open(doc, number, title, first=False):
    if not first:
        doc.add_page_break()
    para(doc, "CHAPTER %d" % number, 14, True, align=CENTER, line=1.5, before=15)
    blank(doc, count=2)
    para(doc, title.upper(), 14, True, align=CENTER, line=1.5,
         style="Heading 1")
    blank(doc, count=4)


def h1(doc, text):
    doc.add_page_break()
    return para(doc, text.upper(), 14, True, align=CENTER, line=1.5,
                style="Heading 1")


def h2(doc, text):
    return para(doc, text.upper(), 14, True, align=LEFT, line=1.5,
                before=8, after=4, style="Heading 2")


def h3(doc, text):
    return para(doc, text, 14, True, align=LEFT, line=1.5,
                before=6, after=2, style="Heading 3")


def body(doc, text, indent=True):
    return para(doc, text, 14, align=JUSTIFY, line=1.5, indent=indent)


def bullets(doc, items):
    for item in items:
        p = para(doc, "\u2022  " + item, 14, align=JUSTIFY, line=1.5)
        p.paragraph_format.left_indent = Twips(720)
        p.paragraph_format.first_line_indent = Twips(-360)


def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def set_cell(cell, text, size=12, bold=False, align=LEFT, bg=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    pf = p.paragraph_format
    pf.line_spacing = 1.0
    pf.space_before = Pt(1)
    pf.space_after = Pt(1)
    style_run(p.add_run(text), size, bold)
    if bg:
        shade(cell, bg)


def add_table(doc, caption, headers, rows, widths=None, size=12,
              first_col_center=False):
    if caption:
        para(doc, caption, 12, True, align=CENTER, line=1.0,
             before=6, after=3, keep_with_next=True)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, head in enumerate(headers):
        set_cell(table.rows[0].cells[i], str(head), size, True, CENTER, "D9D9D9")
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            align = CENTER if (i == 0 and first_col_center and len(headers) > 2) else LEFT
            set_cell(cells[i], str(val), size, False, align)
    if widths:
        table.autofit = False
        for i, w in enumerate(widths):
            for row in table.rows:
                row.cells[i].width = Mm(w)
    return table


def add_figure(doc, image, caption, width_mm=125):
    p = doc.add_paragraph()
    p.alignment = CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.0
    pf.keep_with_next = True
    p.add_run().add_picture(str(image), width=Mm(width_mm))
    para(doc, caption, 12, True, align=CENTER, line=1.0, before=2, after=6)
    return p


# --------------------------------------------------------------------------- #
# Page numbering / sections
# --------------------------------------------------------------------------- #
def set_pgnum(section, fmt=None, start=None):
    sectPr = section._sectPr
    pgNumType = sectPr.find(qn("w:pgNumType"))
    if pgNumType is None:
        pgNumType = OxmlElement("w:pgNumType")
        cols = sectPr.find(qn("w:cols"))
        if cols is not None:
            cols.addprevious(pgNumType)
        else:
            sectPr.append(pgNumType)
    if fmt:
        pgNumType.set(qn("w:fmt"), fmt)
    if start is not None:
        pgNumType.set(qn("w:start"), str(start))


def footer_page_number(section):
    section.footer.is_linked_to_previous = False
    p = section.footer.paragraphs[0]
    p.alignment = CENTER
    run = p.add_run()
    style_run(run, 12)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def clear_footer(section):
    section.footer.is_linked_to_previous = False
    for p in section.footer.paragraphs:
        for r in list(p.runs):
            r._element.getparent().remove(r._element)


def setup_margins(section):
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(35)
    section.bottom_margin = Mm(30)
    section.left_margin = Mm(40)
    section.right_margin = Mm(25)


# --------------------------------------------------------------------------- #
# Front matter
# --------------------------------------------------------------------------- #
def college_block(doc, line=1.0):
    para(doc, "VIVEKANANDHA COLLEGE OF ENGINEERING FOR WOMEN",
         16, True, align=CENTER, line=line)
    para(doc, "[Autonomous]", 14, align=CENTER, line=line)
    para(doc, "An ISO 9001:2015 Certified Institution",
         14, align=CENTER, line=line)
    para(doc, "(Approved by AICTE, New Delhi and Affiliated to Anna University, Chennai,",
         14, align=CENTER, line=line)
    para(doc, "Accredited by NAAC and NBA Tier - I UG: CSE, EEE, ECE, IT and Bio-Tech.)",
         14, align=CENTER, line=line)
    para(doc, "Tiruchengode - 637205, Namakkal Dt., Tamil Nadu",
         14, align=CENTER, line=line)


def cover_page(doc):
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    left = table.cell(0, 0).paragraphs[0]
    left.alignment = CENTER
    left.add_run().add_picture(str(COLLEGE_LOGO), width=Mm(20.4))
    right = table.cell(0, 1).paragraphs[0]
    right.alignment = CENTER
    right.add_run().add_picture(str(ANNA_LOGO), width=Mm(16.9))
    for col in table.columns:
        col.width = Mm(72.5)

    blank(doc, size=10)
    college_block(doc)
    blank(doc, size=10)
    para(doc, TITLE, 15, True, align=CENTER, line=1.0)
    para(doc, "A MINI PROJECT REPORT", 14, True, align=CENTER, line=1.0)
    para(doc, "Submitted by", 14, True, align=CENTER, line=1.0)
    para(doc, P, 15, True, align=CENTER, line=1.0)
    para(doc, P, 15, True, align=CENTER, line=1.0)
    blank(doc, size=10)
    para(doc, "In partial fulfillment for the award of the degree of",
         14, True, align=CENTER, line=1.0)
    para(doc, P, 14, True, align=CENTER, line=1.0)
    para(doc, "IN", 14, True, align=CENTER, line=1.0)
    para(doc, P, 14, align=CENTER, line=1.0)
    blank(doc, size=10)
    college_block(doc)
    para(doc, P, 14, align=CENTER, line=1.0)


def bonafide(doc):
    para(doc, "VIVEKANANDHA COLLEGE OF", 18, True, align=CENTER, line=1.5)
    para(doc, "ENGINEERING FOR WOMEN", 18, True, align=CENTER, line=1.5)
    blank(doc)
    para(doc, "BONAFIDE CERTIFICATE", 15, True, align=CENTER, line=1.5)
    blank(doc)
    body(doc, "Certified that this project report \u201c%s\u201d is the "
              "bonafide work of \u201c%s\u201d who carried out the mini project "
              "work under my supervision." % (TITLE, P))
    blank(doc)
    body(doc, "Submitted to the Viva voce Examination held on "
              "_____________________.")
    blank(doc, count=2)
    sig = doc.add_table(rows=1, cols=2)
    c0 = sig.cell(0, 0).paragraphs[0]
    c0.alignment = CENTER
    style_run(c0.add_run("____________________________"), 12)
    c0.add_run("\n")
    style_run(c0.add_run("Signature of the Head of the Department"), 12, True)
    c0.add_run("\n")
    style_run(c0.add_run("Name: " + P), 12)
    c0.add_run("\n")
    style_run(c0.add_run("Department: " + P), 12)
    c0.add_run("\n")
    style_run(c0.add_run("Address: " + P), 12)
    c1 = sig.cell(0, 1).paragraphs[0]
    c1.alignment = CENTER
    style_run(c1.add_run("____________________________"), 12)
    c1.add_run("\n")
    style_run(c1.add_run("Signature of the Supervisor"), 12, True)
    c1.add_run("\n")
    style_run(c1.add_run("Name: " + P), 12)
    c1.add_run("\n")
    style_run(c1.add_run("Designation: " + P), 12)
    c1.add_run("\n")
    style_run(c1.add_run("Department: " + P), 12)
    blank(doc, count=2)
    exam = doc.add_table(rows=1, cols=2)
    e0 = exam.cell(0, 0).paragraphs[0]
    e0.alignment = CENTER
    style_run(e0.add_run("INTERNAL EXAMINER"), 14, True)
    e1 = exam.cell(0, 1).paragraphs[0]
    e1.alignment = CENTER
    style_run(e1.add_run("EXTERNAL EXAMINER"), 14, True)


def acknowledgement(doc):
    h1(doc, "Acknowledgement")
    body(doc, "We express our sincere gratitude to our project supervisor, %s, "
              "%s, Department of %s, for the valuable guidance, constant "
              "encouragement and constructive suggestions provided throughout "
              "the course of this mini project." % (P, P, P))
    body(doc, "We thank the Head of the Department, %s, and the entire faculty "
              "and non-teaching staff of the Department of %s for their "
              "support and for providing the laboratory facilities that made "
              "this work possible." % (P, P))
    body(doc, "We are grateful to the Principal and the Management of "
              "Vivekanandha College of Engineering for Women for the "
              "infrastructure and encouragement extended to us.")
    body(doc, "Finally, we thank our family and friends for their patience and "
              "moral support during the preparation of this report.")
    blank(doc, count=2)
    para(doc, "THE CANDIDATES", 14, True, align=RIGHT, line=1.5)


def vision_mission(doc):
    h1(doc, "Institute and Department Vision and Mission")
    h3(doc, "Institute Vision")
    body(doc, P)
    h3(doc, "Institute Mission")
    body(doc, P)
    h3(doc, "Department Vision")
    body(doc, P)
    h3(doc, "Department Mission")
    body(doc, P)


PO_TEXT = [
    "PO1: Engineering knowledge - Apply the knowledge of mathematics, science, "
    "engineering fundamentals and an engineering specialization to the "
    "solution of complex engineering problems.",
    "PO2: Problem analysis - Identify, formulate, review research literature "
    "and analyze complex engineering problems reaching substantiated "
    "conclusions using first principles of mathematics, natural sciences and "
    "engineering sciences.",
    "PO3: Design/development of solutions - Design solutions for complex "
    "engineering problems and design system components or processes that meet "
    "the specified needs with appropriate consideration for public health and "
    "safety and the cultural, societal and environmental considerations.",
    "PO4: Conduct investigations of complex problems - Use research-based "
    "knowledge and research methods including design of experiments, analysis "
    "and interpretation of data, and synthesis of the information to provide "
    "valid conclusions.",
    "PO5: Modern tool usage - Create, select and apply appropriate techniques, "
    "resources and modern engineering and IT tools including prediction and "
    "modelling to complex engineering activities with an understanding of the "
    "limitations.",
    "PO6: The engineer and society - Apply reasoning informed by the contextual "
    "knowledge to assess societal, health, safety, legal and cultural issues "
    "and the consequent responsibilities relevant to the professional "
    "engineering practice.",
    "PO7: Environment and sustainability - Understand the impact of the "
    "professional engineering solutions in societal and environmental contexts, "
    "and demonstrate the knowledge of, and the need for, sustainable "
    "development.",
    "PO8: Ethics - Apply ethical principles and commit to professional ethics "
    "and responsibilities and norms of the engineering practice.",
    "PO9: Individual and team work - Function effectively as an individual, and "
    "as a member or leader in diverse teams, and in multidisciplinary "
    "settings.",
    "PO10: Communication - Communicate effectively on complex engineering "
    "activities with the engineering community and with society at large.",
    "PO11: Project management and finance - Demonstrate knowledge and "
    "understanding of the engineering and management principles and apply "
    "these to one's own work, as a member and leader in a team, to manage "
    "projects and in multidisciplinary environments.",
]


def peo_po_pso(doc):
    h1(doc, "Programme Educational Objectives, Programme Outcomes and "
            "Programme Specific Outcomes")
    h3(doc, "Programme Educational Objectives")
    for i in range(1, 6):
        body(doc, "PEO %d: %s" % (i, P))
    h3(doc, "Programme Outcomes")
    for text in PO_TEXT:
        body(doc, text)
    h3(doc, "Programme Specific Outcomes")
    for i in range(1, 4):
        body(doc, "PSO%d: %s" % (i, P))


CO_TEXT = [
    ("CO1", "Identify the area of the project", "Remembering"),
    ("CO2", "Illustrate the literature of the project", "Understanding"),
    ("CO3", "Determine the problem identified and plan the solution", "Applying"),
    ("CO4", "Experimentation / design analysis / prototype development", "Creating"),
    ("CO5", "Result and analysis", "Analyzing"),
    ("CO6", "Conclusion, scope for future work and documentation", "Evaluating"),
]

CO_PO = {
    "CO1": [3, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0],
    "CO2": [2, 3, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0],
    "CO3": [2, 2, 3, 2, 1, 0, 0, 0, 0, 0, 0, 2, 1, 0],
    "CO4": [2, 1, 3, 3, 2, 1, 0, 0, 2, 1, 0, 2, 2, 1],
    "CO5": [2, 1, 2, 2, 2, 1, 1, 1, 2, 1, 1, 2, 1, 2],
    "CO6": [2, 1, 1, 1, 0, 2, 2, 1, 0, 0, 2, 1, 1, 2],
}


def co_mapping(doc):
    h1(doc, "Course Outcome Mapping with Programme Outcomes and Programme "
            "Specific Outcomes")
    body(doc, "Upon completion of the course, students will be able to:")
    add_table(doc, "Course outcomes and their Bloom's taxonomy level",
              ["CO#", "Course Outcomes", "Bloom's Taxonomy Level"],
              [[c, t, b] for c, t, b in CO_TEXT],
              widths=[16, 100, 34], size=12)
    blank(doc, size=12)
    h3(doc, "CO - PO / PSO Mapping")
    body(doc, "The following mapping is proposed for this mini project. The "
              "values 3, 2 and 1 indicate a high, medium and low correlation "
              "respectively and 0 indicates no correlation. The mapping should "
              "be confirmed with the project supervisor.")
    headers = (["COs"] + ["PO%d" % i for i in range(1, 12)]
               + ["PSO1", "PSO2", "PSO3"])
    rows = [["CO%d" % i] + [str(v) for v in CO_PO["CO%d" % i]]
            for i in range(1, 7)]
    add_table(doc, "CO - PO / PSO mapping matrix (3/2/1 = strong/medium/low "
                   "correlation)",
              headers, rows,
              widths=[13] + [8] * 11 + [11, 11, 11], size=9,
              first_col_center=True)


def relevance(doc):
    h1(doc, "Relevance to Programme Outcomes and Programme Specific Outcomes")
    for text in [
        "This mini project applies engineering knowledge to a real "
        "sustainability problem and therefore maps strongly to PO1 and PO2. "
        "The behaviour of a hybrid solar and wind microgrid was studied, the "
        "monitoring and prediction problem was formulated, and the measured "
        "and simulated sensor data were analysed using first principles.",
        "The design and development of the embedded node, the data pipeline "
        "and the machine learning models address PO3 and PO4. The work "
        "included the design of the sensor interface, the construction of a "
        "reproducible dataset and the quantitative evaluation of the models on "
        "a held-out test set.",
        "The use of the ESP8266 platform, the Flask framework, SQLite and the "
        "scikit-learn library satisfies PO5, since modern engineering and IT "
        "tools were selected and applied with an understanding of their "
        "limitations.",
        "The project contributes to affordable and clean energy and to climate "
        "action, which aligns with PO6 and PO7. The report also documents the "
        "ethical treatment of data by never presenting simulated or estimated "
        "values as measured values, which supports PO8.",
        "The work was carried out as a team, with clearly divided "
        "responsibilities for the firmware, the backend, the machine learning "
        "pipeline and the dashboard, which corresponds to PO9 and PO10. The "
        "planning of the schedule and the documentation of the deliverables "
        "relate to PO11.",
        "The project also supports the Sustainable Development Goals, "
        "particularly SDG 7 (Affordable and Clean Energy), SDG 9 (Industry, "
        "Innovation and Infrastructure) and SDG 13 (Climate Action).",
    ]:
        body(doc, text)


def abstract(doc):
    h1(doc, "Abstract")
    para(doc, "Renewable microgrids that combine solar photovoltaic and small "
              "wind generation are widely used, but their output is "
              "intermittent and developing faults often go unnoticed. This mini "
              "project designs and evaluates a low-cost Internet of Things (IoT) "
              "platform that monitors a hybrid solar and wind microgrid node, "
              "predicts its generation, classifies its operating condition, "
              "detects anomalies, and recommends how the available energy "
              "should be allocated between essential load, deferrable load and "
              "storage. An ESP8266 node measures solar and wind voltage, turbine "
              "speed, temperature, humidity and light level and publishes each "
              "reading over Wi-Fi to a Flask REST backend, which validates, "
              "deduplicates and stores the data and runs three Random Forest "
              "models. On a reproducible simulated dataset of 12,000 samples "
              "with a chronological split, the generation regressor reached a "
              "mean absolute error of 0.0147 W and an R-squared of 0.9968, the "
              "condition classifier an accuracy of 0.8528, and the anomaly "
              "detector an accuracy of 0.9861. These results characterise the "
              "software pipeline on simulated data and are not a claim of field "
              "accuracy.",
         14, align=JUSTIFY, line=2.0)
    para(doc, "Keywords: IoT, renewable microgrid, solar and wind energy, "
              "Random Forest, generation forecasting, anomaly detection, "
              "energy management, ESP8266, Flask, scikit-learn.",
         14, align=JUSTIFY, line=2.0)


def toc(doc):
    para(doc, "TABLE OF CONTENTS", 14, True, align=CENTER, line=1.5)
    blank(doc)
    p = doc.add_paragraph()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), 'TOC \\o "1-3" \\h \\z \\u')
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "Right-click and choose 'Update Field' to build the contents."
    run.append(t)
    fld.append(run)
    p._p.append(fld)


def caption_list(doc, heading, col1, entries):
    h1(doc, heading)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, head in enumerate([col1, "Title", "Page No."]):
        set_cell(table.rows[0].cells[i], head, 12, True, CENTER, "D9D9D9")
    for number, title in entries:
        cells = table.add_row().cells
        set_cell(cells[0], number, 12, False, CENTER)
        set_cell(cells[1], title, 12, False, LEFT)
        set_cell(cells[2], "", 12, False, CENTER)
    for row in table.rows:
        row.cells[0].width = Mm(22)
        row.cells[1].width = Mm(103)
        row.cells[2].width = Mm(20)


ABBREVIATIONS = [
    ("AC", "Alternating Current"), ("ADC", "Analogue-to-Digital Converter"),
    ("AI", "Artificial Intelligence"),
    ("API", "Application Programming Interface"),
    ("CSV", "Comma-Separated Values"), ("DC", "Direct Current"),
    ("DOI", "Digital Object Identifier"), ("ER", "Entity-Relationship"),
    ("GPIO", "General-Purpose Input/Output"),
    ("HTML", "HyperText Markup Language"),
    ("HTTP", "HyperText Transfer Protocol"),
    ("I2C", "Inter-Integrated Circuit"), ("IoT", "Internet of Things"),
    ("INA219", "Current, Voltage and Power Monitor"),
    ("JSON", "JavaScript Object Notation"),
    ("LDR", "Light-Dependent Resistor"),
    ("MAE", "Mean Absolute Error"), ("ML", "Machine Learning"),
    ("MPP", "Maximum Power Point"), ("NTP", "Network Time Protocol"),
    ("PEO", "Programme Educational Objective"),
    ("PO", "Programme Outcome"), ("PSO", "Programme Specific Outcome"),
    ("RF", "Random Forest"), ("RMSE", "Root Mean Square Error"),
    ("RPM", "Revolutions Per Minute"),
    ("REST", "Representational State Transfer"),
    ("SDG", "Sustainable Development Goal"),
    ("SQL", "Structured Query Language"),
    ("SSR", "Solid-State Relay"), ("TOC", "Table of Contents"),
    ("VOC", "Open-Circuit Voltage"), ("WSN", "Wireless Sensor Network"),
]


def list_of_symbols(doc):
    h1(doc, "List of Symbols and Abbreviations")
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for abbr, meaning in ABBREVIATIONS:
        cells = table.add_row().cells
        set_cell(cells[0], abbr, 12, True, LEFT)
        set_cell(cells[1], meaning, 12, False, LEFT)
    for row in table.rows:
        row.cells[0].width = Mm(35)
        row.cells[1].width = Mm(110)


# --------------------------------------------------------------------------- #
# Chapters
# --------------------------------------------------------------------------- #
def chapter1(doc):
    chapter_open(doc, 1, "Introduction", first=True)
    h2(doc, "1.1 Overview of Renewable Microgrids")
    body(doc, "A microgrid is a small, self-contained electrical system that "
              "combines distributed generation sources with local loads and, "
              "optionally, energy storage. When the generators are renewable, "
              "the microgrid can supply electricity with very low carbon "
              "emissions and at a low marginal cost. Hybrid systems that "
              "combine solar photovoltaic generation with small wind "
              "generation are attractive because the two sources are "
              "complementary: solar output peaks during the day while wind "
              "output can continue into the night. Such systems are widely "
              "used for rural electrification, agricultural pumping, telecom "
              "towers and campus demonstration facilities.")
    h2(doc, "1.2 Need for Predictive Monitoring in Microgrids")
    body(doc, "Renewable generation is intermittent and depends on weather "
              "that cannot be controlled. Because the available power changes "
              "from minute to minute, operators need continuous information "
              "about how much energy is being produced, whether the equipment "
              "is healthy and how the available energy should be used. Faults "
              "such as a shaded or soiled panel, a fouled turbine, a failed "
              "rectifier or a drifting sensor may not stop the system "
              "immediately, but they silently reduce the energy delivered and "
              "can shorten equipment life. If such conditions are detected "
              "early, maintenance can be scheduled before a minor degradation "
              "becomes a failure.")
    h2(doc, "1.3 Role of the Internet of Things")
    body(doc, "The Internet of Things provides the sensing, communication and "
              "actuation layer that makes continuous monitoring practical. "
              "Low-cost microcontrollers such as the ESP8266 integrate Wi-Fi "
              "connectivity and analogue and digital inputs in a single "
              "module, so a complete telemetry node can be built at very low "
              "cost. The node samples the sensors, constructs a compact "
              "message and publishes it to a server over the local wireless "
              "network, where it can be stored, analysed and displayed.")
    h2(doc, "1.4 Machine Learning for Energy Analytics")
    body(doc, "Once a reliable stream of sensor data is available, machine "
              "learning can add value in three ways. First, a regression "
              "model can estimate the generation that the system should be "
              "producing and provide a short-horizon forecast. Second, a "
              "classification model can label the current operating "
              "condition, for example normal, reduced generation, night idle "
              "or fault. Third, an anomaly-detection model can flag readings "
              "that do not fit the expected pattern, which usually indicates a "
              "sensor fault or an equipment problem. Random Forest models are "
              "well suited to this task because they handle mixed-scale "
              "sensor features, are robust to noise and provide feature "
              "importances that can be explained to an operator.")
    h2(doc, "1.5 Problem Statement")
    body(doc, "Small renewable microgrids are often installed without any "
              "monitoring, so their actual performance is unknown and "
              "developing faults go unnoticed until the output collapses. "
              "Commercial monitoring systems are expensive and are usually "
              "closed, which makes them unsuitable for low-cost installations "
              "and for student projects. There is a need for an open, "
              "low-cost platform that continuously monitors a hybrid solar and "
              "wind microgrid, estimates its generation, identifies its "
              "operating condition and anomalies, and recommends how the "
              "available energy should be allocated, while being honest about "
              "the difference between measured values, simulated values and "
              "model predictions.")
    h2(doc, "1.6 Objectives")
    bullets(doc, [
        "To design and build a low-cost ESP8266 sensor node that measures "
        "solar voltage and current, wind voltage and current, turbine speed, "
        "temperature, humidity and light level from a hybrid solar and wind "
        "microgrid.",
        "To develop a Flask REST backend that validates, deduplicates and "
        "stores the incoming telemetry in a SQLite database and exposes the "
        "data through a documented JSON API.",
        "To engineer physically meaningful diagnostic features from the raw "
        "sensor vector and to train Random Forest models for generation "
        "prediction, operating-condition classification and anomaly detection.",
        "To build an interactive web dashboard that shows live telemetry, "
        "historical trends, model outputs and an energy-allocation "
        "recommendation.",
        "To establish a reproducible evaluation using a fixed-seed dataset "
        "and a chronological train, validation and test split, and to report "
        "the honest performance of each model.",
        "To document the working principle, wiring, API contract and "
        "operating procedure so that the platform can be reproduced and "
        "extended.",
    ])
    h2(doc, "1.7 Scope of the Project")
    body(doc, "The project covers the sensor node, the backend, the machine "
              "learning pipeline, the dashboard and the evaluation. It is a "
              "laboratory prototype and uses low-voltage devices only. The "
              "relay output is held off by default and automatic load "
              "switching is deliberately not enabled, because safe switching "
              "requires a correctly rated relay or solid-state relay and a "
              "verified low-voltage bench test. At the time of writing the "
              "firmware has been compiled and verified, but the physical node "
              "has not been operated, so the machine learning models are "
              "trained and evaluated on simulated data.")
    h2(doc, "1.8 Organisation of the Report")
    body(doc, "Chapter 2 reviews the relevant literature and identifies the "
              "research gap. Chapter 3 describes the system architecture, the "
              "hardware, the firmware, the data contract, the database, the "
              "feature engineering and the machine learning models. Chapter 4 "
              "presents the dataset characteristics, the model results and the "
              "dashboard validation. Chapter 5 concludes the work and lists "
              "the future scope. The appendices contain the pin configuration, "
              "a sample API exchange and the installation and operating guide.")


def chapter2(doc):
    chapter_open(doc, 2, "Literature Review")
    h2(doc, "2.1 Introduction")
    body(doc, "This chapter reviews published work on IoT architectures for "
              "energy monitoring, solar and wind generation modelling, machine "
              "learning for generation prediction, anomaly detection and "
              "energy management. The review is used to position the present "
              "project and to identify the gap that it addresses.")
    h2(doc, "2.2 IoT Architectures for Energy Monitoring")
    body(doc, "Al-Fuqaha et al. [1] survey the enabling technologies, "
              "protocols and applications of the Internet of Things and "
              "describe the layered architecture that most monitoring systems "
              "follow: a sensing layer, a network layer and an application "
              "layer. Lazarescu [9] demonstrates that a low-power wireless "
              "sensor platform can collect environmental data over long "
              "periods with minimal maintenance. Gungor et al. [5] review "
              "communication technologies and standards for the smart grid and "
              "note that the choice of communication layer is driven by cost, "
              "range and data rate. These works establish that a "
              "microcontroller with integrated Wi-Fi and a lightweight HTTP "
              "protocol is sufficient for low-rate energy telemetry.")
    h2(doc, "2.3 Solar and Wind Generation Modelling")
    body(doc, "Antonanzas et al. [2] review photovoltaic power forecasting and "
              "classify the methods into physical, statistical and machine "
              "learning families. They observe that the terminal voltage of a "
              "panel follows a saturating curve against irradiance and that "
              "cell temperature modifies this curve, which is the basis of the "
              "voltage-deficit diagnostic feature used in this project. For "
              "wind, the standard model relates the turbine speed to wind "
              "speed through a cut-in speed, a near-linear rise and a rated "
              "region, and the rectified voltage of a small generator is "
              "approximately proportional to the rotational speed above the "
              "rectifier drop. Voyant et al. [14] review machine learning "
              "methods for solar radiation forecasting and confirm that "
              "ensemble methods such as Random Forests are competitive and "
              "require little tuning.")
    h2(doc, "2.4 Machine Learning for Generation Prediction")
    body(doc, "Breiman [3] introduced Random Forests, an ensemble of decision "
              "trees trained on bootstrap samples with random feature subsets, "
              "and showed that the method is accurate, robust to outliers and "
              "provides a natural measure of feature importance. Raza and "
              "Khosravi [12] review artificial-intelligence-based load and "
              "generation forecasting for smart grids and buildings and report "
              "that ensemble tree methods perform well on tabular sensor data. "
              "Kanchev et al. [8] present energy management and operational "
              "planning for a microgrid with a photovoltaic generator and show "
              "how a forecast of the available power improves the dispatch "
              "decision.")
    h2(doc, "2.5 Anomaly and Fault Detection")
    body(doc, "Chandola et al. [4] survey anomaly detection and distinguish "
              "point, contextual and collective anomalies. Sensor faults, "
              "stuck sensors, generation drops, generator mismatch and "
              "over-voltage spikes are point anomalies that appear as unusual "
              "combinations of features rather than as unusual single values. "
              "A supervised classifier can be trained to recognise these "
              "combinations when a labelled fault history is available, which "
              "is the approach taken here. Han et al. [6] describe the "
              "preprocessing, feature construction and evaluation methodology "
              "used for such classification tasks.")
    h2(doc, "2.6 Energy Management and Load Allocation")
    body(doc, "Hatziargyriou et al. [7] introduce microgrids and describe "
              "their control and management requirements. Siano [13] reviews "
              "demand response and smart grids and highlights the role of "
              "real-time information in shifting flexible load to periods of "
              "surplus generation. Lund [10] argues that renewable energy "
              "strategies for sustainable development depend on the "
              "integration of variable sources with flexible demand and "
              "storage. These works motivate the allocation policy implemented "
              "in this project, in which available generation is assigned "
              "first to essential load, then to a reserve, then to deferrable "
              "load and finally to storage.")
    h2(doc, "2.7 Research Gap")
    body(doc, "The reviewed literature provides strong evidence for each "
              "individual building block, but it rarely combines them into a "
              "single, open, low-cost platform for a hybrid solar and wind "
              "microgrid. Table 2.1 summarises the relevant studies and shows "
              "that most concentrate on a single source, on a single task or "
              "on expensive instrumentation. The present project addresses "
              "this gap by integrating a low-cost sensor node, a documented "
              "REST backend, a transparent feature-engineering step, three "
              "Random Forest models and an advisory energy-allocation policy "
              "in one reproducible system, with an explicit separation of "
              "measured, simulated and predicted values.")
    add_table(doc, tcap("2.1"),
              ["Study", "Focus", "Technique", "Limitation"],
              [["Al-Fuqaha et al. [1]", "IoT architecture and protocols",
                "Survey", "No energy application"],
               ["Lazarescu [9]", "Low-power WSN monitoring",
                "Embedded platform", "Environmental data only"],
               ["Antonanzas et al. [2]", "PV power forecasting",
                "Review of methods", "Solar only, no node design"],
               ["Voyant et al. [14]", "Solar radiation forecasting",
                "Machine learning review", "No wind channel, no dashboard"],
               ["Breiman [3]", "Ensemble learning",
                "Random Forest", "Algorithm only"],
               ["Raza and Khosravi [12]", "Load and generation forecasting",
                "AI review", "No hardware integration"],
               ["Chandola et al. [4]", "Anomaly detection",
                "Survey", "Generic, not microgrid-specific"],
               ["Kanchev et al. [8]", "Microgrid energy management",
                "Optimisation and control", "Requires accurate forecasts"],
               ["Siano [13]", "Demand response",
                "Review", "No prediction models"],
               ["This work", "Hybrid solar and wind microgrid",
                "IoT node + Random Forest + dashboard",
                "Simulated evaluation, no field trial"]],
              widths=[30, 40, 38, 37], size=10)
    h2(doc, "2.8 Summary")
    body(doc, "The literature confirms the value of IoT sensing, of Random "
              "Forest models for prediction and of transparent energy "
              "management, but no reviewed work brings these together for a "
              "low-cost hybrid solar and wind microgrid with the same "
              "attention to honesty about measured, simulated and predicted "
              "data. The next chapter describes the system that was built to "
              "fill this gap.")


def chapter3(doc):
    chapter_open(doc, 3, "System Design and Methodology")
    h2(doc, "3.1 Introduction")
    body(doc, "This chapter describes how the platform was designed and built. "
              "It covers the overall architecture, the hardware, the sensor "
              "node firmware, the data contract, the database, the feature "
              "engineering, the synthetic dataset, the machine learning "
              "models, the energy-allocation policy, the dashboard and the "
              "testing approach.")
    h2(doc, "3.2 System Architecture")
    body(doc, "The system is organised as a sensing layer, a network and "
              "storage layer and an application layer, as shown in Figure 3.1. "
              "The sensor node reads the electrical, mechanical and "
              "environmental sensors, builds one JSON reading and posts it to "
              "the backend over the local Wi-Fi network. The backend validates "
              "the reading, stores it in a SQLite database, runs the three "
              "machine learning models and serves the dashboard. The dashboard "
              "runs entirely on the laptop that hosts the backend; the ESP8266 "
              "only publishes readings and never receives control commands.")
    add_figure(doc, DIAGRAMS / "report_architecture.png", fcap("3.1"))
    h2(doc, "3.3 Hardware Design")
    body(doc, "The node is built around the ESP8266 NodeMCU, which provides "
              "Wi-Fi connectivity, one analogue input and sufficient digital "
              "pins for the sensors. The generators are a small 6 V solar "
              "panel and a small DC wind dynamo. Because the microgrid is a "
              "low-voltage laboratory prototype, the measured voltages are "
              "small and the currents are in the milliampere range. Table 3.1 "
              "lists the components and their roles.")
    add_table(doc, tcap("3.1"),
              ["Component", "Specification", "Role"],
              [["ESP8266 NodeMCU", "ESP-12E, 80 MHz, 3.3 V logic",
                "Microcontroller and Wi-Fi node"],
               ["Solar panel", "6 V, 1.5 W", "Solar generation source"],
               ["DC wind dynamo", "Small DC generator with propeller",
                "Wind generation source"],
               ["INA219 (x2)", "I2C, addresses 0x40 and 0x41",
                "Bus voltage and current measurement"],
               ["DHT11", "3.3 V, digital", "Temperature and humidity"],
               ["KY-024 Hall module", "Digital output",
                "Turbine revolution counting"],
               ["LDR module", "Comparator, digital output",
                "Bright and dark light detection"],
               ["Relay module", "Active-low, default OFF",
                "Advisory load switching (disabled)"],
               ["Resistors", "10 kohm pull-up, load resistors",
                "DHT11 pull-up and test load"]],
              widths=[35, 55, 55], size=10)
    h2(doc, "3.4 Sensor Node Firmware")
    body(doc, "The firmware is written for the NodeMCU 1.0 (ESP-12E) board and "
              "is designed to stay responsive: the main loop never blocks for "
              "more than a few milliseconds and uses non-blocking retries for "
              "the Wi-Fi link and for any sensor that failed at boot. Two "
              "INA219 modules share the I2C bus and are distinguished by their "
              "addresses. The Hall-effect module generates an interrupt on "
              "each magnet pass and the revolutions per minute are computed "
              "from the pulse count and the elapsed interval. The pin map is "
              "given in Table 3.2.")
    add_table(doc, tcap("3.2"),
              ["Signal", "Pin", "GPIO", "Notes"],
              [["I2C SDA", "D2", "GPIO4", "Shared by both INA219 modules"],
               ["I2C SCL", "D1", "GPIO5", "Shared by both INA219 modules"],
               ["DHT11 data", "D5", "GPIO14", "10 kohm pull-up to 3V3"],
               ["Hall digital out", "D6", "GPIO12",
                "Interrupt, pulse counting"],
               ["LDR digital out", "D7", "GPIO13", "Bright and dark detection"],
               ["Relay input", "D0", "GPIO16", "Active-low, held OFF"],
               ["On-board LED", "D4", "GPIO2", "Heartbeat blink"]],
              widths=[35, 15, 20, 75], size=10)
    body(doc, "The firmware sends a field as null rather than guessing it. In "
              "particular, generated current cannot be measured when no load "
              "is connected, because the INA219 measures current through its "
              "shunt and an open circuit carries no current; in that case the "
              "current and power fields are sent as null and the dashboard "
              "shows that the current was not measured. The relay is driven to "
              "its off state during start-up and is never switched "
              "automatically.")
    h2(doc, "3.5 Data Contract and REST API")
    body(doc, "The node posts a JSON object to the ingest endpoint. The "
              "backend converts the firmware field names to internal column "
              "names, parses the timestamp, checks every numeric field against "
              "a plausible range and rejects a reading with a precise reason "
              "when it is not usable. Table 3.3 lists the payload fields and "
              "Table 3.4 lists the endpoints exposed by the backend.")
    add_table(doc, tcap("3.3"),
              ["Field", "Type", "Required", "Description"],
              [["device_id", "string", "No", "Node identifier"],
               ["timestamp", "ISO-8601", "No", "UTC sample time"],
               ["solar_voltage", "number", "Yes", "Panel bus voltage (V)"],
               ["solar_current", "number or null", "No",
                "Panel current (A); null when not measurable"],
               ["solar_power", "number or null", "No", "Panel power (W)"],
               ["wind_voltage", "number", "Yes", "Dynamo bus voltage (V)"],
               ["wind_current", "number or null", "No", "Dynamo current (A)"],
               ["wind_power", "number or null", "No", "Dynamo power (W)"],
               ["turbine_rpm", "number", "Yes", "Turbine speed (RPM)"],
               ["temperature", "number", "No", "Ambient temperature (degC)"],
               ["humidity", "number", "No", "Relative humidity (%)"],
               ["light_status", "string", "No",
                "bright, dim, dark or unknown"],
               ["sensor_status", "string", "Yes",
                "OK or a list of failures"],
               ["device_ip", "string", "No", "Node IP address"]],
              widths=[32, 28, 20, 65], size=10)
    add_table(doc, tcap("3.4"),
              ["Method", "Endpoint", "Purpose"],
              [["POST", "/api/ingest",
                "Validate, store and predict one reading"],
               ["GET", "/api/health", "Service and model readiness"],
               ["GET", "/api/overview", "Dashboard aggregate payload"],
               ["GET", "/api/readings/latest",
                "Most recent reading and prediction"],
               ["GET", "/api/readings/history",
                "Historical readings for charts"],
               ["GET", "/api/predictions/series",
                "Predictions joined to readings"],
               ["POST", "/api/predict",
                "Predict for a supplied or latest reading"],
               ["GET", "/api/model/status", "Model metadata and test metrics"],
               ["GET", "/api/model/importance", "Feature importances"],
               ["GET/PUT", "/api/settings", "Runtime configuration"],
               ["POST", "/api/demo/seed",
                "Insert simulated readings for demonstration"],
               ["GET", "/api/export/readings.csv",
                "Download readings as CSV"],
               ["POST", "/api/maintenance/purge", "Delete stored readings"]],
              widths=[22, 55, 68], size=10)
    h2(doc, "3.6 Database Design")
    body(doc, "The backend stores data in a SQLite database with four tables. "
              "Readings are deduplicated on the pair of device identifier and "
              "reading timestamp, so a node that reconnects and re-sends the "
              "same sample cannot pollute the history. The entity-relationship "
              "diagram is shown in Figure 3.2 and the tables are described in "
              "Table 3.5.")
    add_figure(doc, DIAGRAMS / "report_er.png", fcap("3.2"))
    add_table(doc, tcap("3.5"),
              ["Table", "Purpose", "Key columns"],
              [["readings", "One row per accepted sample",
                "id, device_id, reading_timestamp, sensor values"],
               ["devices", "Latest state of each node",
                "device_id, last_seen_unix, total_readings"],
               ["predictions", "Model output per reading",
                "reading_id, predicted_power_w, predicted_condition"],
               ["settings", "Runtime configuration",
                "key, value, updated_at_unix"]],
              widths=[28, 55, 62], size=10)
    h2(doc, "3.7 Data Pipeline and Feature Engineering")
    body(doc, "The platform has two pipelines that share the same feature "
              "engineering code so that training and live inference remain "
              "consistent. The online pipeline processes live readings and the "
              "offline pipeline generates the dataset, trains the models and "
              "produces the evaluation figures. Both pipelines are shown in "
              "Figure 3.3.")
    add_figure(doc, DIAGRAMS / "report_dataflow.png", fcap("3.3"))
    body(doc, "Three diagnostic features are computed from the raw sensor "
              "vector and fixed hardware constants. The solar voltage deficit "
              "compares the measured panel voltage with the clean voltage "
              "expected for the current irradiance and cell temperature, so "
              "partial shading and heavy soiling appear here first. The wind "
              "volts-per-RPM feature measures the effective generator constant, "
              "which falls when the rotor is fouled or the rectifier begins to "
              "fail. The lux-per-irradiance feature measures the agreement "
              "between the light sensor and the irradiance estimate, so a stuck "
              "or shaded light sensor becomes visible. Table 3.6 lists the "
              "features used by every model.")
    add_table(doc, tcap("3.6"),
              ["Feature", "Definition"],
              [["hour", "Hour of day from the reading timestamp"],
               ["day_of_year", "Day of year from the reading timestamp"],
               ["solar_irradiance_wm2", "Irradiance inferred from the LDR"],
               ["solar_voltage", "Measured panel bus voltage (V)"],
               ["wind_voltage", "Measured dynamo bus voltage (V)"],
               ["turbine_rpm", "Measured turbine speed (RPM)"],
               ["temperature_c", "Ambient temperature (degC)"],
               ["humidity_percent", "Relative humidity (%)"],
               ["light_level_lux", "Light level (lux)"],
               ["solar_v_deficit", "Clean panel voltage minus measured voltage"],
               ["wind_v_per_rpm", "Dynamo voltage divided by RPM"],
               ["lux_per_irradiance", "Light level divided by irradiance"]],
              widths=[40, 105], size=10)
    h2(doc, "3.8 Dataset Generation")
    body(doc, "Because the physical node could not be operated during the "
              "evaluation, a reproducible synthetic dataset was generated to "
              "develop and demonstrate the pipeline. The generator models a "
              "solar irradiance curve that depends on the time of day and on "
              "cloud cover, a temperature and humidity cycle, a wind-speed "
              "process with gusts, the panel voltage curve and the rectified "
              "dynamo voltage curve, and the non-fault loss mechanisms of "
              "soiling and becalming. It then injects five labelled faults: a "
              "sensor fault, a stuck sensor, a generation drop, a "
              "voltage-to-RPM mismatch and an over-voltage spike. The dataset "
              "contains 12,000 samples at a five-minute interval, spanning "
              "01 January 2025 to 11 February 2025, and is fully reproducible "
              "for the fixed seed 42.")
    h2(doc, "3.9 Machine Learning Models")
    body(doc, "Three supervised models are trained on the engineered features. "
              "The generation regressor predicts the total estimated power in "
              "watts. The operating-condition classifier predicts one of four "
              "labels: normal, reduced generation, night idle or fault. The "
              "anomaly classifier predicts whether the reading contains an "
              "injected sensor or equipment anomaly. All three are Random "
              "Forest models, which were chosen for their accuracy on tabular "
              "data, their robustness to noise and the interpretable feature "
              "importances they provide. The hyperparameters are listed in "
              "Table 3.7.")
    add_table(doc, tcap("3.7"),
              ["Model", "Estimators", "Other settings", "Target"],
              [["Generation regressor", "220",
                "min_samples_leaf=2, max_features=0.8", "total_est_power_w"],
               ["Condition classifier", "220",
                "balanced_subsample, min_samples_leaf=2",
                "operating_condition"],
               ["Anomaly classifier", "220",
                "balanced_subsample, min_samples_leaf=2", "anomaly_label"]],
              widths=[38, 22, 55, 35], size=10)
    body(doc, "The dataset is divided chronologically into 70 % training, "
              "15 % validation and 15 % test partitions. A random shuffle is "
              "deliberately avoided so that the model cannot see the future, "
              "which would inflate every reported score. The validation set is "
              "used for sanity checks and the test set is used exactly once, "
              "to report the final honest numbers. The fixed random state "
              "ensures that the whole experiment can be reproduced.")
    h2(doc, "3.10 Energy Allocation Policy")
    body(doc, "The energy-allocation component is a transparent rule-based "
              "policy rather than a learned controller. It answers a single "
              "question: given the power that is being generated right now, "
              "how should it be split between essential load, a reserve, "
              "deferrable load and storage. Table 3.8 lists the tiers of the "
              "policy. The relay is never switched automatically, and the "
              "recommendation becomes advisory only whenever the node is "
              "offline or the generation cannot be measured.")
    add_table(doc, tcap("3.8"),
              ["Tier", "Description", "Default"],
              [["Essential load", "Served first, unconditionally", "1.5 W"],
               ["Reserve", "Held back before discretionary load", "5.0 W"],
               ["Deferrable load", "Served only if surplus remains", "4.0 W"],
               ["Storage", "Receives any remaining surplus", "Remainder"]],
              widths=[35, 90, 30], size=10)
    h2(doc, "3.11 Dashboard")
    body(doc, "The dashboard is a single-page web application served by the "
              "same Flask process. It uses a dark charcoal theme with an "
              "emerald-green accent and a local copy of the Chart.js library so "
              "that it works without an internet connection. It presents seven "
              "sections: an overview, live monitoring, AI analytics, energy "
              "optimization, historical data, model and system status, and "
              "settings. The settings page never reveals the device token or "
              "any stored secret in full.")
    h2(doc, "3.12 Software and Toolchain")
    body(doc, "The software is written in Python and JavaScript. Table 3.9 "
              "lists the principal tools and their roles. The platform runs on "
              "Python 3.8 and is served by the built-in Flask development "
              "server for demonstration.")
    add_table(doc, tcap("3.9"),
              ["Tool / Library", "Version", "Role"],
              [["Python", "3.8", "Backend and machine learning"],
               ["Flask", "2.3.3", "REST API and dashboard server"],
               ["pandas / numpy", "2.0.3 / 1.24.4", "Data processing"],
               ["scikit-learn", "1.3.2", "Random Forest models"],
               ["joblib", "1.4.2", "Model persistence"],
               ["matplotlib / seaborn", "3.7.2 / 0.12.2",
                "Evaluation figures"],
               ["SQLite", "bundled", "Persistent storage"],
               ["Chart.js", "4.4.1", "Dashboard charts"],
               ["Arduino ESP8266 core", "3.1.2", "Firmware compilation"]],
              widths=[40, 30, 75], size=10)
    h2(doc, "3.13 Testing Approach")
    body(doc, "The backend is covered by an automated test suite that runs "
              "against a temporary database so that the development database "
              "is never modified. The suite exercises payload validation, the "
              "database layer, every API route, the dataset generator, the "
              "training pipeline and the inference service. One hundred and "
              "five tests are defined, and a training test runs a real, small "
              "fit to confirm that the whole pipeline works end to end.")
    h2(doc, "3.14 Summary")
    body(doc, "This chapter described the architecture, the hardware, the "
              "firmware, the data contract, the database, the feature "
              "engineering, the dataset, the machine learning models, the "
              "allocation policy, the dashboard and the testing approach. The "
              "next chapter presents the results obtained from this system.")


def chapter4(doc):
    chapter_open(doc, 4, "Results and Discussion")
    h2(doc, "4.1 Introduction")
    body(doc, "This chapter presents and discusses the results. It begins with "
              "the characteristics of the dataset, then examines the sensor "
              "and generation relationships, then reports the performance of "
              "the three models on the held-out test set, then presents the "
              "energy-allocation results and the dashboard validation. It "
              "concludes with the limitations of the evaluation.")
    h2(doc, "4.2 Dataset Characteristics")
    body(doc, "The generated dataset contains 12,000 samples and 27 columns, "
              "with no null values and no duplicated timestamps. Table 4.1 "
              "summarises its composition. The anomaly types are distributed "
              "as shown in Table 4.2 and the operating conditions as shown in "
              "Figure 4.1; the dataset is imbalanced, with normal operation "
              "dominating and fault conditions being relatively rare, which is "
              "why the classifiers use balanced class weighting.")
    add_table(doc, tcap("4.1"),
              ["Property", "Value"],
              [["Number of samples", "12,000"],
               ["Number of columns", "27"],
               ["Sample interval", "5 minutes"],
               ["Time range", "01 Jan 2025 to 11 Feb 2025"],
               ["Null cells", "0"],
               ["Anomaly rate", "7.49 %"],
               ["Random seed", "42"],
               ["Train / validation / test", "8400 / 1800 / 1800"]],
              widths=[70, 75], size=10)
    add_table(doc, tcap("4.2"),
              ["Anomaly type", "Count"],
              [["none", "11101"], ["generation_drop", "268"],
               ["sensor_fault", "241"], ["voltage_rpm_mismatch", "197"],
               ["overvoltage_spike", "124"], ["sensor_stuck", "69"]],
              widths=[70, 75], size=10)
    add_figure(doc, GRAPHS / "operating_condition_distribution.png", fcap("4.1"))
    h2(doc, "4.3 Sensor and Generation Analysis")
    body(doc, "Figure 4.2 shows the panel voltage and the solar power over "
              "time. The voltage rises quickly with irradiance and then "
              "saturates, which is the expected behaviour of a small panel. "
              "Figure 4.3 shows the dynamo voltage and the turbine speed over "
              "time and confirms that the rectified voltage tracks the speed "
              "above the rectifier drop. Figure 4.4 shows that the light level "
              "and the solar generation are strongly related, which supports "
              "the use of the light sensor as a proxy for irradiance. Figure "
              "4.5 shows the relationship between the turbine speed and the "
              "wind generation. Figure 4.6 shows the relative contribution of "
              "the solar and wind channels to the total generation and "
              "illustrates the complementary nature of the two sources.")
    add_figure(doc, GRAPHS / "solar_voltage_power_over_time.png", fcap("4.2"), 118)
    add_figure(doc, GRAPHS / "wind_voltage_rpm_over_time.png", fcap("4.3"), 118)
    add_figure(doc, GRAPHS / "light_vs_solar_generation.png", fcap("4.4"), 118)
    add_figure(doc, GRAPHS / "rpm_vs_wind_generation.png", fcap("4.5"), 118)
    add_figure(doc, GRAPHS / "solar_vs_wind_contribution.png", fcap("4.6"), 118)
    h2(doc, "4.4 Generation Prediction Results")
    body(doc, "The generation regressor was evaluated on the 1,800 held-out "
              "test samples. Table 4.3 reports the metrics on both the "
              "validation and the test partitions. The mean absolute error on "
              "the test set is 0.0147 W and the coefficient of determination "
              "is 0.9968, which means that almost all of the variation in the "
              "generation is explained by the sensor features. Figure 4.7 "
              "shows the predicted power against the actual power and Figure "
              "4.8 shows the regression evaluation. Figure 4.9 shows the "
              "generation trend and forecast over the test period. Figure 4.10 "
              "compares the model scores for a compact summary.")
    add_table(doc, tcap("4.3"),
              ["Metric", "Validation", "Test"],
              [["Mean absolute error (W)", "0.0202", "0.0147"],
               ["Root mean square error (W)", "0.0399", "0.0251"],
               ["Coefficient of determination", "0.9926", "0.9968"],
               ["Maximum absolute error (W)", "0.8459", "0.2018"]],
              widths=[65, 40, 40], size=10)
    add_figure(doc, GRAPHS / "actual_vs_predicted_heldout.png", fcap("4.7"), 118)
    add_figure(doc, GRAPHS / "regression_evaluation.png", fcap("4.8"), 118)
    add_figure(doc, GRAPHS / "generation_trend_forecast.png", fcap("4.9"), 118)
    add_figure(doc, GRAPHS / "model_score_comparison.png", fcap("4.10"), 118)
    h2(doc, "4.5 Operating-Condition Classification Results")
    body(doc, "The operating-condition classifier achieved an accuracy of "
              "0.8528 and a macro F1 score of 0.8365 on the held-out test set. "
              "Table 4.4 reports the per-class precision, recall and F1 score, "
              "and Figure 4.11 shows the confusion matrix. The night-idle and "
              "fault classes are detected reliably, while the "
              "reduced-generation class is the most difficult, because a "
              "moderate reduction in output lies close to normal operation and "
              "is sometimes misclassified as normal. This is an acceptable "
              "trade-off for a monitoring system, in which a missed early "
              "degradation is less dangerous than frequent false alarms.")
    add_table(doc, tcap("4.4"),
              ["Class", "Precision", "Recall", "F1 score", "Support"],
              [["fault", "0.953", "0.795", "0.867", "127"],
               ["night_idle", "0.976", "1.000", "0.988", "82"],
               ["normal", "0.878", "0.933", "0.904", "1261"],
               ["reduced_generation", "0.652", "0.533", "0.587", "330"],
               ["Macro average", "0.865", "0.815", "0.837", "1800"]],
              widths=[45, 25, 22, 25, 25], size=10)
    add_figure(doc, GRAPHS / "confusion_matrix_condition.png", fcap("4.11"), 112)
    h2(doc, "4.6 Anomaly Detection Results")
    body(doc, "The anomaly detector achieved an accuracy of 0.9861 on the "
              "held-out test set, with a precision of 0.9636 and a recall of "
              "0.8346. Table 4.5 reports the metrics and Figure 4.12 shows the "
              "confusion matrix. The detector is precise, which means that it "
              "rarely raises a false alarm, and it recovers a large fraction "
              "of the injected anomalies. The false negatives are "
              "predominantly the mild generation drops that are hard to "
              "separate from legitimate soiling. Figure 4.13 contrasts the "
              "normal and anomalous patterns.")
    add_table(doc, tcap("4.5"),
              ["Metric", "Value"],
              [["Accuracy", "0.9861"], ["Precision", "0.9636"],
               ["Recall", "0.8346"], ["F1 score", "0.8945"],
               ["Specificity", "0.9976"],
               ["True positives / false negatives", "106 / 21"],
               ["False positives / true negatives", "4 / 1669"]],
              widths=[70, 75], size=10)
    add_figure(doc, GRAPHS / "confusion_matrix_anomaly.png", fcap("4.12"), 112)
    add_figure(doc, GRAPHS / "normal_vs_anomalous_patterns.png", fcap("4.13"), 118)
    h2(doc, "4.7 Feature Importance")
    body(doc, "Figure 4.14 shows the feature importances of the generation "
              "regressor and Table 4.6 lists them. The two measured voltages "
              "dominate, which is expected because they are directly related "
              "to the generated power. The turbine speed and the irradiance "
              "estimate are the next most important, and the engineered "
              "diagnostic features contribute the remainder. The ordering "
              "confirms that the model is learning physically meaningful "
              "relationships rather than memorising the data.")
    add_table(doc, tcap("4.6"),
              ["Feature", "Importance"],
              [["solar_voltage", "0.4122"], ["wind_voltage", "0.3773"],
               ["turbine_rpm", "0.0734"], ["solar_irradiance_wm2", "0.0385"],
               ["light_level_lux", "0.0372"], ["lux_per_irradiance", "0.0324"],
               ["wind_v_per_rpm", "0.0247"], ["solar_v_deficit", "0.0028"]],
              widths=[70, 75], size=10)
    add_figure(doc, GRAPHS / "feature_importance.png", fcap("4.14"), 118)
    h2(doc, "4.8 Energy Optimization Results")
    body(doc, "The allocation policy was applied to a set of representative "
              "generation levels. Table 4.7 shows four scenarios. When the "
              "generation is zero, the status is unknown and a recommendation "
              "is produced without switching the relay. When the generation is "
              "below the demand, the status is deficit and the policy advises "
              "shedding the deferrable load before the essential load. When the "
              "generation just covers the demand, the status is balanced. When "
              "the generation exceeds the demand and the reserve, the surplus "
              "is assigned to storage and the status is surplus.")
    add_table(doc, tcap("4.7"),
              ["Scenario", "Generation", "Status", "Essential", "Deferrable",
               "Storage"],
              [["A", "0.0 W", "unknown", "0.0", "0.0", "0.0"],
               ["B", "1.0 W", "deficit", "1.0", "0.0", "0.0"],
               ["C", "5.5 W", "balanced", "1.5", "4.0", "0.0"],
               ["D", "8.0 W", "surplus", "1.5", "4.0", "2.5"]],
              widths=[20, 22, 22, 22, 24, 20], size=10)
    body(doc, "The essential-load tier is always served first, the reserve is "
              "held back before any discretionary load, and the deferrable load "
              "is served only while a surplus remains. This policy is "
              "transparent and easy to explain to an operator, which was the "
              "intended design goal.")
    h2(doc, "4.9 API and Dashboard Validation")
    body(doc, "The backend was started and exercised with real HTTP requests. "
              "The health endpoint reported the service as healthy with the "
              "models loaded, the overview and history endpoints returned valid "
              "payloads, the dashboard page was served correctly, the "
              "evaluation figures were served as static files and an unknown "
              "figure correctly returned a not-found response. A telemetry "
              "tick inserted a simulated reading and produced a prediction, "
              "which confirms that the ingestion and inference path works end "
              "to end.")
    h2(doc, "4.10 Limitations of the Evaluation")
    body(doc, "The reported metrics characterise the software pipeline on "
              "simulated data and are not a claim of field accuracy. The "
              "synthetic faults are cleanly separable, so the measured F1 "
              "scores overstate what a real, noisy sensor stream would "
              "produce. The estimated currents come from the same simulation "
              "model as the target, so the regression task is easier than a "
              "real one. The physical node has not been operated, so no field "
              "measurement of the sensors or of the models has been made. "
              "Finally, no battery state of charge, cloud forecast or tariff "
              "signal is modelled, so the optimiser remains a rule-based "
              "demonstration.")
    h2(doc, "4.11 Summary")
    body(doc, "The results show that the pipeline predicts generation with a "
              "very small error, classifies the operating condition with good "
              "accuracy and detects anomalies with high precision, all on a "
              "held-out chronological test set. The limitations of simulating "
              "the data are stated explicitly, and the next chapter concludes "
              "the work and describes how these limitations can be removed.")


def chapter5(doc):
    chapter_open(doc, 5, "Conclusion and Future Scope")
    h2(doc, "5.1 Conclusion")
    body(doc, "This project designed, built and evaluated a low-cost IoT "
              "platform for the predictive monitoring and energy optimization "
              "of a hybrid solar and wind microgrid. The platform integrates an "
              "ESP8266 sensor node, a Flask REST backend with SQLite storage, a "
              "transparent feature-engineering step, three Random Forest models "
              "and a dark-themed web dashboard. Measured values, simulated "
              "values and model predictions are kept separate throughout so "
              "that no estimated number is ever presented as a measurement.")
    body(doc, "On a reproducible simulated dataset of 12,000 samples with a "
              "strictly chronological split, the generation regressor achieved "
              "a mean absolute error of 0.0147 W and a coefficient of "
              "determination of 0.9968, the operating-condition classifier "
              "achieved an accuracy of 0.8528 with a macro F1 score of 0.8365, "
              "and the anomaly detector achieved an accuracy of 0.9861 with a "
              "precision of 0.9636 and a recall of 0.8346. The energy "
              "allocation policy produced transparent and explainable "
              "recommendations for essential load, reserve, deferrable load and "
              "storage, while keeping the relay off by default for safety.")
    body(doc, "The objectives set out in Chapter 1 were met: the node, the "
              "backend, the models and the dashboard were all implemented and "
              "verified as software, the evaluation was made reproducible, and "
              "the system was documented so that it can be reproduced and "
              "extended. The principal limitation is that the physical node "
              "was not operated during the evaluation, so the reported metrics "
              "reflect the software pipeline rather than proven field "
              "performance.")
    h2(doc, "5.2 Future Scope")
    bullets(doc, [
        "Deploy the node on the physical bench, replace the synthetic dataset "
        "with a real sensor log and retrain the models to obtain genuine field "
        "accuracy figures.",
        "Add an accurate pyranometer or calibrate the light-sensor curve "
        "against a reference so that the irradiance estimate improves.",
        "Introduce a battery model with a state-of-charge estimate and a "
        "simple charge and discharge controller.",
        "Integrate a short-horizon weather forecast so that the allocation "
        "policy can plan ahead instead of reacting to the current reading.",
        "Enable the relay for automatic load switching only after a verified "
        "low-voltage bench test with a correctly rated relay or solid-state "
        "relay.",
        "Add multi-node support so that several microgrid nodes can be "
        "monitored from a single dashboard.",
        "Add authentication and transport security so that the platform can be "
        "deployed beyond a trusted local network.",
        "Package the platform as a container with a production WSGI server for "
        "long-term unattended operation.",
    ])
    h2(doc, "5.3 Sustainable Development Goals")
    body(doc, "The project supports SDG 7 (Affordable and Clean Energy) by "
              "improving the usable output of renewable generation, SDG 9 "
              "(Industry, Innovation and Infrastructure) through the use of "
              "low-cost IoT and machine learning, and SDG 13 (Climate Action) "
              "by encouraging the efficient use of clean energy.")


# --------------------------------------------------------------------------- #
# Appendices and references
# --------------------------------------------------------------------------- #
def appendices(doc):
    h1(doc, "Appendix 1 - Pin Configuration and Wiring")
    body(doc, "The node uses the default I2C pins of the ESP8266, so both "
              "INA219 modules share the same SDA and SCL lines and are "
              "distinguished by their addresses. All modules and both "
              "generators must share a common ground.")
    add_table(doc, "Table A1.1  Connection summary",
              ["Module", "Module pin", "ESP8266 pin", "Remarks"],
              [["INA219 solar", "VCC / GND / SDA / SCL", "3V3 / GND / D2 / D1",
                "Address 0x40"],
               ["INA219 wind", "VCC / GND / SDA / SCL", "3V3 / GND / D2 / D1",
                "Address 0x41 (A0 bridged)"],
               ["DHT11", "VCC / GND / DATA", "3V3 / GND / D5",
                "10 kohm pull-up on DATA"],
               ["KY-024", "VCC / GND / DO", "3V3 / GND / D6",
                "One pulse per magnet pass"],
               ["LDR module", "VCC / GND / DO", "3V3 / GND / D7",
                "Set active-low in firmware"],
               ["Relay", "VCC / GND / IN", "VU / GND / D0",
                "Active-low, default OFF"]],
              widths=[30, 42, 35, 38], size=10)

    h1(doc, "Appendix 2 - Sample API Exchange")
    body(doc, "The following example shows a single reading posted by the node "
              "and the response returned by the backend. The current and power "
              "fields are null because no load is connected.")
    para(doc, "Request  POST /api/ingest", 12, True, align=LEFT, line=1.0,
         before=6, after=2)
    code_block(doc, [
        "Content-Type: application/json",
        "X-Device-Token: <device-token>",
        "{",
        '  "device_id": "ESP8266-GRID-01",',
        '  "timestamp": "2025-01-01T12:00:00+00:00",',
        '  "solar_voltage": 5.42, "solar_current": null, "solar_power": null,',
        '  "wind_voltage": 2.81, "wind_current": null, "wind_power": null,',
        '  "turbine_rpm": 640.0, "temperature": 28.5, "humidity": 61.0,',
        '  "light_status": "bright", "sensor_status": "OK",',
        '  "device_ip": "192.168.43.37"',
        "}",
    ])
    para(doc, "Response  201 Created", 12, True, align=LEFT, line=1.0,
         before=6, after=2)
    code_block(doc, [
        "{",
        '  "status": "ok",',
        '  "data": {',
        '    "accepted": true, "duplicate": false, "reading_id": 1,',
        '    "prediction": {',
        '      "predicted_power_w": 0.3917,',
        '      "predicted_condition": "normal",',
        '      "condition_confidence": 0.87,',
        '      "anomaly_probability": 0.02, "anomaly_flag": 0,',
        '      "model_version": "1.0.0"',
        "    }",
        "  },",
        '  "server_time": "2025-01-01T12:00:01+00:00"',
        "}",
    ])

    h1(doc, "Appendix 3 - Installation and Operating Guide")
    body(doc, "The project is distributed as a single archive. The following "
              "steps describe how to run the backend and the dashboard on a "
              "Windows machine.")
    body(doc, "Step 1: install Python 3.8 and the required packages with "
              "pip install -r requirements.txt, or run install.bat.")
    body(doc, "Step 2: generate the dataset and train the models by running "
              "python -m ml.generate_dataset followed by python -m ml.train, "
              "or run the helper script scripts/run_pipeline.py.")
    body(doc, "Step 3: start the backend with run.bat or with python -m "
              "backend.app. The dashboard is then available at the local host "
              "address on port 5000.")
    body(doc, "Step 4: copy firmware/microgrid_node/credentials.example.h to "
              "credentials.h, enter the Wi-Fi name, the Wi-Fi password and the "
              "backend address, and compile and upload the firmware with the "
              "Arduino tools.")
    body(doc, "Step 5: open the dashboard, confirm that the device appears as "
              "online and that readings are arriving, and use the settings "
              "page to adjust the sampling interval and the anomaly threshold. "
              "A demonstration feed can be started from the settings page when "
              "no hardware is connected.")


def code_block(doc, lines):
    for line in lines:
        p = para(doc, line, 10, align=LEFT, line=1.0, before=0, after=0)
        p.paragraph_format.left_indent = Twips(720)


REFERENCES = [
    "Al-Fuqaha, A., Guizani, M., Mohammadi, M., Aledhari, M., & Ayyash, M. "
    "(2015). Internet of Things: A survey on enabling technologies, protocols, "
    "and applications. IEEE Communications Surveys & Tutorials, 17(4), "
    "2347-2376. https://doi.org/10.1109/COMST.2015.2444095",
    "Antonanzas, J., Osorio, N., Escobar, R., Urraca, R., Martinez-de-Pison, "
    "F. J., & Antonanzas-Torres, F. (2016). Review of photovoltaic power "
    "forecasting. Solar Energy, 136, 78-111. "
    "https://doi.org/10.1016/j.solener.2016.06.069",
    "Breiman, L. (2001). Random forests. Machine Learning, 45(1), 5-32. "
    "https://doi.org/10.1023/A:1010933404324",
    "Chandola, V., Banerjee, A., & Kumar, V. (2009). Anomaly detection: A "
    "survey. ACM Computing Surveys, 41(3), 1-58. "
    "https://doi.org/10.1145/1541880.1541882",
    "Gungor, V. C., Sahin, D., Kocak, T., Ergut, S., Buccella, C., Cecati, C., "
    "& Hancke, G. P. (2011). Smart grid technologies: Communication "
    "technologies and standards. IEEE Transactions on Industrial Informatics, "
    "7(4), 529-539. https://doi.org/10.1109/TII.2011.2166794",
    "Han, J., Pei, J., & Tong, H. (2022). Data Mining: Concepts and Techniques "
    "(4th ed.). Morgan Kaufmann.",
    "Hatziargyriou, N., Asano, H., Iravani, R., & Marnay, C. (2007). "
    "Microgrids. IEEE Power and Energy Magazine, 5(4), 78-94. "
    "https://doi.org/10.1109/MPAE.2007.376583",
    "Kanchev, H., Lu, D., Colas, F., Lazarov, V., & Francois, B. (2011). "
    "Energy management and operational planning of a microgrid with a "
    "PV-based active generator for smart grid applications. IEEE Transactions "
    "on Industrial Electronics, 58(10), 4583-4592. "
    "https://doi.org/10.1109/TIE.2011.2123853",
    "Lazarescu, M. T. (2013). Design of a WSN platform for long-term "
    "environmental monitoring for IoT applications. IEEE Journal on Emerging "
    "and Selected Topics in Circuits and Systems, 3(1), 45-54. "
    "https://doi.org/10.1109/JETCAS.2013.2243032",
    "Lund, H. (2007). Renewable energy strategies for sustainable development. "
    "Energy, 32(6), 912-919. https://doi.org/10.1016/j.energy.2006.10.017",
    "Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., "
    "Grisel, O., Blondel, M., Prettenhofer, P., Weiss, R., Dubourg, V., "
    "Vanderplas, J., Passos, A., Cournapeau, D., Brucher, M., Perrot, M., & "
    "Duchesnay, E. (2011). Scikit-learn: Machine learning in Python. Journal "
    "of Machine Learning Research, 12, 2825-2830.",
    "Raza, M. Q., & Khosravi, A. (2015). A review on artificial intelligence "
    "based load demand forecasting techniques for smart grid and buildings. "
    "Renewable and Sustainable Energy Reviews, 50, 1352-1372. "
    "https://doi.org/10.1016/j.rser.2015.04.065",
    "Siano, P. (2014). Demand response and smart grids - A survey. Renewable "
    "and Sustainable Energy Reviews, 30, 461-478. "
    "https://doi.org/10.1016/j.rser.2013.10.022",
    "Voyant, C., Notton, G., Kalogirou, S., Nivet, M.-L., Paoli, C., Motte, F., "
    "& Fouilloy, A. (2017). Machine learning methods for solar radiation "
    "forecasting: A review. Renewable Energy, 105, 569-582. "
    "https://doi.org/10.1016/j.renene.2016.12.095",
]


def references(doc):
    h1(doc, "References")
    blank(doc, count=4)
    for item in REFERENCES:
        p = para(doc, item, 12, align=LEFT, line=1.0, before=0, after=6)
        pf = p.paragraph_format
        pf.left_indent = Mm(10)
        pf.first_line_indent = Mm(-10)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def configure_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(14)
    normal.font.color.rgb = BLACK
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        st = doc.styles[name]
        st.font.name = FONT
        st.font.size = Pt(14)
        st.font.bold = True
        st.font.color.rgb = BLACK


def build():
    if not (DIAGRAMS / "report_architecture.png").exists():
        subprocess.run([sys.executable, str(HERE / "make_diagrams.py")],
                       cwd=str(HERE), check=False)

    doc = Document()
    configure_styles(doc)
    setup_margins(doc.sections[0])

    cover_page(doc)

    doc.add_section(WD_SECTION.NEW_PAGE)
    bonafide(doc)
    acknowledgement(doc)
    vision_mission(doc)
    peo_po_pso(doc)
    co_mapping(doc)
    relevance(doc)
    abstract(doc)
    toc(doc)
    caption_list(doc, "List of Tables", "Table No.",
                 [(k, TBL[k]) for k in TBL_ORDER])
    caption_list(doc, "List of Figures", "Figure No.",
                 [(k, FIG[k]) for k in FIG_ORDER])
    list_of_symbols(doc)

    doc.add_section(WD_SECTION.NEW_PAGE)
    chapter1(doc)
    chapter2(doc)
    chapter3(doc)
    chapter4(doc)
    chapter5(doc)
    appendices(doc)
    references(doc)

    for section in doc.sections:
        setup_margins(section)
    clear_footer(doc.sections[0])
    footer_page_number(doc.sections[1])
    set_pgnum(doc.sections[1], fmt="lowerRoman", start=1)
    footer_page_number(doc.sections[2])
    set_pgnum(doc.sections[2], fmt="decimal", start=1)

    doc.save(str(OUT_DOCX))
    print("wrote", OUT_DOCX)


def main():
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
