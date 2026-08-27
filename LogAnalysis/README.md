# JVM Diagnostic Agents

Multi-agent toolkit that reads **GC logs**, **thread dumps**, and **heap dumps**, then produces a correlated JVM performance report (CLI + static dashboard).

A coordinator classifies files, runs specialist LangChain agents in parallel, optionally retrieves notes from a Dify knowledge base, and writes `dashboard/data.json`.

## Architecture

```
User query / file flags
        │
        ▼
 SmartRootCoordinator
        │
        ├── GC agent      → GCeasy API
        ├── Thread agent  → TDA JAR (optional) + Python parser
        └── Memory agent  → Eclipse MAT ParseHeapDump.sh
        │
        ▼
  Synthesis LLM  (+ optional Dify)
        │
        ▼
  dashboard/data.json + agent_outputs/*.md
```

## Requirements

- Python 3.10+
- An LLM key: **Azure OpenAI** (`LLM_PROVIDER=azure`, default) or **OpenAI** (`LLM_PROVIDER=openai`)
- Optional:
  - [GCeasy](https://gceasy.io) API key (GC logs)
  - [Eclipse Memory Analyzer](https://eclipse.dev/mat/) `ParseHeapDump.sh` (heap dumps)
  - TDA 2.6 JAR with `--mcp` (richer thread-dump analysis; Python fallback is always used)
  - Java runtime for MAT / TDA
  - Dify dataset API (optional RAG)

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # then edit .env
```

Never commit `.env`. If this project previously contained hardcoded keys, **rotate those keys** before you push.

## Configure

See `.env.example`. Minimum for a dry run of the coordinator:

- `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT`  
  **or** `LLM_PROVIDER=openai` + `OPENAI_API_KEY`

Heap dumps also need `MAT_PARSE_SCRIPT` pointing at MAT’s `ParseHeapDump.sh`.  
GC logs need `GCEASY_API_KEY`.  
Thread dumps work without TDA; set `TDA_JAR_PATH` if you have the JAR.

Put production JVM flags in `JVM_STARTUP_PARAMS` or `JVM_PARAMS_FILE` so the GC agent can compare flags with the log.

## Usage

```bash
# Natural language (paths must exist)
python -m jvm_diag "Analyze ./logs/app-gc.log and ./dumps/app.tdump"

# Explicit files
python -m jvm_diag --gc ./app-gc.log --thread ./app.tdump --heap ./app.hprof

# JSON on stdout
python -m jvm_diag --gc ./app-gc.log --json
```

Open the dashboard (needs a local HTTP server because `fetch` is blocked for `file://`):

```bash
python -m http.server 8080 --directory dashboard
# http://127.0.0.1:8080
```

## File classification

| Type   | Filename heuristics                                      |
|--------|-----------------------------------------------------------|
| memory | `.hprof`, `.heapdump`                                     |
| gc     | `*gc*.log`, `.gclog`                                      |
| thread | `.tdump`, `.jstack`, `.threads`, or name contains `thread` / `jstack` |

Generic `.txt` / `.log` files are **not** treated as thread dumps.

## Project layout

```
jvm_diag/          # package
  agents/          # GC / thread / heap LangChain agents
  tools/           # GCeasy, MAT, thread parser, Dify
  coordinator.py   # planning + parallel run + synthesis
  cli.py
dashboard/         # static report UI
tests/
```

## Tests

```bash
pytest
```

## Security

- Secrets live in environment variables only.
- Do not commit heap dumps, thread dumps, or generated reports (they often contain customer data).
- `.gitignore` excludes `.env`, `*.hprof`, dumps, and `jvm_dshboard/` (legacy local outputs).

## License

MIT
