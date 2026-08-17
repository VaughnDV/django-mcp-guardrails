# Release publishing

The package is **not on PyPI yet**. A first upload is coming soon.

This repository is prepared for PyPI Trusted Publishing. A coding agent must
not tag, publish, change package visibility, or upload artifacts unless a
maintainer explicitly asks.

Package metadata `version = "0.1.0"` describes planned work until a GitHub
Release is published. Keep changelog entries under `## [Unreleased]` until an
authorised release PR converts that heading to a dated version.

## Production PyPI

Workflow: [`.github/workflows/release.yml`](../.github/workflows/release.yml)

- Trigger: `release: types: [published]` only
- Build job: no OIDC token; builds once, runs `twine check`, inspects
  contents, clean-installs the wheel, and checks that tag `vX.Y.Z`, metadata,
  installed version, and changelog heading agree
- Publish job: downloads those artifacts, `id-token: write`, GitHub
  environment `pypi`, official `pypa/gh-action-pypi-publish`
- No PyPI tokens and no `skip-existing`

Configure a GitHub Environment named `pypi` with required reviewers, and a
matching Trusted Publisher on https://pypi.org for this repository and
workflow. If environment protection is unavailable, defer publishing rather
than weakening the gate.

## TestPyPI

Workflow: [`.github/workflows/publish-testpypi.yml`](../.github/workflows/publish-testpypi.yml)

- Trigger: `workflow_dispatch` only
- Requires a PEP 440 pre-release in project metadata (for example `0.1.0rc1`)
- GitHub environment `testpypi`

Never publish every commit on `main`.

## Maintainer steps

1. Open a release PR that sets the version, moves `## [Unreleased]` to
   `## [X.Y.Z] - YYYY-MM-DD`, and leaves an empty Unreleased section.
2. Merge after CI is green.
3. Create the GitHub Release/tag `vX.Y.Z`. That event runs production publish.
4. Confirm the environment approval and the PyPI listing.

Ordinary CI on push and pull request does not publish.
