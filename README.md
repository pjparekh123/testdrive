# 🔮 Chaos Oracle MCP

A mystical — but actually useful — MCP server for getting unstuck. When you don't know what to do next, ask the Oracle.

Six tools for lateral thinking, creative unblocking, and perspective shifts. Zero external dependencies. Works with Claude, Cursor, or any MCP-compatible client.

---

## Tools

| Tool | What it does |
|------|-------------|
| `consult_oracle` | Ask any question. Get an ancient prophecy + a grounded practical interpretation. |
| `oblique_strategy` | Draw 1–5 Brian Eno-style cards for breaking creative deadlock. |
| `flip_perspective` | Invert your problem — what if the bug IS the feature? |
| `cosmic_coincidence` | Find unexpected connections between two unrelated concepts. |
| `fortune_for_devs` | Your developer fortune for the current moment. Changes every few minutes. |
| `random_constraint` | A creative constraint to force lateral thinking. Gentle, moderate, or chaotic. |

---

## Quickstart

### Run directly with npx (no install)

```bash
npx chaos-oracle-mcp
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "chaos-oracle": {
      "command": "npx",
      "args": ["chaos-oracle-mcp"]
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add chaos-oracle -- npx chaos-oracle-mcp
```

### Cursor / other MCP clients

Point your client at: `npx chaos-oracle-mcp` via stdio transport.

---

## Example interactions

**"I'm stuck on a design decision"**
> Use `consult_oracle` with your question, or `oblique_strategy` with your context.

**"This bug is driving me insane"**
> Use `flip_perspective` — maybe it's not a bug.

**"I need fresh inspiration"**
> Use `cosmic_coincidence` with two unrelated things from your world.

**"What should I focus on today?"**
> Use `fortune_for_devs` with your current mood.

**"I keep solving this the same wrong way"**
> Use `random_constraint` with your task and `intensity: chaotic`.

---

## Philosophy

The Oracle doesn't give you answers. It gives you better questions.

All tools are seeded by the current time, so repeated calls yield different results — but a given call at a given moment is deterministic (useful for sharing a result with a teammate).

---

## Local development

```bash
git clone https://github.com/pjparekh123/testdrive
cd testdrive
npm install
npm run dev   # runs via tsx (no build step)
npm run build # compile to dist/
```

## License

MIT
