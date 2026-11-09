#!/usr/bin/env python3
"""Generate templates/reference.docx with the CV's Word styles.

Run this once (or after changing the design):
    python3 tools/make_reference_docx.py

It starts from pandoc's default reference document and rewrites the handful of
styles the CV uses, so DOCX output matches the PDF/HTML look.
"""

from __future__ import annotations

import io
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "templates" / "reference.docx"

ACCENT = "1F4E79"
TEXT = "333333"
FONT = "Arial"

STYLES = {
    "Normal": f"""
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
  <w:name w:val="Normal"/>
  <w:qFormat/>
  <w:pPr><w:spacing w:after="80" w:line="240" w:lineRule="auto"/></w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="{FONT}" w:eastAsia="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>
    <w:color w:val="{TEXT}"/>
    <w:sz w:val="20"/><w:szCs w:val="20"/>
  </w:rPr>
</w:style>
""",
    "BodyText": f"""
<w:style w:type="paragraph" w:styleId="BodyText">
  <w:name w:val="Body Text"/>
  <w:basedOn w:val="Normal"/>
  <w:link w:val="BodyTextChar"/>
  <w:pPr><w:spacing w:before="0" w:after="10" w:line="236" w:lineRule="auto"/></w:pPr>
  <w:qFormat/>
</w:style>
""",
    "Compact": f"""
<w:style w:type="paragraph" w:customStyle="1" w:styleId="Compact">
  <w:name w:val="Compact"/>
  <w:basedOn w:val="BodyText"/>
  <w:qFormat/>
  <w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
</w:style>
""",
    "Heading1": f"""
<w:style w:type="paragraph" w:styleId="Heading1">
  <w:name w:val="Heading 1"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="BodyText"/>
  <w:uiPriority w:val="9"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/><w:keepLines/>
    <w:spacing w:before="0" w:after="80"/>
    <w:outlineLvl w:val="0"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="{FONT}" w:eastAsia="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>
    <w:b/><w:bCs/>
    <w:color w:val="{ACCENT}"/>
    <w:sz w:val="40"/><w:szCs w:val="40"/>
  </w:rPr>
</w:style>
""",
    "Heading2": f"""
<w:style w:type="paragraph" w:styleId="Heading2">
  <w:name w:val="Heading 2"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="BodyText"/>
  <w:uiPriority w:val="9"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/><w:keepLines/>
    <w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{ACCENT}"/></w:pBdr>
    <w:spacing w:before="180" w:after="50"/>
    <w:outlineLvl w:val="1"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="{FONT}" w:eastAsia="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>
    <w:b/><w:bCs/>
    <w:color w:val="{ACCENT}"/>
    <w:sz w:val="24"/><w:szCs w:val="24"/>
  </w:rPr>
</w:style>
""",
    "Heading3": f"""
<w:style w:type="paragraph" w:styleId="Heading3">
  <w:name w:val="Heading 3"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="BodyText"/>
  <w:uiPriority w:val="9"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/><w:keepLines/>
    <w:spacing w:before="160" w:after="40"/>
    <w:outlineLvl w:val="2"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="{FONT}" w:eastAsia="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>
    <w:b/><w:bCs/>
    <w:color w:val="{ACCENT}"/>
    <w:sz w:val="21"/><w:szCs w:val="21"/>
  </w:rPr>
</w:style>
""",
    "Hyperlink": f"""
<w:style w:type="character" w:styleId="Hyperlink">
  <w:name w:val="Hyperlink"/>
  <w:basedOn w:val="DefaultParagraphFont"/>
  <w:rPr>
    <w:color w:val="{ACCENT}"/>
    <w:u w:val="none"/>
  </w:rPr>
</w:style>
""",
}

DOC_DEFAULTS = f"""
<w:docDefaults>
  <w:rPrDefault>
    <w:rPr>
      <w:rFonts w:ascii="{FONT}" w:eastAsia="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>
      <w:sz w:val="20"/><w:szCs w:val="20"/>
      <w:lang w:val="en-US" w:eastAsia="en-US" w:bidi="ar-SA"/>
    </w:rPr>
  </w:rPrDefault>
  <w:pPrDefault>
    <w:pPr><w:spacing w:after="80" w:line="240" w:lineRule="auto"/></w:pPr>
  </w:pPrDefault>
</w:docDefaults>
"""

SECT_PR = """
<w:sectPr>
  <w:pgSz w:w="11906" w:h="16838"/>
  <w:pgMar w:top="720" w:right="800" w:bottom="680" w:left="800"
           w:header="425" w:footer="425" w:gutter="0"/>
</w:sectPr>
"""


def replace_style(xml: str, style_id: str, block: str) -> str:
    pattern = re.compile(
        r'<w:style [^>]*w:styleId="%s".*?</w:style>' % re.escape(style_id),
        re.DOTALL,
    )
    if not pattern.search(xml):
        raise SystemExit(f"style {style_id} not found in reference.docx")
    return pattern.sub(lambda _m: block.strip(), xml, count=1)


def main() -> None:
    base = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        check=True,
        capture_output=True,
    ).stdout

    src = zipfile.ZipFile(io.BytesIO(base))
    styles = src.read("word/styles.xml").decode("utf-8")
    document = src.read("word/document.xml").decode("utf-8")

    styles = re.sub(r"<w:docDefaults>.*?</w:docDefaults>", DOC_DEFAULTS.strip(), styles, flags=re.DOTALL)
    for style_id, block in STYLES.items():
        styles = replace_style(styles, style_id, block)

    if "<w:sectPr" not in document:
        document = document.replace("</w:body>", SECT_PR + "</w:body>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/styles.xml":
                data = styles.encode("utf-8")
            elif item.filename == "word/document.xml":
                data = document.encode("utf-8")
            dst.writestr(item, data)

    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
