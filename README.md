# BuildSprint Chat + `sitecrawl`

A local chat app that turns a website request into a typed task, runs the bundled crawler as a separate process, and reports the crawler's real output and exit status.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer and npm
- An API key for OpenAI, Anthropic, or Google Gemini is optional. Without one, URL/keyword requests use the labelled regex planner and summaries use the labelled extractive fallback.

## Run locally

From the repository root, create a Python 3.11+ environment, install the backend and CLI, then start the API. On Windows, the Python launcher selects the supported interpreter (the generic `python` command may point at an older installation):

```bash
# Windows PowerShell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

On macOS/Linux, replace `py -3.13` with `python3.11` (or newer) and use `.venv/bin/python` for the install and Uvicorn commands.

In another terminal, configure the frontend and start Vite:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The Vite dev server proxies `/api` to FastAPI on `http://127.0.0.1:8000`.

For a single-process build, run `npm run build` in `frontend`, then start FastAPI from the repository root. FastAPI serves `frontend/dist` when present.

## LLM setup

Copy `.env.example` to `.env` and set `LLM_PROVIDER` to `openai`, `anthropic`, or `gemini` with the matching key. Models can be overridden with `LLM_MODEL`. The planner only returns `TaskSpec`; it cannot construct or execute commands. The summary request has no tools and its cited URLs are checked against the crawl result. If provider configuration or a call is unavailable, the UI and result identify the regex/extractive fallback.

## CLI

```bash
sitecrawl --url https://quotes.toscrape.com --out result.json
```

`sitecrawl` is a purpose-built CLI so its argument list, limits, progress events, result schema, and exit codes are controlled and independently inspectable. It checks HTTP(S) URLs and resolved addresses, respects `robots.txt`, crawls only the starting host (treating `www.` as equivalent), and writes an atomic checkpoint after every page. Stdout is NDJSON progress; stderr is for human-readable logs. Exit codes: `0` complete, `10` partial, `2` invalid arguments, `3` blocked by policy/robots, `4` unreachable, `5` no HTML/content, `1` internal error.

## Security and known limits

- Subprocess calls use `create_subprocess_exec` with a fixed registry-built argv list, scrubbed environment, per-job temporary directory, output caps, process-group timeout and cancellation.
- Network checks reject non-HTTP(S), private, loopback, link-local, multicast, reserved and unspecified addresses. Every redirect and requested crawl URL is checked. DNS is checked before connection but not pinned to that connection, so DNS rebinding is not fully closed.
- Requests are limited to 25 pages (default 10), depth 3 (default 2), 10 seconds per request, 90 seconds per job (default 60), 2 MB per response, HTML only, and 300 ms delay (configurable by the CLI).
- JavaScript rendering, cross-domain crawling, login, persistent job history, and production multi-user storage are out of scope. Jobs are held in memory.

## Tests

```bash
# use .venv\Scripts\python on Windows, or .venv/bin/python on macOS/Linux
python -m pip install -e '.[dev]'
python -m pytest
```

The tests cover URL/network policy, result status rules, and result schema validation. A live demo can use `quotes.toscrape.com` or `books.toscrape.com`; check the target site's robots rules before crawling.

## AI and external services

The optional planner/summarizer calls use the provider configured by `LLM_PROVIDER`. With provider mode enabled, the application sends the user's request to the planner, and sends extracted page text (labelled as untrusted input) to the summary model. No API key is passed to the crawler process. OpenAI Codex assisted with the application scaffold and implementation; runtime AI calls are optional and use only the provider explicitly configured in `.env`.
