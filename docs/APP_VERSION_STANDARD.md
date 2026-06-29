# App Version and Release Log Standard

## Purpose

Active projects should have one clear version source of truth and one clear place to record release history. Version metadata must be factual, reproducible, and never guessed.

If a project needs local variation, do not edit a centrally managed `*_STANDARD.md` copy in that project. Create or update the matching project notes file instead:

```text
APP_VERSION_PROJECT_NOTES.md
```

Read order:

```text
1. APP_VERSION_STANDARD.md
2. APP_VERSION_PROJECT_NOTES.md
```

## Version Source of Truth

Each app should have one editable source of truth for the running version.

Preferred Python app pattern:

```python
APP_VERSION = "2026.06.14"

VERSION_LOG = [
    {
        "version": APP_VERSION,
        "date": "2026-06-29 14:30 BST",
        "summary": "Short factual summary of the completed change.",
    },
]
```

Accepted source files:

- `version.py`
- `app/version.py`
- package module `version.py`, for example `taws_log/version.py`
- a clearly documented equivalent for non-Python projects

Project-specific names such as `SITE_VERSION` may remain where they are already established, provided the project documents the convention.

For packaging metadata, avoid a second hard-coded competing version. Prefer dynamic wiring from the app version source where practical.

For containerised apps:

```text
app version = release version = fixed container tag
```

The fixed tag is required for rollback. A `latest` tag may also be published, but must not be the only tag.

## Version Format

Default app version format:

```text
YYYY.MM.RR
```

Where:

- `YYYY` is the year.
- `MM` is the month.
- `RR` is the release or revision number within that month.

The revision number resets at the start of each month.

Examples:

```text
2026.06.01
2026.06.14
2026.07.01
```

Use `vYYYY.MM.RR` only where the project already exposes a visible `v` prefix or for Git tags. Keep the stored app version consistent inside each project.

Reusable packages may use SemVer, for example `0.1.0`, when package-manager compatibility matters more than app-footer release numbering.

Home Assistant integrations may need alignment between `manifest.json`, package metadata, release notes, and Git tags. Follow the integration's established release convention and keep those public version surfaces consistent.

## Release Log Location

Each app should keep concise release history close to the version source.

Preferred Python app pattern:

- `APP_VERSION` stores the current app version.
- `VERSION_LOG` stores recent release entries.
- The app footer or version modal reads from the same source.

Project-level detail should go in the existing project log, if one exists:

- `PROJECT_LOG.md`
- `project_log.md`
- `project_update.md`
- `project_notes.md`
- `CHANGELOG.md`

Do not invent a new log file for a repo that already has an established log unless the user asks for a migration.

## Release Log Entry Format

Use one concise entry per version:

```python
{
    "version": APP_VERSION,
    "date": "2026-06-29 14:30 BST",
    "summary": "Short factual summary of the completed change.",
}
```

Rules:

- Keep entries newest-first.
- Add the new entry above existing entries.
- Preserve all previous entries.
- Do not overwrite, delete, or rewrite the previous top entry when creating a new version.
- Keep the summary factual and operator-readable.
- Avoid long file-by-file implementation detail in the visible version modal.
- New or touched release entries should use full local timestamp format: `YYYY-MM-DD HH:MM ZZZ`.
- Old date-only entries do not need rewriting just for consistency.
- Do not churn historical logs unless correcting a known error.

## Timestamp Source Rule

Never guess, infer, fabricate, round, backfill from memory, or invent version-log timestamps.

For a new version-log entry, get the timestamp from the local shell:

```bash
date '+%Y-%m-%d %H:%M %Z'
```

Copy that exact output into the version log.

If documenting an already-created commit, get the timestamp from Git:

```bash
git show -s --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <commit>
```

Copy that exact output into the version log.

If neither command can be run, stop and leave the timestamp unset rather than inventing one.

## Timezone Rule

Version-log display timestamps should use the local project/operator timezone with the timezone abbreviation included.

For local `/srv` projects, use the local shell output from:

```bash
date '+%Y-%m-%d %H:%M %Z'
```

This produces DST-aware `GMT` or `BST` on a correctly configured UK host.

Application data may still be stored internally as UTC. This rule is about release/version-log entries intended for operators.

## Chronological Ordering

Version-log entries must be newest-first.

When adding a version:

1. Read the current version source first.
2. Increment from the actual current version.
3. Insert one new entry at the top.
4. Leave previous entries below it unchanged.
5. Check that the top entry version matches the current app version.

Do not sort by string at render time if it can hide a wrongly ordered source file. The source file itself should be correct and readable.

## Version Bump Rules

Runtime, app, and deployable changes normally require a version bump.

Documentation, process, and tooling changes require a version bump where the repo convention says they do. Follow the local README, project notes, release process, or existing version-log pattern.

Read-only audits, validation-only checks, and investigation-only work do not require a version bump.

Additional rules:

- Use one bump for a coherent batch of related changes completed in one pass.
- Do not bump when the user explicitly says not to change the version.
- For deploy-versioned projects, bump when deploying, even if the source change was already committed earlier.
- For public packages or integrations, bump the public package/integration version when runtime behavior, public API, Home Assistant manifest behavior, packaging, or release artifacts change.

## Commit Message Convention

Preferred release commit messages:

```text
v2026.06.14 short factual summary
```

or:

```text
Bump to 2026.06.14 - short factual summary
```

Rules:

- Include the version when the commit contains a version bump.
- Use imperative or factual wording consistently.
- Never commit placeholder messages such as `{commit_message}`.
- Avoid vague messages such as `Minor` for release commits.
- Standards-only sync commits may use the established pattern `standards sync YYYY-MM-DD`.

## Public vs Internal Changelog Guidance

Use the visible app version modal for concise operator awareness.

Use internal project logs for operational detail, deployment notes, validation evidence, and known risks.

Use public `CHANGELOG.md` for public repos, packages, and integrations. Public changelogs should exclude local secrets, private paths, internal operational details, and unfinished planning notes.

Where a project has both internal and public logs, keep them intentionally different:

- Public changelog: user-facing changes, compatibility, migration notes.
- Internal log: deployment commands, local validation, environment-specific notes, follow-up risks.

## Pre-Commit Sanity Checks

Before committing a versioned change, check:

- The current version source was read before editing.
- The new version increments from the actual current version.
- The top `VERSION_LOG` entry version matches the current app version.
- The timestamp came from `date '+%Y-%m-%d %H:%M %Z'` or the documented `git show` command.
- Existing version-log entries were preserved.
- Any container tag, `.env`, compose file, package metadata, manifest, or README version reference is intentionally aligned or intentionally unchanged.
- The project log or changelog was updated when the repo convention requires it.
- `git diff --check` passes, unless the repo has known pre-existing whitespace issues that are explicitly reported.

Where practical, projects should add a lightweight test or script to detect version drift.

## Codex-Specific Instructions

Codex must follow these rules for version work:

- Start by reading the actual version source in the repo.
- Do not rely on memory, previous chat context, or inferred release numbers for the current version.
- Run `date '+%Y-%m-%d %H:%M %Z'` immediately before creating a new version-log timestamp.
- Use `git show -s --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <commit>` when documenting an already-created commit.
- Never invent, future-date, backdate, round, fabricate, or guess timestamps.
- Never rewrite old date-only entries just to match the current timestamp format.
- Never overwrite the previous top version-log entry.
- Preserve unrelated local changes.
- Do not edit centrally managed project-local `*_STANDARD.md` files directly.
- If the prompt says read-only, audit-only, investigation-only, docs-only, no version bump, no commit, or no deploy, obey that scope exactly.
