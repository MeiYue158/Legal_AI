# Citation Verifier — MCP Server

Exposes this project's citation-checking machinery to any MCP client
(Claude Desktop, Claude Code, another agent).

## Why this capability, and not retrieval

These tools take the document text as an argument, so they work on a
contract, a paper, or an opinion this project has never seen — nothing here
touches `corpus_cases` or the FAISS index. `app/rag/verify.py` imports
neither `faiss` nor `psycopg2`, which is what makes that true at the
architecture level rather than just in principle.

Retrieval is deliberately *not* exposed. It only means something against
our 136-case index, and the product calls it directly as a Python
function — putting it behind a protocol would add hops without adding
reach.

## Tools

| Tool | Question it answers | Nature of the answer |
|---|---|---|
| `verify_quote` | Does this quote actually appear in the document? | **Evidence.** Exact or whitespace-tolerant match, with character offsets. |
| `locate_evidence` | Which sentence best supports this claim? | **A lead.** Embedding similarity — ranked guesses, never proof. |
| `check_citations` | Audit several quotes against one document | Per-quote verdicts, plus the closest sentence for each miss. |

The distinction between the first two is the point of the server. An exact
match is evidence; a similarity match is a lead. Every response says which
it is, because conflating them reintroduces precisely the failure this
exists to catch.

### Reading similarity scores

`all-MiniLM-L6-v2` scores even unrelated English sentence pairs around
0.1–0.35, so a score near 0.3 is noise, not weak support. Measured against
a sample document, claims the text genuinely covered scored 0.67–0.80 while
unrelated claims scored 0.12–0.35; `WEAK_EVIDENCE_THRESHOLD = 0.5` sits in
that gap. `locate_evidence` prefixes its note with `WEAK` below it.

## Setup

The server needs this repo's venv — `sentence-transformers` for sentence
embedding and `nltk` punkt for sentence splitting. Both are already
installed and cached locally; no download or training is involved.

Add to `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "citation-verifier": {
      "command": "/Users/ivy/Documents/Summer_2025/legal_ai/venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/Users/ivy/Documents/Summer_2025/legal_ai",
      "env": { "TOKENIZERS_PARALLELISM": "false" }
    }
  }
}
```

Absolute paths are required — the client does not inherit your shell's cwd.
`TOKENIZERS_PARALLELISM=false` suppresses a HuggingFace fork warning that
would otherwise go to stderr on every call.

Run standalone (for debugging):

```bash
venv/bin/python -m app.mcp.server
```

It speaks JSON-RPC on stdin/stdout, so it will appear to hang — that is a
server waiting for a client, not a failure.

## Notes

- First call loads the embedding model (~90MB, a few seconds). The process
  stays alive, so subsequent calls are fast. `verify_quote` and
  `check_citations` need no model at all when every quote matches — the
  matcher is pure string and regex.
- `MAX_DOCUMENT_CHARS = 400_000`. Oversized input raises `ToolError`, which
  the client can read and act on, rather than an opaque crash.
- Tests: `venv/bin/python -m pytest tests/test_verify.py`
