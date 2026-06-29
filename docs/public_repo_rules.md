# Public Repository Rules

## Purpose

This document defines the minimum rules for any repository that is public, may become public, or may be copied into a public GitHub repository.

The aim is to keep public repositories useful to users while avoiding unnecessary exposure of internal development history, future plans, implementation strategy, research notes, prompts, logs, or operational detail.

Public repositories should contain the product and the user-facing instructions.

They should not contain the development playbook.

## Core Rule

A public repository must include only what is needed for:

* installation
* configuration
* safe operation
* basic troubleshooting
* licensing
* security guidance
* public release history
* required platform metadata
* source code required to run the project

Everything else should stay private, local, or in a separate non-public archive.

## Applies To

These rules apply to:

* existing public repositories
* repositories intended to become public
* repositories submitted to HACS, GitHub Marketplace, package indexes, or similar public catalogues
* repositories created through Ops Helper / OpsDeck
* copied project templates that may later be pushed to GitHub

These rules do not require private/local-only development repositories to be slimmed in the same way unless they are later made public.

## Files Normally Allowed in Public Repositories

The following are normally acceptable in a public repository:

* `README.md`
* `LICENSE`
* `CHANGELOG.md`
* `RELEASE_NOTES.md`
* `SECURITY.md`
* `CONTRIBUTING.md`, if needed
* issue templates
* pull request templates
* required app/integration metadata
* required package metadata
* source code required to run the project
* minimal configuration examples
* minimal screenshots needed for user understanding
* user-facing documentation
* public-safe test files
* public-safe CI/workflow files

For Home Assistant / HACS projects, this includes required files such as:

* `hacs.json`
* `manifest.json`
* `strings.json`
* translations
* integration source files
* minimal dashboard examples where useful
* HACS/Home Assistant validation workflow files

## Files Normally Not Allowed in Public Repositories

The following should not be included in public repositories unless there is a specific, reviewed reason:

* full internal project logs
* detailed development history
* Codex prompts
* AI assistant prompts or outputs
* internal planning notes
* future roadmap detail
* detailed TODO files
* implementation strategy notes
* architecture debate notes
* risk assessment working notes
* API research notes
* competitor analysis
* HACS/default submission strategy notes
* private operational notes
* local server notes
* deployment notes containing internal paths, hosts, usernames, IP addresses, tokens, or infrastructure details
* screenshots that reveal private systems, internal dashboards, keys, addresses, or future features
* large draft documents
* copied internal standards that are not needed by public users
* private test data
* real logs from production systems
* real financial/account data
* real user/customer data
* backup files
* temporary files
* exported chat history
* old generated reports
* local environment files

## Public Log Standard

Public repositories may contain a slim user-facing log, but must not contain a full internal project log.

A public log should record only:

* released version
* release date
* user-facing changes
* breaking changes
* migration notes
* security notes
* known limitations relevant to users

A public log should not include:

* internal reasoning
* failed attempts
* prompt history
* detailed implementation decisions
* future planned features
* private project strategy
* competitor references
* HACS queue strategy
* development workflow commentary

Preferred public wording:

```markdown
## v2026.06.8

- Added read-only account summary sensors.
- Improved HACS compatibility.
- Updated documentation for safe read-only API token use.
```

Avoid public wording like:

```markdown
## Internal notes

- Next we will add pies, positions and dividends.
- Codex struggled with the config flow.
- We decided not to implement orders yet because of risk.
- HACS backlog strategy discussed.
```

## Roadmap Rule

Public repositories should not expose detailed future roadmap information.

Avoid publishing:

* exact upcoming feature lists
* planned API endpoints
* future dashboard/card plans
* implementation sequencing
* known competitive gaps
* “coming next” lists
* detailed wishlist items

Acceptable public wording:

```markdown
Further read-only account data may be added in future releases.
```

Not acceptable:

```markdown
Next planned features:
- pies
- dividends
- active orders
- tax summaries
- Lovelace card
- multi-account dashboards
```

## README Rules

A public `README.md` should be useful but not excessive.

It should normally include:

* what the project does
* install instructions
* basic configuration
* required permissions
* safe-use notes
* user-facing feature list
* known limitations
* support/issue guidance
* licence reference

It should not include:

* internal development history
* detailed future plans
* prompt-generated planning text
* internal debates
* private infrastructure detail
* excessive implementation notes
* unnecessary screenshots
* strategy commentary

## Security and Token Handling Documentation

