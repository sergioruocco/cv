# Sergio Ruocco — modular CV

One content source, three audience-specific CVs, and a static website. Everything
is plain text (YAML + Markdown templates), so it versions cleanly in git and can
be rebuilt at any time.

## Quick start

```bash
python3 build.py --all
```

That writes:

| File | Purpose |
|---|---|
| `output/Sergio_Ruocco_CV_academic.pdf` | Full academic/research CV (5 pages) |
| `output/Sergio_Ruocco_CV_industry.pdf` | Industry R&D CV (3 pages) |
| `output/Sergio_Ruocco_CV_consulting.pdf` | Consulting/contractor CV (3 pages) |
| matching `.docx` and `.html` files | Editable and web versions |
| `docs/index.html` | Personal website |
| `docs/publications.html` | Full publication list |
| `docs/files/*` | PDF/DOCX/HTML copies linked from the site |

`python3 build.py --list` shows the available profiles. `make` is a shortcut for
the same build.

## How it is organised

```
data/                  content, one file per topic
  profile.yml          name, address, phone, emails, links
  bios.yml             short / academic / industry / consulting summaries
  education.yml
  experience.yml
  competencies.yml     competency areas and technical-skill groups
  research_interests.yml
  projects.yml         selected projects, with `featured` flags
  publications.yml     17 publications + PhD thesis
  patents.yml          patents and A*STAR technology disclosures
  talks.yml
  teaching.yml
  grants.yml
  supervision.yml
  service.yml
  citations.yml        generated OpenAlex counts (override layer)

profiles/              audience choices
  academic.yml
  industry.yml
  consulting.yml

templates/
  cv.latex             XeLaTeX template for PDFs
  cv.css               styling for the standalone HTML CVs
  reference.docx       Word styles used by pandoc
  site_*.html.j2       website templates
  site.css

build.py               assembles and renders everything
tools/
  make_reference_docx.py   regenerates templates/reference.docx
  update_citations.py      refreshes OpenAlex counts into data/citations.yml
docs/                  generated website (GitHub Pages root)
output/                generated CVs (git-ignored)
```

## Editing content

- **Facts and wording** live in `data/*.yml`. Edit the YAML directly; no code
  changes are needed.
- **Audience choices** live in `profiles/*.yml`. A profile lists the sections to
  include, in order, plus options:

  ```yaml
  options:
    experience_highlights: true
    projects: featured          # all | featured | none
    publications: full          # full | selected | none
    citation_source: openalex   # scholar | openalex | none
    patents: all                # all | disclosures | none
    teaching: full              # full | summary | none
  ```

- **A publication** uses `featured: true` to appear in short profiles. Add
  `citations: {scholar: 12, openalex: 39}` to show counts; either source can be
  selected per profile.
- **A project** uses `featured: true` to appear in the shorter profiles.
- **Experience entries and projects** carry a `tags` list. An item is shown only
  in profiles named in that list, so the same data can be rich for one audience
  and concise for another. For example, the pre-2004 roles are tagged
  `[consulting]` because they show breadth to clients but are noise on a senior
  industry CV.
- **Avoid duplicate detail.** The industry and consulting profiles set
  `experience_highlights: false` and put the technical depth in
  `Selected projects`; the academic profile keeps the detailed experience
  timeline and uses projects only as a highlight reel.
- **A new audience**: copy one file in `profiles/`, change `name`, `label`,
  `filename`, `tagline`, `bio`, `sections` and `options`. It is picked up
  automatically. Remember to add the new name to the relevant `tags` lists.

## Refreshing citation counts

```bash
python3 tools/update_citations.py
python3 build.py --all
```

The script queries OpenAlex for author `A5051152014` and writes
`data/citations.yml`. The build merges those counts over the values in
`publications.yml`, so the generated file can be replaced at any time. Counts
shown in the CV are labelled with their source and date; the site links to
Google Scholar for live counts and the h-index.

Google Scholar counts are typed by hand into `publications.yml`. When you
update them, also set `scholar_retrieved: 'YYYY-MM'` in `data/citations.yml`
(the refresh script preserves it) so the CV label shows the right date.

## Rebuilding the Word styles

`templates/reference.docx` controls fonts, sizes, colours, heading rules and
margins in DOCX output. Regenerate it after editing the design:

```bash
python3 tools/make_reference_docx.py
```

The PDF uses `templates/cv.latex`; the site uses `templates/site.css`.

Page breaks are handled for you: the PDF emits `\needspace` before section
headings, roles and projects, and the DOCX is post-processed to add Word's
"keep with next" property to those headings. This stops a role or project title
being stranded at the bottom of a page.

## Website and GitHub Pages

`docs/` is a self-contained static site (no JavaScript, no build step at
runtime). To publish it:

1. Push the repository to GitHub.
2. Open **Settings → Pages**.
3. Choose **Deploy from a branch**, branch `main`, folder `/docs`.
4. Save. The site appears at `https://<user>.github.io/<repo>/`.

The site links to `docs/files/`, which the build populates with the current
PDF/DOCX/HTML files. Rebuild and commit `docs/` whenever the content changes.

## Dependencies

- Python 3.10+ with **PyYAML** and **Jinja2**
- **pandoc** 3.x
- **XeLaTeX** (`texlive-xetex`) with `fontspec`, `titlesec`, `enumitem`,
  `needspace`, `hyperref`, `longtable`, `booktabs`
- **Liberation Sans** (metric-compatible with Arial; keeps PDF text extraction
  and applicant-tracking systems clean)
- LibreOffice is only needed if you want to preview the generated DOCX as PDF

## Content provenance

The new CV starts from `2025_04_02_..._v13.odt` and recovers material that had
been dropped from it:

- **2013 v38 CV**: full publication list, research narrative, teaching history,
  grants and EU/Micron projects, invited talks, conference service.
- **2021–2023 I²R CVs**: inventions, patents and technology disclosures,
  supervision, project and commercialisation details.
- **v11/v12**: the 25-year summary and the NTU-era structure.
- **The current LinkedIn profile** (authoritative for 2025 onward): EMASS Senior
  Software Engineer since 06/2025, NTU Research Fellow 04/2024–05/2025, the
  A*STAR Senior Scientist II / Scientist II split, and the earlier roles. It
  supersedes v13, which still showed the NTU role as current.
- **2013 MNC/ASTAR bios**: the longer institutional narrative.

The publication list was cross-checked against OpenAlex and matches the
"Journal: 5 / Conference: 12" count in v13 exactly (plus the PhD thesis). The
2017 `CV2017 44441 Magno + annexe.pdf` and the Magno CV were excluded as a
colleague's material; the two manager testimonial PDFs are references, not CV
content.

## Open items to confirm

- ORCID and GitHub URLs (placeholders are commented in `data/profile.yml`);
  LinkedIn and Google Scholar are already filled in.
- Publication-list completeness: every work OpenAlex lists for the author is
  in `publications.yml` (checked November 2026). Papers indexed only elsewhere
  (e.g. Google Scholar, DBLP) must be added manually.
- Consulting engagements are subject to case-by-case management approval; the
  consulting CV is retained on that basis.
