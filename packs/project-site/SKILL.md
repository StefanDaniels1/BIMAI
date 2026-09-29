---
name: project-site
description: Build or open the project's documentation site (people, AI teams, agreements, decisions, meetings, this week). Use when someone asks for the project site, wants to show the project to a manager, director or client, or onboards a new colleague.
---

# Project site

The project site is generated **entirely by code** from the project's files
(`scripts/generate_site.py`). You never write its pages yourself and never add content that
isn't in the project files: the site must only ever show what the project team shares.

## What you do

- **"Show me the project site" / "open the site":** run the `site-build` workflow, then open the
  result locally (`bimai site open`).
- **"Share it with the director / the client":** explain that project sites are private by default
  and can only be published to the location the organization configured (`bimai site publish`).
  Never publish to a public host. If no location is configured, say so and offer the local version
  or a zip file.
- **"Something on the site is wrong":** the site mirrors the project files. Find the file the page is
  generated from (e.g. `ownership.yaml` for People, `agreements.yaml` for Agreements) and propose the
  change there; shared files go through the rule owners' approval.
- **"Add a page about X":** only if X lives in the project files. Otherwise suggest adding it to
  `context/` or to the project's links in `project.yaml`.

## Never

- Publish without the person asking for it.
- Include desk content, raw transcripts, raw data exports or anything from a private session.
