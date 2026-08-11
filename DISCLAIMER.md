# Disclaimer

## What Yoker Is

Yoker is a **Python-first agent harness framework** — a library and CLI tool that lets you
embed LLM-powered agents into your Python applications. It provides the
infrastructure: tool calling, guardrails, multi-provider backend integration,
context management, and session orchestration. You bring the LLM; Yoker
handles the plumbing.

Yoker is **open source** software released under the MIT License.

## What Yoker Is Not

- **Yoker is not an AI model.** It does not produce responses itself. It
  forwards your prompts to a third-party LLM provider (Ollama, OpenAI,
  Anthropic, Google Gemini, or any LiteLLM-supported provider) and returns the
  model's output.

- **Yoker is not a hosted service.** It runs on your machine, in your process,
  with your configuration. There is no Yoker server, no Yoker cloud, no Yoker
  account.

- **Yoker is not a replacement for human judgment.** An LLM agent can produce
  incorrect, biased, or harmful output. Yoker does not verify the correctness,
  safety, or appropriateness of what the model generates. You are responsible
  for reviewing all output before acting on it.

## What Yoker Does

Yoker gives an LLM agent **access to your local machine and network**. This is
the core value proposition — and the core risk. Specifically, a Yoker agent can:

### Filesystem Access

- **Read** files on your local filesystem (subject to extension allowlists and
  size limits).
- **Write** new files to your filesystem.
- **Update** existing files (replace, insert, delete content).
- **List** directory contents.
- **Search** file contents with regex or search filenames with glob patterns.
- **Create** directories.
- **Check** whether files and folders exist.

### Code Execution

- **Run Makefile targets** via the `make` tool. Makefile recipes can execute
  arbitrary shell commands. The `make` tool enforces a per-target env var
  allowlist and a framework hard-denylist, but recipes inherit the yoker
  process environment — including any API keys or tokens present in it.

### Git Operations

- **Run Git commands** via the `git` tool: `status`, `log`, `diff`, `branch`,
  `show`, `add`, `commit`, `push`, `pull`, `tag`, `rm`, `checkout`. Write
  operations (commit, push) require interactive approval by default and are
  blocked in batch mode.

### GitHub Access

- **Query GitHub** via the `gh` CLI: view issues, PRs, workflow runs, reviews,
  and comments. The GitHub tool is read-only.

### Network Access

- **Search the web** via the `websearch` tool. This sends queries to a web
  search backend (e.g., Ollama's built-in web search or a LiteLLM-supported
  provider).
- **Fetch web content** via the `webfetch` tool. This retrieves content from
  URLs you or the agent specify. SSRF protection blocks private IPs and cloud
  metadata endpoints by default.

### Sub-Agent Spawning

- **Spawn sub-agents** via the `agent` tool. A sub-agent inherits guardrails
  from its parent and gets an isolated context. Recursion depth is limited.

### Third-Party Plugins

- **Load plugins** from external Python packages. Plugins can add arbitrary
  tools, skills, and agent definitions. A plugin's code runs in your process
  with your privileges.

### External Agentic Packages

- **Run agentic packages** from GitHub URLs, zip files, local folders, or
  Python modules via `yoker run`. These packages can contain arbitrary Python
  code, agent definitions, and configuration overrides.

## What Yoker Does Not Do

- **Yoker does not sandbox tool execution.** Tools run in the Yoker process
  with the same OS permissions as the user running Yoker. There is no
  container, no chroot, no restricted user.
- **Yoker does not filter LLM output.** The model's response is passed through
  to your application as-is. Yoker does not check for harmful content,
  hallucinations, or incorrect code.
- **Yoker does not guarantee tool call safety.** Guardrails reduce risk but
  are not a security boundary. A determined agent can bypass Yoker's tools by
  generating Python code that a Makefile recipe then executes, or by
  convincing you to approve a dangerous action.
- **Yoker does not protect your API keys from the LLM.** API keys in your
  environment variables are visible to Makefile recipes. API keys in your
  config file are used for backend authentication but are not hidden from
  tools the agent calls.
- **Yoker does not provide audit logging by default.** Session events are
  persisted for context resumption, but there is no tamper-proof audit trail
  of what the agent did.

