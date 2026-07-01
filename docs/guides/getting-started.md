# Getting Started: From Zero to Hello Agent

This guide takes you all the way from an empty machine to your first "hello
agent" moment with yoker, using Ollama's **free tier**. No paid accounts, no
API keys required for the basic path.

If you already have Python and `uv` installed, jump to
[Install yoker](#install-yoker).

```{contents}
:local:
:depth: 1
```

---

## What you will need

- About 10 minutes.
- A machine running macOS, Windows, or Linux.
- An internet connection.
- An Ollama account (free — created during setup).

You do **not** need a paid model provider. yoker runs on Ollama's free tier,
which is enough to explore agentic workflows end to end.

---

## Step 1 — Set up Python and uv

yoker is a Python application. You need Python 3.10 or newer, and we recommend
`uv` to manage the install (it is fast and keeps things tidy).

### macOS

The easiest route is via [Homebrew](https://brew.sh):

```bash
# Install Homebrew (if you don't have it already)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python and uv
brew install python@3.12 uv
```

If you prefer per-project Python versions, use
[pyenv](https://github.com/pyenv/pyenv):

```bash
brew install pyenv
pyenv install 3.12
pyenv global 3.12
pip install uv
```

Verify both are available:

```bash
python3 --version   # 3.10 or higher
uv --version
```

### Windows

A little more work, but still quick.

1. **Install Python** — download the official installer from
   <https://www.python.org/downloads/windows/>. Run it and, importantly,
   tick **"Add python.exe to PATH"** at the top of the installer before
   clicking **Install**.
2. **Install uv** — open a new terminal (so PATH changes take effect) and run:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Or, with `pip`:

   ```bash
   pip install uv
   ```

Verify both are available:

```bash
python --version   # 3.10 or higher
uv --version
```

### Linux

Use your distribution's package manager, then install `uv`:

```bash
# Python (Debian/Ubuntu example)
sudo apt update && sudo apt install -y python3 python3-pip

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify both are available:

```bash
python3 --version   # 3.10 or higher
uv --version
```

---

## Step 2 — Install yoker

The simplest path, using `uv` (no virtual environment to manage):

```bash
uv tool install yoker
```

This installs the `yoker` command on your PATH. You can now run `yoker` from
anywhere.

Prefer to try it once without a permanent install? Use `uvx`:

```bash
uvx yoker
```

If you prefer plain `pip`, that works too:

```bash
pip install yoker
```

Whichever route you take, verify the install:

```bash
yoker --version
```

---

## Step 3 — Run yoker for the first time

The first time you run `yoker`, it detects that no configuration exists yet and
launches the **bootstrap wizard** — a short, guided setup that writes your
`~/.yoker.toml` config file for you.

```bash
yoker
```

The wizard walks you through a few steps:

1. **Opening** — yoker explains itself and notes that no config was found. It
   offers a guided setup, manual setup, a link to the docs, or abort.
2. **Backend intro** — yoker introduces Ollama as the backend and points out
   the free tier. There is nothing to choose here.
3. **Account check** — yoker asks whether you already have an Ollama account.
   If not, it points you to the docs and waits while you create one.
4. **Connection method** — choose how yoker reaches Ollama:
   - **The Ollama app running locally** (recommended — no API key needed), or
   - **An Ollama API key** (use cloud-hosted models without running the app).
5. **Model selection** — pick a model from the curated list, accept the
   default, or enter a model name by hand.
6. **Confirmation** — yoker writes `~/.yoker.toml` (with safe file permissions)
   and you are ready to go.

For the detailed companion to step 3 (creating an Ollama account, installing
the local app/proxy, and optionally generating an API key), see
{doc}`Getting Started with Ollama <getting-started-with-ollama>`. For a plain
explanation of what yoker is and why the wizard exists, see
{doc}`Getting Started with Yoker <getting-started-with-yoker>`.

> **Free tier reminder:** The default model offered by the wizard works on
> Ollama's free tier. You do not need to add payment details or generate a
> paid key to complete this guide.

Here's an actual recording of the wizard, with a setup for Google Gemini:

```console
% uvx yoker
Step 1 of 6: Welcome
Welcome to yoker — a provider-neutral AI backend for running agentic workflows.
yoker connects to model providers and gives your tools, skills,
and agents a single place to run.

No yoker configuration was found at ~/.yoker.toml — that's why this wizard is showing.
Docs: https://yoker.readthedocs.io/en/latest/guides/getting-started-with-yoker.html

Would you like to configure yoker now?
  1) Guided setup (recommended) — I'll ask a few questions and write the config for you.
  2) Manual setup — I'll print a config skeleton and a docs link, and you author ~/.yoker.toml yourself.
  3) Visit the documentation first — I'll open the docs in your browser, then come back here.

