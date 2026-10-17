// guide-check v1 (2026-10-17). One identical copy in every public Godspeed repository that has
// .github/guide-map.json; the copy in MichaelZelbel/godspeed-mission-control is the original, so
// change it there, raise the version and copy it to the others.
//
// Names the pages of the user guide (https://godspeedmissioncontrol.com/guide) that may describe
// something changed here and that nobody has marked as reviewed. .github/guide-map.json says which
// paths each page describes; scripts/guide-map.mjs in the website repository writes it from each
// page's `sources`. A change to a page's paths since `since` (not counting `ignore`) is open until
// that commit, or a later one on the same line of history, has a line in its message reading
//   Guide-Reviewed: <slug>, <slug>              or   Guide-Reviewed: none-needed (<why>)
// The line may stand anywhere in the message, so it survives a squash merge. No AI, no network,
// Node's own modules only: git does the path matching (:(glob) and :(exclude,glob) pathspecs).
//
//   node .github/guide-check.mjs              exit 0: nothing open; 1: pages open; 2: the map is wrong
//   node .github/guide-check.mjs --self-test  proves the rules in a throwaway repository
//   options: --repo <dir> (default: the repository holding this file), --map <file>
import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const VERSION = "guide-check v1";
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
// A line of the message, after any indent, bullet or quote mark a squash or merge adds.
const REVIEWED = /^[ \t>*+-]*Guide-Reviewed:[ \t]*(.*)$/gim;

class MapError extends Error {}

// Inside a git hook GIT_DIR and friends are set and would win over -C, so they are dropped.
const gitEnv = Object.fromEntries(
  Object.entries(process.env).filter(([k]) => !/^GIT_(DIR|WORK_TREE|INDEX_FILE|OBJECT_DIRECTORY|ALTERNATE_OBJECT_DIRECTORIES|COMMON_DIR|PREFIX)$/.test(k)),
);

function gitIn(repo, config = []) {
  const run = (...args) =>
    execFileSync("git", [...config, "-C", repo, ...args], { encoding: "utf8", env: gitEnv, maxBuffer: 256 << 20, stdio: ["ignore", "pipe", "pipe"] }).replace(/\s+$/, "");
  const ok = (...args) => {
    try {
      run(...args);
      return true;
    } catch {
      return false;
    }
  };
  return { run, ok };
}

const pageUrl = (guide, slug) => `${String(guide || "https://godspeedmissioncontrol.com/guide/").replace(/\/?$/, "/")}${slug}`;

/** Every Guide-Reviewed line in since..HEAD: which commit cleared which pages, and what looked wrong. */
function readReviews(git, range, known) {
  const reviews = [];
  const warnings = [];
  for (const record of git.run("log", "--format=%H%x00%B%x01", range).split("\x01")) {
    const [sha, body = ""] = record.replace(/^\s+/, "").split("\x00");
    if (!sha) continue;
    const at = sha.slice(0, 9);
    let all = false;
    const slugs = new Set();
    for (const [, said] of body.matchAll(REVIEWED)) {
      const value = said.trim();
      if (/^none-needed\b/i.test(value)) {
        const why = (/^none-needed\s*\((.*)\)\s*$/i.exec(value)?.[1] ?? "").trim();
        if (!why || /^<.*>$/.test(why)) warnings.push(`commit ${at} says "Guide-Reviewed: ${value}" without a reason in brackets, so it clears nothing; write "none-needed (<the reason>)"`);
        else all = true;
        continue;
      }
      for (const word of value.split(/[\s,]+/).filter(Boolean)) {
        if (SLUG.test(word) && known.has(word)) slugs.add(word);
        else warnings.push(`commit ${at} names "${word}" in Guide-Reviewed, which is not a page in .github/guide-map.json`);
      }
    }
    if (all || slugs.size) reviews.push({ sha, all, slugs });
  }
  return { reviews, warnings };
}

