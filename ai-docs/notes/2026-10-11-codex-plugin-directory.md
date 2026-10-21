---
title: What the ChatGPT and Codex plugin directory shows the public
kind: note
date: 2026-10-11
verified: 2026-10-11
stale_after: 2027-01-11
tags: [codex, chatgpt, openai, plugin-directory, research, codex_plugins]
summary: "what OpenAI's plugin directory (shared by ChatGPT and Codex) exposes without a login on 2026-10-11: listing pages yes, API no, install counts and ratings no; how codex_plugins reads a listing and why it needs its own TLS context; read before changing codex_snapshot or when a codex run fails"
---

# The ChatGPT and Codex plugin directory, from outside (2026-10-11)

## Summary

OpenAI publishes no install counts, ratings or public API for its plugin directory. What is public is a server-rendered listing page per plugin, `https://chatgpt.com/plugins/<id>`, which shows the name, developer, category and version. That is all repo-traffic can record, so `codex_plugins` records whether each listing is live, its name and its version, one row per run in `codex.csv`.

## What the docs say

- One catalog for both products: "ChatGPT and Codex use the same public plugin catalog" ([learn.chatgpt.com/docs/plugins](https://learn.chatgpt.com/docs/plugins); developers.openai.com/codex/plugins redirects there with a 308). Browsing happens in the Plugins tab of ChatGPT (web: Work mode, then Plugins) or the desktop app, and `/plugins` in the Codex CLI.
- Submission ([developers.openai.com/plugins/deploy/submission](https://developers.openai.com/plugins/deploy/submission)): upload a ZIP at [platform.openai.com/plugins](https://platform.openai.com/plugins), review, then the developer chooses when to publish. The dashboard covers publication status, review progress and MCP tool findings; nothing about installs or usage. The page mentions "listing API responses" but documents no endpoint.
- Codex marketplaces ([developers.openai.com/plugins/build/plugins](https://developers.openai.com/plugins/build/plugins)): `marketplace.json` at `.agents/plugins/` (repo or home) or the legacy `marketplace.json` in a `.claude-plugin/` folder (the plugin repo's, not this one); entries are a Git URL, a `git-subdir` or an npm package; `codex plugin marketplace add owner/repo`. No counts anywhere. A plugin installed from a Git marketplace shows up only as clones in GitHub traffic (which repo-traffic already saves); one installed from an npm source would show in npm downloads.
- The OpenAI help article (help.openai.com/en/articles/20001256) answered 403 to a plain fetch; search snippets say the app directory moved into the plugin directory on 2026-07-09 and that plugins shared inside a workspace are not published to the public directory.

## What chatgpt.com serves without a login (probed 2026-10-11)

- `https://chatgpt.com/plugins` is the directory, server-rendered, 1.2 MB. It links 91 plugins by name (`<a href="/plugins/<id>"><span class="sr-only">Open NAME</span>`), out of 127 ids in the page; category pages (`?category=developer-tools`) and search render nothing server-side. So a name cannot be looked up reliably; repo-traffic takes the listing id or URL.
- `https://chatgpt.com/apps` and the old `/apps/<slug>/<id>` URLs redirect (302) to `/plugins`.
- Listing ids look like `plugin_asdk_app_<32 hex>` (apps with an MCP server, e.g. Spotify), `Plugin_<32 hex>` (e.g. Codex Security) and `plugins~Plugin_<32 hex>` (e.g. Superpowers, a skills plugin by Jesse Vincent, version 6.4.2).
- Every `/plugins/<anything>` answers 200 with the same `<title>` ("ChatGPT Plugins | Browse and add plugins to ChatGPT"), so status and title say nothing. A live listing has `<h1 ...>NAME</h1>` and a `<dt>Developer</dt>` / `<dt>Category</dt>` / `<dt>Version</dt>` list (version can be empty). An unknown id has no `<h1>` and the page's query cache rejects with `new Error("Plugin not found")`. repo-traffic uses those two markers and fails the plugin when neither is there.
- No install counts, users, ratings or reviews anywhere on a listing page.

## Cloudflare and Python

- curl (Schannel) gets 200 every time. Python's urllib got 403 with `cf-mitigated: challenge` every time: its default TLS context (`http.client._create_https_context`) turns on post-handshake auth. A plain `ssl.create_default_context()` with ALPN `http/1.1` passes most of the time; without ALPN it is refused too. Headers (Accept, Connection) made no difference.
- Even then about one request in four is challenged, at random. `http_json` now retries a 403 that carries `cf-mitigated` like a 429 (10, 20, 30, 40 s); a plain 403 is still not retried. In a live run of 4 x 3 listings, one listing failed after all five tries and was reported as a failure; once, before the not-found check, a live listing came back as a 200 without its `<h1>`, which is why a page with neither marker is a failure, not "not listed".
- Only chatgpt.com gets the custom context: passing `context=` to `urlopen` builds a new opener, which would bypass the golden harness's installed opener for npm, NuGet and pypistats.

## What to record when Mark's plugins are listed

The listing id is not known until the plugin is published. Once the portal or the directory shows it, add the id or URL to `codex_plugins`; the history in `codex.csv` then shows the day it went live (or disappeared) and each version change.

Related: see also [the v1 plan](../plans/2026-10-08-modernization-and-v1-release.md) (size budget D11).
