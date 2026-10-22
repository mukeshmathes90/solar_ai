# -*- coding: utf-8 -*-
"""Finalise the VCEW mini-project report with Microsoft Word (COM).

Steps
-----
1. Open the generated .docx.
2. Update every field (Table of Contents + PAGE fields in footers).
3. Fill the "Page No." column of the List of Tables and the List of Figures by
   locating each caption paragraph in the body and reading its page number.
4. Export the finished document to PDF.
5. Print page counts so the layout rules can be verified.

Run:  "C:\\Program Files\\Python38\\python.exe" finalize_report.py
"""

from __future__ import annotations

from pathlib import Path

import pythoncom
import win32com.client as win32

HERE = Path(__file__).resolve().parent
DOCX = HERE / "Microgrid_AI_Mini_Project_Report.docx"
PDF = HERE / "Microgrid_AI_Mini_Project_Report.pdf"

WD_ACTIVE_END_ADJUSTED_PAGE_NUMBER = 1
WD_EXPORT_FORMAT_PDF = 17
WD_ALIGN_CENTER = 1
WD_ALIGN_LEFT = 0
WD_STATISTIC_PAGES = 2
WD_STATISTIC_WORDS = 0
WD_DO_NOT_SAVE_CHANGES = 0


def clean(text: str) -> str:
    return (text or "").replace("\r", "").replace("\x07", "").strip()


def collect_caption_pages(doc):
    """Map 'Table 2.1' / 'Figure 3.1' prefixes to page numbers."""
    pages = {}
    total = doc.Paragraphs.Count
    for i in range(1, total + 1):
        p = doc.Paragraphs(i)
        txt = clean(p.Range.Text)
        if txt.startswith("Table ") or txt.startswith("Figure "):
            head = txt.split("  ")[0].strip()
            if head and head not in pages:
                pages[head] = p.Range.Information(
                    WD_ACTIVE_END_ADJUSTED_PAGE_NUMBER)
    return pages


def find_list_table(doc, marker):
    for tbl in doc.Tables:
        try:
            first = clean(tbl.Cell(1, 1).Range.Text)
        except Exception:
            continue
        if first == marker:
            return tbl
    return None


def fill_list(doc, tbl, pages, prefix):
    filled = 0
    missing = []
    for r in range(2, tbl.Rows.Count + 1):
        number = clean(tbl.Cell(r, 1).Range.Text)
        key = "%s %s" % (prefix, number)
        page = pages.get(key)
        if page is None:
            missing.append(key)
            continue
        cell = tbl.Cell(r, 3)
        cell.Range.Text = str(page)
        cell.Range.Font.Name = "Times New Roman"
        cell.Range.Font.Size = 12
        cell.Range.Font.Bold = 0
        cell.Range.ParagraphFormat.Alignment = WD_ALIGN_CENTER
        filled += 1
    return filled, missing


def main():
    if not DOCX.exists():
        raise SystemExit("missing %s" % DOCX)

    pythoncom.CoInitialize()
    app = win32.gencache.EnsureDispatch("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    doc = app.Documents.Open(str(DOCX))

    try:
        # 1. Update the table of contents and all fields.
        try:
            if doc.TablesOfContents.Count > 0:
                doc.TablesOfContents(1).Update()
                print("TOC entries:", doc.TablesOfContents(1).Range
                      .Paragraphs.Count)
            else:
                print("WARNING: no TOC field found")
        except Exception as exc:  # noqa: BLE001
            print("TOC update failed:", exc)
        doc.Fields.Update()

        # 2. Collect caption page numbers and fill the two lists.
        pages = collect_caption_pages(doc)
        print("captions located:", len(pages))

        tbl_tables = find_list_table(doc, "Table No.")
        tbl_figures = find_list_table(doc, "Figure No.")
        if tbl_tables is None or tbl_figures is None:
            raise SystemExit("could not find List of Tables / Figures tables")

        n1, miss1 = fill_list(doc, tbl_tables, pages, "Table")
        n2, miss2 = fill_list(doc, tbl_figures, pages, "Figure")
        print("List of Tables filled:", n1, "missing:", miss1)
        print("List of Figures filled:", n2, "missing:", miss2)

        # 3. Force a field refresh so PAGE numbers settle, then export.
        doc.Fields.Update()

        words = doc.ComputeStatistics(WD_STATISTIC_WORDS)
        n_pages = doc.ComputeStatistics(WD_STATISTIC_PAGES)
        print("total pages:", n_pages, "words:", words)

        # Report the page number of a few landmarks.
        for needle in ("BONAFIDE CERTIFICATE", "TABLE OF CONTENTS",
                       "CHAPTER 1", "REFERENCES"):
            found = None
            for i in range(1, doc.Paragraphs.Count + 1):
                txt = clean(doc.Paragraphs(i).Range.Text)
                if txt.startswith(needle):
                    found = doc.Paragraphs(i).Range.Information(
                        WD_ACTIVE_END_ADJUSTED_PAGE_NUMBER)
                    break
            print("landmark %-22s page=%s" % (needle, found))

        doc.Save()
        doc.ExportAsFixedFormat(
            OutputFileName=str(PDF),
            ExportFormat=WD_EXPORT_FORMAT_PDF,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
        print("wrote", PDF)
    finally:
        doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
        app.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