/** The open pages of one repository. Throws MapError when the map itself is wrong. */
function check({ repo, mapFile }) {
  const git = gitIn(repo);
  let map;
  try {
    map = JSON.parse(readFileSync(mapFile, "utf8"));
  } catch (e) {
    throw new MapError(`cannot read ${mapFile}: ${e.message}`);
  }
  const pages = map.pages && typeof map.pages === "object" ? map.pages : {};
  const since = String(map.since ?? "");
  if (!/^[0-9a-f]{7,40}$/i.test(since)) throw new MapError(`"since" in ${mapFile} must be a commit hash`);
  if (!git.ok("cat-file", "-e", `${since}^{commit}`)) {
    return { skipped: `the start commit ${since.slice(0, 9)} is not in this clone (a shallow clone?), so nothing was checked` };
  }
  if (!git.ok("merge-base", "--is-ancestor", since, "HEAD")) {
    throw new MapError(`"since" ${since.slice(0, 9)} in ${mapFile} is not in this branch's history; set it to a commit this branch contains`);
  }
  const range = `${since}..HEAD`;
  const { reviews, warnings } = readReviews(git, range, new Set(Object.keys(pages)));
  const exclude = (Array.isArray(map.ignore) ? map.ignore : []).map((g) => `:(exclude,glob)${g}`);
  const open = [];
  for (const [slug, globs] of Object.entries(pages)) {
    if (!Array.isArray(globs) || !globs.length) continue;
    // The newest change to the page's paths that no review covers: a review covers every commit
    // it contains, so its hash (and since) are left out of the walk.
    const covering = reviews.filter((r) => r.all || r.slugs.has(slug)).map((r) => r.sha);
    const last = git.run("log", "-1", "--topo-order", "--format=%H%x09%s", "HEAD", "--not", since, ...covering, "--", ...globs.map((g) => `:(glob)${g}`), ...exclude);
    if (!last) continue;
    const [sha, subject = ""] = last.split("\t");
    open.push({ slug, url: pageUrl(map.guide, slug), sha, subject });
  }
  // On Michael's machines the website sits beside this repository: a mapped page that is not
  // there any more was renamed or removed.
  const site = resolve(repo, "..", "godspeedmissioncontrol", "content", "guide");
  if (existsSync(site)) {
    for (const slug of Object.keys(pages)) if (!existsSync(join(site, `${slug}.md`))) warnings.push(`the map names "${slug}", but ${join(site, `${slug}.md`)} does not exist (renamed or removed?)`);
  }
  const pushed = git.ok("rev-parse", "--verify", "-q", "HEAD") && git.run("branch", "-r", "--contains", "HEAD") !== "";
  return { since, open, warnings, pushed };
}

function report(result) {
  const { since, open, warnings, pushed } = result;
  for (const w of warnings) console.log(`warning: ${w}`);
  if (!open.length) {
    console.log(`${VERSION}: every guide page mapped here is reviewed for the changes since ${since.slice(0, 9)}.`);
    return 0;
  }
  const slugs = open.map((o) => o.slug).join(", ");
  const n = open.length === 1 ? "1 page of the user guide" : `${open.length} pages of the user guide`;
  const lines = [`${VERSION}: ${n} may describe something that changed here:`, ""];
  for (const o of open) lines.push(`  ${o.slug}  ${o.url}`, `      newest change ${o.sha.slice(0, 9)} ${o.subject}`);
  lines.push(
    "",
    "Read each page and correct it if it no longer matches: its text is content/guide/<slug>.md in the",
    "private website repository MichaelZelbel/godspeedmissioncontrol (on Michael's machines ../godspeedmissioncontrol).",
  );
  const add = pushed
    ? ["Then mark them reviewed. Your newest commit is already pushed, so add an empty commit:", `  git commit --allow-empty -m "Guide pages reviewed" --trailer "Guide-Reviewed: ${slugs}"`]
    : ["Then mark them reviewed. Your newest commit is not pushed yet, so add the line to it:", `  git commit --amend --no-edit --trailer "Guide-Reviewed: ${slugs}"`];
  lines.push(...add, "When nothing a reader sees changed, give the reason instead of the page names:", `  --trailer "Guide-Reviewed: none-needed (<the reason>)"`);
  console.log(lines.join("\n"));
  if (process.env.GITHUB_STEP_SUMMARY) {
    const md = [`### User guide pages to review`, "", ...open.map((o) => `- [${o.slug}](${o.url}): newest change \`${o.sha.slice(0, 9)}\` ${o.subject.replace(/[<>]/g, "")}`), "", "How to clear them: the log of the step above, or AGENTS.md.", ""];
    try {
      appendFileSync(process.env.GITHUB_STEP_SUMMARY, md.join("\n"));
    } catch {}
  }
  return 1;
}

