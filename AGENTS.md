# Working in this repository

## The user guide

Readers learn what this repository does from the user guide at https://godspeedmissioncontrol.com/guide. Its pages are Markdown files `content/guide/<slug>.md` in the private website repository MichaelZelbel/godspeedmissioncontrol (on Michael's machines `../godspeedmissioncontrol`), and `.github/guide-map.json` says which paths here each page describes.
Before you push, run `node .github/guide-check.mjs`. For each page it names: read it, correct it in the website repository if it no longer matches, then mark it with the command the check prints (`Guide-Reviewed: <slug>, <slug>` in your newest commit), or with `Guide-Reviewed: none-needed (<why>)` when nothing a reader sees changed.
The map is written from each page's `sources` by `scripts/guide-map.mjs` in the website repository, never by hand: when you add something readers will see, add its paths to the `sources` of the page that should describe it, run that script with `--write`, and commit the new map here.