If a project asks users for API keys, tokens, passwords, credentials, financial data, personal data, or service account details, the public repo must clearly explain the security boundary.

For API/token projects, document:

* what permissions are required
* whether read-only permissions are sufficient
* whether write/mutation access is used
* what the integration does not do
* how secrets are stored
* whether tokens are excluded from logs/diagnostics
* whether the project makes outbound network calls beyond the expected service

For financial/API integrations, be explicit.

Example:

```markdown
This integration is read-only.

It does not place trades, cancel orders, edit account settings, move funds, deposit, withdraw, or perform mutation actions.

Use an API token restricted to read-only permissions wherever the upstream service allows it.
```

## Entity and Data Exposure Rules

Public documentation should avoid exposing unnecessary detail about internal entity design unless users need it.

For Home Assistant integrations:

* document user-facing entities
* document optional entity groups
* document defaults
* document any high-volume entity behaviour
* document how to disable optional entity groups if supported

Do not publish internal entity design debates, future entity plans, or detailed implementation reasoning unless required by users.

## Examples and Screenshots

Examples and screenshots should be minimal and public-safe.

Allowed:

* simple example configuration
* basic dashboard example
* cropped screenshot showing only the project UI
* fake/demo data

Not allowed:

* real tokens
* real account balances
* real customer/user data
* internal server names
* private IP addresses unless intentionally generic
* private URLs
* admin dashboards
* development dashboards
* future unreleased features
* screenshots that reveal unrelated systems

## Internal Documentation Location

Internal project material should remain outside public repositories.

Examples of internal-only material:

* full project logs
* long-form implementation notes
* Codex/AI prompts and outputs
* detailed TODOs
* future feature plans
* research notes
* architecture decision drafts
* private deployment notes
* competitor notes
* backlog strategy

These may be kept locally, in private repositories, or in a private archive, but must not be committed to public repositories.

## Git History Rule

Removing a sensitive or non-public file from the live working tree is not always enough.

If a public repository has previously contained material that should not remain public, consider whether Git history also needs cleaning.

History rewrite may be appropriate for:

* credentials
* tokens
* private keys
* private infrastructure details
* real personal/financial/customer data
* internal strategy documents
* Codex/prompt logs
* detailed roadmap documents
* private operational notes
* files that should never have been public

History rewrite must be treated as a destructive action.

Before rewriting public Git history or force-pushing, record:

* repository name
* remote URL
* current branch
* files/paths to purge
* proposed command
* whether tags are affected
* whether release tags are affected
* force-push command
* risks
* rollback options
* explicit approval

Do not rewrite public history casually.

## Public Repository Pre-Release Checklist

Before making a repository public, confirm:

* [ ] README is user-facing only.
* [ ] Licence is present.
* [ ] Security notes are present where needed.
* [ ] No internal project logs are present.
* [ ] No Codex/AI prompt history is present.
* [ ] No detailed roadmap is present.
* [ ] No internal TODO list is present.
* [ ] No API research notes are present.
* [ ] No private infrastructure details are present.
* [ ] No real logs or real data are present.
* [ ] No secrets, tokens, keys, or credentials are present.
* [ ] Screenshots contain only safe/demo data.
* [ ] Examples use fake/demo values.
* [ ] Public changelog/release notes are slim and user-facing.
* [ ] `.gitignore` excludes private/internal files.
* [ ] Git history has been reviewed for material that should not remain public.
* [ ] Required metadata and install files remain present.
* [ ] Source code required to run the project remains present.

## New Repository Rule

New repositories created through Ops Helper / OpsDeck should include this document by default.

New public-ready repositories should start with a public-safe documentation layout.

Recommended default public documentation set:

```text
README.md
LICENSE
CHANGELOG.md
SECURITY.md
public_repo_rules.md
```

Project-specific internal notes should not be created in the public repo by default.

If internal notes are needed, create them in a private/local location.

## Existing Repository Cleanup Rule

When applying these rules to an existing public repository:

1. Identify all documentation and support files.
2. Classify each file as keep, slim, or remove.
3. Preserve required user-facing documentation.
4. Remove or slim non-essential internal material.
5. Check whether removed/slimmed material remains in Git history.
6. Plan history rewrite only where justified.
7. Do not force-push without explicit approval.
8. Update `.gitignore` to prevent reintroducing private material.
9. Keep local/private workflows intact.

## Default Position

If unsure whether a document belongs in a public repository, assume it does not.

Public repositories should show users how to use the project.

They should not show outsiders how the project was planned, built, debated, prioritised, or positioned.