/** Builds a throwaway repository and proves the rules on it. */
function selfTest() {
  const dir = mkdtempSync(join(tmpdir(), "guide-check-"));
  const repo = join(dir, "repo");
  const hooks = join(dir, "no-hooks");
  mkdirSync(repo);
  mkdirSync(hooks);
  const cfg = ["-c", "user.name=guide-check", "-c", "user.email=guide-check", "-c", "commit.gpgsign=false", "-c", `core.hooksPath=${hooks}`, "-c", "core.autocrlf=false", "-c", "init.defaultBranch=main"];
  const g = gitIn(repo, cfg);
  const put = (file, text) => {
    mkdirSync(dirname(join(repo, file)), { recursive: true });
    writeFileSync(join(repo, file), text);
  };
  const commit = (message, files = {}) => {
    for (const [f, t] of Object.entries(files)) put(f, t);
    g.run("add", "-A");
    g.run("commit", "-q", "--allow-empty", "-m", message);
    return g.run("rev-parse", "HEAD");
  };
  const results = [];
  const expect = (name, got, want) => results.push({ name, pass: JSON.stringify(got) === JSON.stringify(want), got, want });
  try {
    g.run("init", "-q");
    const since = commit("Start", { "app/main.js": "1\n", "app/main.test.js": "1\n", "README.md": "# App\n", "docs/notes.md": "1\n", "skill/x/SKILL.md": "1\n" });
    const mapFile = join(repo, ".github", "guide-map.json");
    const writeMap = (start) => put(".github/guide-map.json", JSON.stringify({ guide: "https://example.invalid/guide/", since: start, ignore: ["**/*.test.*", "docs/**", ".github/**"], pages: { alpha: ["app/**"], beta: ["skill/x/**"] } }));
    writeMap(since);
    const run = () => check({ repo, mapFile });
    const open = () => run().open.map((o) => o.slug);

    expect("nothing changed since the start: no page is open", open(), []);
    commit("Tests and wording", { "app/main.test.js": "2\n", "README.md": "# App\n\n", "docs/notes.md": "2\n" });
    expect("a change only to a test, an unmapped README and docs/ opens no page", open(), []);
    const changed = commit("Change the app", { "app/main.js": "2\n" });
    expect("a change to a mapped path opens its page, naming that commit", run().open.map((o) => [o.slug, o.sha]), [["alpha", changed]]);
    commit("Guide pages reviewed\n\nGuide-Reviewed: alpha");
    expect('"Guide-Reviewed: alpha" in a later commit clears it', open(), []);
    commit("More", { "app/main.js": "3\n", "skill/x/run.sh": "1\n" });
    expect("a newer change opens it again, and a skill folder counts as a whole", open(), ["alpha", "beta"]);
    commit("Placeholder\n\nGuide-Reviewed: none-needed (<why>)");
    expect("none-needed without a real reason clears nothing", open(), ["alpha", "beta"]);
    const amended = commit("Change the skill again", { "skill/x/run.sh": "2\n" });
    g.run("commit", "-q", "--amend", "--no-edit", "--trailer", "Guide-Reviewed: beta");
    expect("the amend command it prints clears the page it names", [open(), g.run("rev-parse", "HEAD") !== amended], [["alpha"], true]);
    commit("Squashed\n\n* Rename a variable\n  Guide-Reviewed: none-needed (internal names only)");
    expect("none-needed (reason), even indented in a squash message, clears every page", open(), []);
    commit("Typo\n\nGuide-Reviewed: gamma");
    expect("a page name the map does not know is warned about", run().warnings.some((w) => w.includes('"gamma"')), true);
    writeMap("0123456789abcdef0123456789abcdef01234567");
    expect("a start commit missing from the clone (shallow) checks nothing and passes", Boolean(run().skipped), true);
  } catch (e) {
    results.push({ name: `the self-test itself ran without an error (${e.message.split("\n")[0]})`, pass: false });
  } finally {
    rmSync(dir, { recursive: true, force: true, maxRetries: 3 });
  }
  const failed = results.filter((r) => !r.pass);
  for (const r of results) console.log(`  ${r.pass ? "ok  " : "FAIL"} ${r.name}${r.pass ? "" : `: got ${JSON.stringify(r.got)}, wanted ${JSON.stringify(r.want)}`}`);
  console.log(`${VERSION} self-test: ${results.length - failed.length} of ${results.length} pass.`);
  return failed.length ? 1 : 0;
}

function main(argv) {
  const opt = (name, fallback) => {
    const i = argv.indexOf(name);
    return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
  };
  if (argv.includes("--help") || argv.includes("-h")) {
    console.log("node .github/guide-check.mjs [--self-test] [--repo <dir>] [--map <file>]");
    return 0;
  }
  if (argv.includes("--self-test")) return selfTest();
  const repo = resolve(opt("--repo", resolve(dirname(fileURLToPath(import.meta.url)), "..")));
  const mapFile = resolve(opt("--map", join(repo, ".github", "guide-map.json")));
  let result;
  try {
    result = check({ repo, mapFile });
  } catch (e) {
    console.error(`${VERSION}: ${e instanceof MapError ? e.message : e.stderr?.toString().trim() || e.message}`);
    return 2;
  }
  if (result.skipped) {
    console.log(`${VERSION}: ${result.skipped}.`);
    return 0;
  }
  return report(result);
}

process.exitCode = main(process.argv.slice(2));
