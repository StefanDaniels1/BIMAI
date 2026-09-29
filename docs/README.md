# bimai documentation

The source of [docs.bimai.nl](https://docs.bimai.nl): a [Fumadocs](https://fumadocs.dev) site,
exported as static files.

```bash
npm install
npm run dev        # preview on http://localhost:3000
npm run example    # regenerate the example project from packs/project-site/examples/
npm run build      # static site in out/
npm run check      # documentation coverage and link check (after build)
```

- Pages: `content/docs/**/*.mdx`. Order and section titles: `meta.json` in each folder.
- Mermaid code blocks render as diagrams in the bimai colours.
- Mark anything not built yet with `<Status state="planned" />` or `<Status state="design">…</Status>`.
- `content/docs/example-project/` is **generated**; don't edit it by hand.
- Published by `.github/workflows/docs.yml` on every push to `main`.

Documentation is part of done: see [the rules](content/docs/build/documentation.mdx).
