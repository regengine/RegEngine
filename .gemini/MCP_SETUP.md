# MCP Setup Guide for RegEngine

## What's Configured

Your `.gemini/settings.json` has 4 MCP servers ready to go:

### 1. 🐙 GitHub MCP
**What it does:** Create/search issues, manage PRs, trigger Actions, read repo data — all from chat.

**Status:** ✅ Ready (using your `gh` CLI token)

**Example uses:**
- "Create an issue for the FSMA 204 export bug"
- "List open PRs"
- "Show me the latest CI run status"

### 2. 📚 Context7 MCP
**What it does:** Fetches up-to-date documentation for libraries in your stack (Next.js, FastAPI, SQLAlchemy, Pydantic, etc.)

**Status:** ✅ Ready (zero config)

**Example uses:**
- "What's the correct way to use async routes in Next.js 15?"
- "Show me SQLAlchemy 2.0 session patterns"

### 3. 🐳 Docker MCP
**What it does:** List/start/stop containers, view logs, inspect container health directly from chat.

**Status:** ✅ Ready (uses your local Docker socket)

**Example uses:**
- "List all running containers"
- "Show me the admin service logs"
- "Restart the ingestion container"

### 4. 📁 Filesystem MCP
**What it does:** Direct read/write access to your RegEngine project directory.

**Status:** ✅ Ready

---

## Adding Supabase/PostgreSQL MCP (Optional)

To add direct database querying, get your connection string from the Supabase dashboard:

1. Go to https://supabase.com/dashboard → Your Project → Settings → Database
2. Copy the **Connection string** (URI format)
3. Add this to `.gemini/settings.json` inside `mcpServers`:

```json
"postgres": {
  "command": "npx",
  "args": [
    "-y",
    "@modelcontextprotocol/server-postgres",
    "postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres"
  ]
}
```

---

## Activating MCPs

After saving the settings file:

1. **Reload your IDE** — Cmd+Shift+P → "Developer: Reload Window"
2. MCPs will start automatically when Gemini needs them
3. First run may take 10-15 seconds as npm packages download

## Security Notes

- `.gemini/settings.json` is gitignored (contains your GitHub token)
- The GitHub token is from your `gh` CLI session and rotates automatically
- If the token expires, run `gh auth login` to refresh it, then update the token
