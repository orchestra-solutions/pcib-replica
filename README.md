# pcib-replica

Emergency static copy of the public pcibooking.net marketing site, rebuilt from Wayback Machine snapshots.

- `site/` is the deployed output (GitHub Pages, via `.github/workflows/pages.yml`).
- `build/build.py` regenerates it from raw `id_` snapshots: `python3 build/build.py <dir with raw/ and pages.tsv>`.

Content is sanitised to plain HTML inside shared chrome (`build/template.html`, `site/assets/site.css`).
Forms, sign-up, sandbox and card-capture demo pages are not replicated; they redirect or point to email.
Developer docs stay on Mintlify at developers.pcibooking.net.