## Guardrails and Their Limitations

Yoker includes several guardrail layers. These are **safety nets, not security
boundaries**. They protect against powerful mistakes — they do not protect
against a malicious agent or a compromised LLM provider.

### Path Guardrail

- Blocks path traversal (`../` sequences).
- Enforces file size limits.
- Restricts file extensions for read and write operations.
- Enforces a configurable `protected_files` denylist (Makefile, pyproject.toml,
  yoker.toml, .git/config, .github/workflows/*.yml, uv.lock, ...) — this is a
  **SOFT** guardrail: in interactive mode it prompts for approval with a diff;
  in batch mode it blocks.

**Limitation**: An agent that can run `make` can execute `make` recipes that
write to any file, bypassing the path guardrail entirely.

### Environment Variable Guardrail

- Enforces a per-target env var allowlist for the `make` tool (deny-by-default).
- Maintains a framework hard-denylist (e.g., `YOKER_TRUST_SOURCE`,
  `PYTHONPATH`, `GIT_DIR`, `BASH_ENV`, `MAKEFLAGS`, ...) that cannot be
  overridden by configuration.

**Limitation**: The allowlist and denylist only govern agent-supplied env vars.
Makefile recipes inherit the Yoker process environment, so any secret present
in Yoker's env (API keys, tokens) is readable by recipes.

### Web Guardrail

- SSRF protection: blocks private IP ranges, localhost, and cloud metadata
  endpoints (169.254.169.254).
- Configurable domain allowlist and blocklist.
- Rate limiting and concurrent request limits.
- Sensitive pattern detection (API keys, passwords in URLs).

**Limitation**: DNS rebinding attacks can bypass SSRF checks. The domain
allowlist is optional and empty by default (all domains allowed).

### Trust Gate

- `yoker run` refuses to execute untrusted sources by default.
- Trust is recorded per-source in your `yoker.toml`.
- The trust decision uses your config, not the source's manifest overrides.

**Limitation**: Once you trust a source, its code runs with full privileges.
The trust gate is a one-time gate, not continuous monitoring.

### Plugin Trust

- Plugins are disabled by default.
- First-time plugin loading shows a confirmation dialog with the plugin's
  components.
- Trusted plugins are recorded in `[plugins.trusted]` in your config.

**Limitation**: A trusted plugin's code runs in your process. Review plugin
code before trusting it.

## Your Responsibilities

1. **Review tool calls.** In interactive mode, Yoker shows you what the agent
   wants to do before it does it. Pay attention, especially to `write`,
   `update`, `git commit`, `git push`, and `make` calls.

2. **Review plugin code.** Before trusting a plugin, inspect its source. A
   plugin can execute arbitrary Python code in your process.

3. **Review agentic packages.** Use `yoker inspect <source>` to preview a
   package before running it. Only trust sources you have reviewed.

4. **Secure your API keys.** Use environment variable interpolation
   (`${OPENAI_API_KEY}`) rather than hardcoding keys in config files. Ensure
   config files have `chmod 600` permissions (Yoker does this automatically via
   `yoker init` and the bootstrap wizard). Consider using a secrets manager
   for production deployments.

5. **Understand model limitations.** LLMs hallucinate, produce biased output,
   and can be manipulated via prompt injection. Never trust agent output
   blindly — especially for security-sensitive operations.

6. **Run with least privilege.** Don't run Yoker as root. Don't run Yoker in a
   directory containing sensitive files you don't want the agent to access.
   Consider using `yoker container` to run agentic packages in an isolated
   container.

7. **Keep your environment clean.** Don't expose secrets in environment
   variables when running untrusted agents. Makefile recipes inherit your
   full environment.

## No Warranty

Yoker is provided "as is", without warranty of any kind, express or implied,
including but not limited to the warranties of merchantability, fitness for a
particular purpose, and non-infringement. In no event shall the authors or
copyright holders be liable for any claim, damages, or other liability,
whether in an action of contract, tort, or otherwise, arising from, out of,
or in connection with the software or the use or other dealings in the
software.

See [LICENSE](LICENSE) for the full MIT License text.