# Security policy

## Reporting a problem

Open an issue or a pull request and I'll take a look. A pull request with the fix is the quickest route.

You can also report privately: open the repository's **Security** tab and choose **Report a vulnerability**.

This is a one-person project with no bug bounty and no response deadline. I'll reply when I can and say what I plan to do. Good-faith testing on your own copy is welcome.

## Supported versions

Only the latest release (on PyPI and GitHub Releases) gets fixes.

## Scope

The script runs on your machine with your `gh` login and writes traffic data, including data for private repos, to a local folder. In scope: anything that makes it send data anywhere except the GitHub, npm, NuGet and pypistats.org APIs, write outside its data folder, or put private data in a tracked file. Releases are built by `.github/workflows/release.yml`, attested, and uploaded to PyPI through Trusted Publishing after a manual approval; `gh attestation verify FILE --repo m4bwav/repo-traffic` checks a downloaded file. Out of scope: bugs in the GitHub CLI or the registries' APIs; report those to their makers.
