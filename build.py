#!/usr/bin/env python3
"""Build Sergio Ruocco's CV for several audiences, plus the static website.

Usage:
    python3 build.py                 # all profiles + site
    python3 build.py --all           # same
    python3 build.py --profile academic industry
    python3 build.py --site
    python3 build.py --list

Content lives in data/*.yml. Audience choices live in profiles/*.yml.
Outputs go to output/ and the web-ready copies to docs/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PROFILE_DIR = ROOT / "profiles"
TEMPLATE_DIR = ROOT / "templates"
OUT_DIR = ROOT / "output"
DOCS_DIR = ROOT / "docs"
FILES_DIR = DOCS_DIR / "files"

TYPE_ORDER = {"journal": 0, "conference": 1, "thesis": 2}
TYPE_LABEL = {
    "journal": "Journal articles",
    "conference": "Conference papers",
    "thesis": "Thesis",
}
SITE_TAGLINE_PROFILE = "industry"  # whose tagline the website header uses
# Inputs whose uncommitted edits mark a build as "+modified" in the stamp.
SOURCE_PATHS = ["build.py", "data", "profiles", "templates", "assets"]


def build_stamp() -> dict:
    """Build date and the git revision of the CV sources it was built from."""
    today = dt.date.today()
    rev = ""
    try:
        rev = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--", *SOURCE_PATHS],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if rev and dirty:
            rev += "+modified"
    except (OSError, subprocess.CalledProcessError):
        pass
    long_date = f"{today.day} {today.strftime('%B %Y')}"
    text = f"Updated {long_date}" + (f" · git {rev}" if rev else "")
    return {"date": today.isoformat(), "long_date": long_date, "rev": rev, "text": text}


STAMP = build_stamp()


def photo_path(profile: dict, data: dict) -> Path | None:
    """The round photo, if the profile shows one and the file exists."""
    photo = data["profile"].get("photo")
    if not photo or not profile.get("options", {}).get("photo"):
        return None
    path = ROOT / photo
    return path if path.exists() else None


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

def read_yaml(path: Path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_data() -> dict:
    data = {}
    for path in sorted(DATA_DIR.glob("*.yml")):
        data[path.stem] = read_yaml(path)
    return data


def load_profiles(names: list[str] | None) -> list[dict]:
    profiles = []
    for path in sorted(PROFILE_DIR.glob("*.yml")):
        profile = read_yaml(path)
        if names and profile["name"] not in names:
            continue
        profiles.append(profile)
    missing = set(names or []) - {p["name"] for p in profiles}
    if missing:
        raise SystemExit(f"unknown profile(s): {', '.join(sorted(missing))}")
    return profiles


# --------------------------------------------------------------------------- #
# Small formatting helpers
# --------------------------------------------------------------------------- #

def publication_location(pub: dict) -> str:
    volume = pub.get("volume")
    issue = pub.get("issue")
    pages = pub.get("pages")
    if volume and issue:
        loc = f"{volume}({issue})"
    elif volume:
        loc = str(volume)
    else:
        loc = ""
    if pages:
        loc = f"{loc}:{pages}" if loc else str(pages)
    return loc


def citation_count(pub: dict, source: str):
    if source == "none":
        return None
    count = (pub.get("citations") or {}).get(source)
    # A zero count adds noise without adding information.
    return count if count else None


def pub_links(pub: dict) -> list[str]:
    links = []
    doi = (pub.get("doi") or "").strip()
    if doi:
        links.append(f"[DOI](https://doi.org/{doi})")
    elif (pub.get("url") or "").strip():
        links.append(f"[paper]({pub['url'].strip()})")
    for item in pub.get("press") or []:
        links.append(f"[{md_em(item['label'])}]({item['url']})")
    return links


def sorted_publications(pubs: list[dict]) -> list[dict]:
    return sorted(
        pubs,
        key=lambda p: (TYPE_ORDER.get(p.get("type"), 9), -int(p.get("year", 0)), p.get("id", "")),
    )


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value)


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def apply_citation_overrides(data: dict) -> None:
    """Merge data/citations.yml (generated by tools/update_citations.py)."""
    overrides = data.get("citations") or {}
    by_doi = overrides.get("by_doi") or {}
    by_title = overrides.get("by_title") or {}
    for pub in data.get("publications", []):
        count = by_doi.get(normalize_doi(pub.get("doi")))
        if count is None:
            count = by_title.get(normalize_title(pub.get("title")))
        if count is not None:
            pub.setdefault("citations", {})["openalex"] = int(count)


def md_em(value: str) -> str:
    """Escape asterisks before wrapping text in Markdown emphasis.

    Organisation names such as "A*STAR" otherwise close the emphasis early.
    """
    return value.replace("*", r"\*")


def tex_escape(value: str) -> str:
    mapping = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(mapping.get(ch, ch) for ch in value)


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

def header_markdown(profile: dict, data: dict) -> str:
    p = data["profile"]
    primary = next((e for e in p["emails"] if e.get("primary")), p["emails"][0])
    secondary = [e for e in p["emails"] if e is not primary]

    line1 = []
    if p.get("address"):
        line1.append(f"{p['address']['line1']}, {p['address']['line2']}")
    if p.get("phone"):
        line1.append(p["phone"])
    if p.get("nationality"):
        line1.append(f"Nationality: {p['nationality']}")
    line2 = [f"[{primary['label']}](mailto:{primary['address']})"]
    line2 += [f"[{e['label']}](mailto:{e['address']})" for e in secondary]
    line2 += [f"[{link['label']}]({link['url']})" for link in p.get("links") or []]
    if p.get("website"):
        line2.append(f"[Website]({p['website']})")

    photo = photo_path(profile, data)
    lines = [f"![{p['short_name']}]({photo}){{width=110px}}", ""] if photo else []
    lines += [
        f"# {p['name']}",
        "",
        f"**{profile['tagline']}**  ",
        p["affiliation"],
        "",
        " · ".join(line1) + "  ",
    ]
    if line2:
        lines.append(" · ".join(line2))
    lines.append("")
    return "\n".join(lines)


def header_latex(profile: dict, data: dict) -> str:
    p = data["profile"]
    primary = next((e for e in p["emails"] if e.get("primary")), p["emails"][0])
    secondary = [e for e in p["emails"] if e is not primary]

    line1 = []
    if p.get("address"):
        line1.append(tex_escape(f"{p['address']['line1']}, {p['address']['line2']}"))
    if p.get("phone"):
        line1.append(tex_escape(p["phone"]))
    if p.get("nationality"):
        line1.append(tex_escape(f"Nationality: {p['nationality']}"))
    line2 = [
        rf"\href{{mailto:{primary['address']}}}{{{tex_escape(primary['label'])}}}"
    ]
    line2 += [
        rf"\href{{mailto:{e['address']}}}{{{tex_escape(e['label'])}}}" for e in secondary
    ]
    line2 += [
        rf"\href{{{link['url']}}}{{{tex_escape(link['label'])}}}"
        for link in p.get("links") or []
    ]
    if p.get("website"):
        line2.append(rf"\href{{{p['website']}}}{{Website}}")

    photo = photo_path(profile, data)
    photo_box = (
        [
            r"\noindent\makebox[0pt][l]{\raisebox{-\height}[0pt][0pt]{"
            rf"\includegraphics[height=2.45cm]{{{photo}}}}}}}%",
        ]
        if photo
        else []
    )
    return "\n".join(
        photo_box
        + [
            r"\begin{center}",
            rf"{{\fontsize{{24}}{{28}}\selectfont\bfseries\color{{accent}} {tex_escape(p['name'])}}}\\[2pt]",
            rf"{{\fontsize{{11}}{{13}}\selectfont {tex_escape(profile['tagline'])}}}\\[1pt]",
            rf"{{\fontsize{{10}}{{12}}\selectfont {tex_escape(p['affiliation'])}}}\\[6pt]",
            r"{\small " + r" \quad\textperiodcentered\quad ".join(line1) + r"}\\[1pt]",
            r"{\small " + r" \quad\textperiodcentered\quad ".join(line2) + "}",
            r"\end{center}",
            r"\vspace{-1pt}",
            "",
        ]
    )


# --------------------------------------------------------------------------- #
# Section renderers
# --------------------------------------------------------------------------- #

def bio_text(data: dict, key: str) -> str:
    """A bio from bios.yml with {years} filled in from profile.career_start."""
    bio = (data["bios"].get(key) or data["bios"]["short"]).strip()
    start = data["profile"].get("career_start")
    if start:
        bio = bio.replace("{years}", str(dt.date.today().year - int(start)))
    return bio


def render_summary(profile: dict, data: dict) -> str:
    heading = profile.get("summary_heading", "Profile")
    return f"## {heading}\n\n{bio_text(data, profile['bio'])}\n"


def render_research_interests(profile: dict, data: dict) -> str:
    items = "\n".join(f"- {item}" for item in data["research_interests"])
    return f"## Research interests\n\n{items}\n"


def render_education(profile: dict, data: dict) -> str:
    chunks = ["## Education"]
    for edu in data["education"]:
        line = f"**{edu['year']} — {edu['degree']}**  "
        inst = edu["institution"]
        if edu.get("field"):
            inst += f" — {edu['field']}"
        if edu.get("grade"):
            inst += f" — {edu['grade']}"
        line += f"\n*{inst}*"
        if edu.get("thesis"):
            line += f"\n\nThesis: *{edu['thesis']}*."
        if edu.get("note"):
            line += f" {edu['note']}"
        chunks.append(line)
    return "\n\n".join(chunks) + "\n"


def render_experience(profile: dict, data: dict) -> str:
    chunks = ["## Experience"]
    show_highlights = profile.get("options", {}).get("experience_highlights", True)
    for job in data["experience"]:
        if profile["name"] not in job.get("tags", [profile["name"]]):
            continue
        block = [
            r"\needspace{4\baselineskip}",
            f"**{job['role']}** — {job['org']}  ",
            f"*{job['period']} · {job['location']}*",
        ]
        if job.get("summary"):
            block.append(job["summary"].strip())
        if show_highlights and job.get("highlights"):
            block.append("\n".join(f"- {h}" for h in job["highlights"]))
        chunks.append("\n\n".join(block))
    return "\n\n".join(chunks) + "\n"


def render_skills(profile: dict, data: dict) -> str:
    chunks = ["## Technical skills"]
    for group in data["competencies"]["groups"]:
        chunks.append(f"**{group['name']}.** " + "; ".join(group["items"]) + ".")
    return "\n\n".join(chunks) + "\n"


def render_capabilities(profile: dict, data: dict) -> str:
    chunks = [
        "## Capabilities",
        "Engagements range from architecture reviews and feasibility studies to "
        "hands-on porting, driver development and debugging.",
    ]
    for group in data["competencies"]["groups"]:
        chunks.append(f"**{group['name']}.** " + "; ".join(group["items"]) + ".")
    return "\n\n".join(chunks) + "\n"


def render_projects(profile: dict, data: dict) -> str:
    mode = profile.get("options", {}).get("projects", "featured")
    if mode == "none":
        return ""
    projects = [
        p for p in data["projects"] if profile["name"] in p.get("tags", [profile["name"]])
    ]
    if mode == "featured":
        projects = [p for p in projects if p.get("featured")]
    chunks = ["## Selected projects"]
    for project in projects:
        block = [
            r"\needspace{4\baselineskip}",
            f"**{project['title']}**  ",
            f"*{md_em(project['period'])} · {md_em(project['context'])}*",
            project["description"].strip(),
        ]
        if project.get("impact"):
            block.append(f"**Impact:** {project['impact'].strip()}")
        chunks.append("\n\n".join(block))
    return "\n\n".join(chunks) + "\n"


def format_pub_line(pub: dict, source: str) -> str:
    details = publication_location(pub)
    line = f"1. {pub['authors']}, “{pub['title']},” *{pub['venue']}*"
    if pub.get("location"):
        line += f", {pub['location']}"
    if details:
        line += f", {details}"
    line += "."
    links = pub_links(pub)
    if links:
        line += " " + " · ".join(links)
    count = citation_count(pub, source)
    if count is not None:
        line += f" · {count} citation{'s' if count != 1 else ''}"
    return line


def render_publications(profile: dict, data: dict) -> str:
    opts = profile.get("options", {})
    mode = opts.get("publications", "none")
    if mode == "none":
        return ""
    source = opts.get("citation_source", "none")
    pubs = data["publications"]
    if mode == "selected":
        pubs = [p for p in pubs if p.get("featured")]
        pubs = sorted(pubs, key=lambda p: (-int(p.get("year", 0)), TYPE_ORDER.get(p.get("type"), 9), p.get("id", "")))
    else:
        pubs = sorted_publications(pubs)

    chunks = ["## Publications"]
    counts = {"journal": 0, "conference": 0, "thesis": 0}
    for pub in data["publications"]:
        counts[pub.get("type")] = counts.get(pub.get("type"), 0) + 1
    count_bits = []
    if counts["journal"]:
        count_bits.append(f"{counts['journal']} journal articles")
    if counts["conference"]:
        count_bits.append(f"{counts['conference']} conference papers")
    if counts["thesis"]:
        count_bits.append("1 PhD thesis")
    if mode == "full":
        chunks.append("*" + ", ".join(count_bits[:-1]) + " and " + count_bits[-1] + ".*")
    else:
        chunks.append("*Selected publications.*")

    if mode == "selected":
        chunks.extend(format_pub_line(pub, source) for pub in pubs)
    else:
        current_type = None
        for pub in pubs:
            if pub["type"] != current_type:
                current_type = pub["type"]
                chunks.append(f"### {TYPE_LABEL.get(current_type, current_type.title())}")
            chunks.append(format_pub_line(pub, source))

    if source != "none":
        label = citation_source_label(data, source)
        scholar = next(
            (l["url"] for l in data["profile"].get("links", []) if l["label"] == "Google Scholar"),
            "",
        )
        note = f"*Citation counts: {label}."
        if scholar:
            note += f" Live counts and h-index: [Google Scholar]({scholar})."
        note += "*"
        chunks.append(note)
    return "\n\n".join(chunks) + "\n"


def month_year(value) -> str:
    """'2026-11-09' or '2025-04' -> 'November 2026' / 'April 2025'."""
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})", text)
    if not match:
        return text
    return dt.date(int(match[1]), int(match[2]), 1).strftime("%B %Y")


def citation_source_label(data: dict, source: str) -> str:
    meta = data.get("citations") or {}
    if source == "openalex":
        when = month_year(meta.get("retrieved"))
        return f"OpenAlex ({when})" if when else "OpenAlex"
    when = month_year(meta.get("scholar_retrieved"))
    return f"Google Scholar ({when})" if when else "Google Scholar"


def render_patents(profile: dict, data: dict) -> str:
    mode = profile.get("options", {}).get("patents", "none")
    if mode == "none":
        return ""
    chunks = ["## Patents and technology disclosures"]
    if mode == "all":
        for patent in data["patents"].get("patents", []):
            line = r"\needspace{3\baselineskip}" + "\n\n"
            line += f"**{patent['id']}** — “{patent['title']}.”"
            line += f" Filed {patent['filed']}; granted {patent['granted']}."
            if patent.get("publication"):
                line += f" [{patent['publication']}]({patent['url']})"
            if patent.get("note"):
                line += f" · {patent['note']}"
            chunks.append(line)
        chunks.append("### Technology disclosures")
    if data["patents"].get("disclosures_note"):
        chunks.append("*" + md_em(data["patents"]["disclosures_note"].strip()) + "*")
    for disclosure in data["patents"].get("disclosures", []):
        line = f"**{disclosure['id']}** — {disclosure['title']}."
        line += f" Filed {disclosure['filed']}."
        if disclosure.get("status"):
            line += f" {disclosure['status']}."
        if disclosure.get("impact"):
            line += f" {disclosure['impact']}."
        if disclosure.get("creators"):
            line += f" Creators: {disclosure['creators']}."
        chunks.append(line)
    return "\n\n".join(chunks) + "\n"


def render_talks(profile: dict, data: dict) -> str:
    chunks = ["## Invited talks"]
    for talk in data["talks"]:
        line = f"- **{talk['date']}** — “{talk['title']},” *{talk['event']}*"
        if talk.get("location"):
            line += f", {talk['location']}"
        line += "."
        if talk.get("url"):
            line += f" [event]({talk['url']})"
        chunks.append(line)
    return "\n".join(chunks) + "\n"


def render_teaching(profile: dict, data: dict) -> str:
    mode = profile.get("options", {}).get("teaching", "full")
    if mode == "none":
        return ""
    chunks = ["## Teaching"]
    for course in data["teaching"]:
        line = f"- **{course['period']}** — *{course['course']}* ({course['level'].lower()}), {course['institution']}."
        if mode == "full" and course.get("editions"):
            line += f" {course['editions']}."
        chunks.append(line)
    return "\n".join(chunks) + "\n"


def render_grants(profile: dict, data: dict) -> str:
    chunks = ["## Grants and funded projects"]
    for grant in data["grants"]:
        meta = [grant["period"]]
        if grant.get("amount"):
            meta.append(grant["amount"])
        if grant.get("role"):
            meta.append(grant["role"])
        block = [
            f"**{grant['name']}**  ",
            "*" + " · ".join(meta) + "*",
        ]
        if grant.get("partners"):
            block.append(f"Partners: {grant['partners']}.")
        block.append(grant["description"].strip())
        if grant.get("url"):
            block.append(f"[Project page]({grant['url']})")
        chunks.append("\n\n".join(block))
    return "\n\n".join(chunks) + "\n"


def render_supervision(profile: dict, data: dict) -> str:
    chunks = ["## Student supervision"]
    for item in data["supervision"]:
        chunks.append(f"- **{item['level']}** — {item['detail']}.")
    return "\n".join(chunks) + "\n"


def render_service(profile: dict, data: dict) -> str:
    chunks = ["## Professional service"]
    for item in data["service"]:
        line = f"- **{item['period']}** — {item['role']}, *{item['venue']}*"
        if item.get("location"):
            line += f", {item['location']}"
        line += "."
        if item.get("url"):
            line += f" [website]({item['url']})"
        chunks.append(line)
    return "\n".join(chunks) + "\n"


RENDERERS = {
    "summary": render_summary,
    "research_interests": render_research_interests,
    "education": render_education,
    "experience": render_experience,
    "skills": render_skills,
    "capabilities": render_capabilities,
    "projects": render_projects,
    "publications": render_publications,
    "patents": render_patents,
    "talks": render_talks,
    "teaching": render_teaching,
    "grants": render_grants,
    "supervision": render_supervision,
    "service": render_service,
}


def render_body(profile: dict, data: dict) -> str:
    parts = []
    for section in profile["sections"]:
        renderer = RENDERERS.get(section)
        if renderer is None:
            raise SystemExit(f"unknown section '{section}' in profile {profile['name']}")
        parts.append(renderer(profile, data))
    body = "\n".join(part for part in parts if part)
    # Keep a section heading with at least the first few lines of its body.
    # Raw LaTeX is ignored by the DOCX and HTML writers.
    return re.sub(r"(?m)^## ", r"\\needspace{8\\baselineskip}\n\n## ", body)


# --------------------------------------------------------------------------- #
# DOCX polish
# --------------------------------------------------------------------------- #

def fix_docx_keep_together(path: Path, profile: dict, data: dict) -> None:
    """Stop Word/LibreOffice splitting a role or project heading from its body.

    Pandoc has no portable "keep with next" syntax, so the generated DOCX is
    post-processed: the paragraph holding the heading, and the paragraph holding
    its date/context line, get the OOXML ``keepNext`` property.
    """
    import zipfile
    from xml.etree import ElementTree as ET

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    anchors: set[str] = set()
    for job in data["experience"]:
        if profile["name"] in job.get("tags", [profile["name"]]):
            anchors.add(f"{job['role']} — {job['org']}")
    projects = [
        p for p in data["projects"] if profile["name"] in p.get("tags", [profile["name"]])
    ]
    if profile.get("options", {}).get("projects", "featured") == "featured":
        projects = [p for p in projects if p.get("featured")]
    anchors.update(p["title"] for p in projects)
    anchors = {a for a in anchors if a}

    with zipfile.ZipFile(path) as src:
        root = ET.fromstring(src.read("word/document.xml"))
        body = root.find(ns + "body")
        paragraphs = body.findall(ns + "p")

        def paragraph_text(p) -> str:
            return "".join(t.text or "" for t in p.iter(ns + "t")).strip()

        def keep_next(paragraph) -> None:
            props = paragraph.find(ns + "pPr")
            if props is None:
                props = ET.Element(ns + "pPr")
                paragraph.insert(0, props)
            if props.find(ns + "keepNext") is None:
                index = 1 if props.find(ns + "pStyle") is not None else 0
                props.insert(index, ET.Element(ns + "keepNext"))

        for index, paragraph in enumerate(paragraphs):
            if paragraph_text(paragraph) not in anchors:
                continue
            keep_next(paragraph)

        document = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        tmp = path.with_name(path.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                payload = src.read(item.filename)
                if item.filename == "word/document.xml":
                    payload = document
                dst.writestr(item, payload)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write("command failed: " + " ".join(cmd) + "\n")
        sys.stderr.write(result.stderr + "\n")
        raise SystemExit(result.returncode)


def build_profile(profile: dict, data: dict) -> dict:
    OUT_DIR.mkdir(exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)

    name = profile["filename"]
    md_path = OUT_DIR / f"{name}.md"
    docx_path = OUT_DIR / f"{name}.docx"
    pdf_path = OUT_DIR / f"{name}.pdf"
    html_path = OUT_DIR / f"{name}.html"
    header_tex = OUT_DIR / f"{name}.header.tex"

    body = render_body(profile, data)
    # The stamp goes at the end of the DOCX and HTML only; the PDF has it in the footer.
    stamp = html.escape(STAMP["text"])
    footer_md = (
        f'\n\n```{{=html}}\n<p class="stamp">{stamp}</p>\n```\n\n'
        "```{=openxml}\n"
        '<w:p><w:pPr><w:spacing w:before="240"/><w:jc w:val="right"/></w:pPr>'
        f'<w:r><w:rPr><w:i/><w:color w:val="5A6570"/><w:sz w:val="16"/></w:rPr>'
        f'<w:t xml:space="preserve">{stamp}</w:t></w:r></w:p>\n```\n'
    )
    md_path.write_text(
        header_markdown(profile, data) + "\n" + body + footer_md, encoding="utf-8"
    )
    header_tex.write_text(header_latex(profile, data), encoding="utf-8")

    reference = TEMPLATE_DIR / "reference.docx"
    run(
        [
            "pandoc",
            str(md_path),
            "--from=markdown+smart",
            "--to=docx",
            f"--reference-doc={reference}",
            "-o",
            str(docx_path),
        ]
    )
    run(
        [
            "pandoc",
            str(md_path),
            "--from=markdown+smart",
            "--to=html5",
            "--standalone",
            "--embed-resources",
            f"--css={TEMPLATE_DIR / 'cv.css'}",
            f"--metadata=pagetitle={data['profile']['short_name']} — {profile['label']}",
            "-o",
            str(html_path),
        ]
    )
    run(
        [
            "pandoc",
            str(md_path),
            "--from=markdown+smart",
            "--pdf-engine=xelatex",
            f"--template={TEMPLATE_DIR / 'cv.latex'}",
            f"--include-before-body={header_tex}",
            f"--variable=stamp:{tex_escape(STAMP['text'])}",
            "-o",
            str(pdf_path),
        ]
    )

    fix_docx_keep_together(docx_path, profile, data)
    header_tex.unlink(missing_ok=True)
    for path in (pdf_path, docx_path, html_path):
        shutil.copy2(path, FILES_DIR / path.name)

    print(f"  {profile['label']}: {pdf_path.name}, {docx_path.name}, {html_path.name}")
    return {
        "name": profile["name"],
        "label": profile["label"],
        "pdf": f"files/{pdf_path.name}",
        "docx": f"files/{docx_path.name}",
        "html": f"files/{html_path.name}",
    }


# --------------------------------------------------------------------------- #
# Website
# --------------------------------------------------------------------------- #

def pub_citation_label(pub: dict) -> str:
    count = citation_count(pub, "openalex")
    if count is None:
        return ""
    return f"{count} citation{'s' if count != 1 else ''}"


def pub_link_label(pub: dict) -> str:
    return "DOI" if (pub.get("doi") or "").strip() else "Paper"


def build_site(profiles: list[dict], data: dict, outputs: list[dict]) -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    shutil.copy2(TEMPLATE_DIR / "site.css", DOCS_DIR / "style.css")
    if data["profile"].get("photo"):
        shutil.copy2(ROOT / "assets" / "photo.jpg", DOCS_DIR / "photo.jpg")

    p = data["profile"]
    scholar = next((l["url"] for l in p.get("links", []) if l["label"] == "Google Scholar"), "")
    pubs = sorted_publications(data["publications"])
    selected = sorted(
        [pub for pub in pubs if pub.get("featured")],
        key=lambda pub: (-int(pub.get("year", 0)), TYPE_ORDER.get(pub.get("type"), 9), pub.get("id", "")),
    )
    today = STAMP["date"]

    tagline_profile = next(
        (pr for pr in profiles if pr["name"] == SITE_TAGLINE_PROFILE), profiles[0]
    )
    index_html = env.get_template("site_index.html.j2").render(
        profile=p,
        tagline=tagline_profile["tagline"],
        bio=bio_text(data, "academic"),
        interests=data["research_interests"],
        experience=data["experience"][:4],
        selected=selected,
        scholar=scholar,
        today=today,
        rev=STAMP["rev"],
        photo="photo.jpg" if p.get("photo") else "",
        downloads=outputs,
        citation_label=pub_citation_label,
        pub_link_label=pub_link_label,
        pub_url=lambda pub: (
            f"https://doi.org/{pub['doi']}" if pub.get("doi") else (pub.get("url") or "")
        ),
    )
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")

    pubs_html = env.get_template("site_publications.html.j2").render(
        profile=p,
        tagline="Publications",
        pub_groups=[
            (TYPE_LABEL[t], [pub for pub in pubs if pub.get("type") == t])
            for t in ("journal", "conference", "thesis")
            if any(pub.get("type") == t for pub in pubs)
        ],
        scholar=scholar,
        today=today,
        rev=STAMP["rev"],
        citation_label=pub_citation_label,
        pub_link_label=pub_link_label,
        pub_url=lambda pub: (
            f"https://doi.org/{pub['doi']}" if pub.get("doi") else (pub.get("url") or "")
        ),
    )
    (DOCS_DIR / "publications.html").write_text(pubs_html, encoding="utf-8")
    print(f"  site: {DOCS_DIR / 'index.html'}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Build CV variants and the website.")
    parser.add_argument("--profile", nargs="+", help="profile name(s), e.g. academic industry")
    parser.add_argument("--site", action="store_true", help="build only the website")
    parser.add_argument("--all", action="store_true", help="build all profiles and the site")
    parser.add_argument("--list", action="store_true", help="list profiles and exit")
    args = parser.parse_args()

    available = load_profiles(None)
    if args.list:
        for profile in available:
            print(f"{profile['name']}: {profile['label']}")
        return

    data = load_data()
    apply_citation_overrides(data)

    if args.site:
        outputs = build_site_placeholder(data)
        build_site(available, data, outputs)
        return

    names = None if args.all or not args.profile else args.profile
    profiles = available if names is None else load_profiles(names)

    print("Building CVs...")
    outputs = []
    for profile in profiles:
        outputs.append(build_profile(profile, data))

    if args.all or not args.profile:
        build_site(available, data, outputs)


def build_site_placeholder(data: dict) -> list[dict]:
    """Download links for a site-only build, pointing at whatever exists."""
    outputs = []
    for profile in load_profiles(None):
        name = profile["filename"]
        if (FILES_DIR / f"{name}.pdf").exists():
            outputs.append(
                {
                    "name": profile["name"],
                    "label": profile["label"],
                    "pdf": f"files/{name}.pdf",
                    "docx": f"files/{name}.docx",
                    "html": f"files/{name}.html",
                }
            )
    return outputs


if __name__ == "__main__":
    main()