Ctrl+c interrupts the setup at any time, without writing anything.

Choose [1/2/3] (Enter = 1 guided):

Step 2 of 6: Select Provider
Choose your preferred LLM provider:

  1) Ollama — Cloud inference with free tier (no local download required)
  2) OpenAI — GPT models via OpenAI API
  3) Anthropic — Claude models via Anthropic API
  4) Google Gemini — Gemini models via Google AI API (free tier available, works with your Google account)

Ctrl+c interrupts the setup at any time, without writing anything.

Choose [1-4] (Enter = 1 Ollama): 4
Do you have a personal Google account? [y/n] (Enter = N): y

Step 4 of 6: API Key
Do you have a Google Gemini API key? [y/n] (Enter = N):
  https://yoker.readthedocs.io/en/latest/guides/getting-started-with-gemini.html#api-key
The guide walks through creating a Google Gemini API key.

Open this in your browser? [y/n] (Enter = Y):
Press Enter when you're ready to continue...
Paste your Google Gemini API key: *****************************************************

Step 5 of 6: Model Selection
Pick a model, or accept the default:
  1) Gemini 2.5 Flash-Lite (default) — fastest, most budget-friendly model
  2) Gemini 2.5 Flash — best price-performance ratio, excellent for reasoning
  3) Gemini 2.5 Pro — most advanced for complex tasks and deep reasoning
  4) Gemini 3.5 Flash — most intelligent for agentic and coding tasks
  5) Gemini 3.1 Pro Preview — advanced reasoning, preview release
  6) Enter a model id by hand

Choose [1-6] (Enter = default):
No model entered; using default.


Step 6 of 6: Configuration Created
Configuration written to /Users/xtof/.yoker.toml (chmod 600).
Provider: Google Gemini
Model: gemini-2.5-flash-lite
yoker is continuing into the normal session now.
```

## Step 4 — Your first "hello agent" interaction

Once the wizard finishes, yoker drops you straight into an interactive chat
session. You should see a prompt like:

```text
Yoker vX.Y.Z - Using model: gemini-3-flash-preview:cloud
Type your message and press Enter. Press Ctrl+D (or Ctrl+Z on Windows) to quit.

>
```

Type a simple prompt and press **Enter**:

```text
> Say hello in one sentence.
```

The model responds, streamed in real time. That is your "it works!" moment —
yoker is configured, connected to Ollama's free tier, and answering prompts.

A few more things to try:

- Ask it to read a file:

  ```text
  > Read the first 3 lines of README.md and summarize them.
  ```

- List the available tools:

  ```text
  > /tools
  ```

- See the thinking trace (the model's reasoning shown before the answer):

  ```text
  > /think on
  > Why is the sky blue?
  ```

When you are done, quit with **Ctrl+D** (or **Ctrl+Z** on Windows).

---

## Step 5 — What just happened?

A quick recap so the next steps make sense:

- You installed Python, `uv`, and yoker.
- yoker detected no config and ran the **bootstrap wizard**, which wrote
  `~/.yoker.toml` for you.
- That single config file now backs every yoker-based app you run — you only
  go through the wizard once.
- You confirmed the setup with a real prompt to the model, on Ollama's free
  tier, at no cost.

---

## Next steps

- {doc}`Getting Started with Yoker <getting-started-with-yoker>` — a plain
  explanation of what yoker is and why a shared config is useful.
- {doc}`Getting Started with Ollama <getting-started-with-ollama>` — the
  detailed Ollama account, app, and API-key companion to the wizard.
- {doc}`Quick Start <../quickstart>` — interactive and batch modes, tools,
  slash commands, and library usage.
- {doc}`Installation <../installation>` — full installation reference,
  including a from-source development setup.
