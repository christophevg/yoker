# Model Catalog

Yoker ships with curated model lists for each supported provider. These are the
models offered by the bootstrap wizard when you run `yoker` for the first time,
and they have been tested to work well with Yoker's tool calling features.

The curated lists are defined in `src/yoker/bootstrap/providers.py` and are the
single source of truth for this page. Other models from these providers may
also work but have not been officially tested.

```{contents}
:local:
:depth: 1
```

## Ollama

Ollama offers a free tier and can be used without an API key via the local app,
or with an API key for cloud-hosted models. The default model works on the free
tier.

| Model ID | Label | Note |
|----------|-------|------|
| `qwen3.5:cloud` | Qwen 3.5 Cloud (default) | fast cloud model, excellent tool calling and reasoning |
| `glm-5:cloud` | GLM-5 Cloud | capable cloud model with strong coding abilities |
| `kimi-k2.6:cloud` | Kimi K2.6 Cloud | advanced cloud model with large context window |
| `gemma4:31b-cloud` | Gemma 4 31B Cloud | larger cloud model for complex reasoning tasks |

**Default**: `qwen3.5:cloud`

## OpenAI

OpenAI provides GPT models via the OpenAI API. An API key is required.

| Model ID | Label | Note |
|----------|-------|------|
| `gpt-4o-mini` | GPT-4o Mini (default) | fast, affordable, excellent for most tasks |
| `gpt-5.4-mini` | GPT-5.4 Mini | strongest mini model for coding and computer use |
| `gpt-4.1` | GPT-4.1 | smartest non-reasoning model |
| `gpt-5.4` | GPT-5.4 | affordable frontier model for professional work |
| `gpt-5.5` | GPT-5.5 | latest flagship for coding and complex reasoning |

**Default**: `gpt-4o-mini`

## Anthropic

Anthropic provides Claude models via the Anthropic API. An API key is required.

| Model ID | Label | Note |
|----------|-------|------|
| `claude-haiku-4-5` | Claude Haiku 4.5 (default) | fastest with near-frontier intelligence |
| `claude-sonnet-5` | Claude Sonnet 5 | best speed/intelligence balance, adaptive thinking |
| `claude-opus-4-8` | Claude Opus 4.8 | most capable Opus-tier for complex reasoning |
| `claude-fable-5` | Claude Fable 5 | most capable widely released model |

**Default**: `claude-haiku-4-5`

## Google Gemini

Google Gemini offers a free tier accessible with a Google account. An API key
is required.

| Model ID | Label | Note |
|----------|-------|------|
| `gemini-2.5-flash-lite` | Gemini 2.5 Flash-Lite (default) | fastest, most budget-friendly model |
| `gemini-2.5-flash` | Gemini 2.5 Flash | best price-performance ratio, excellent for reasoning |
| `gemini-2.5-pro` | Gemini 2.5 Pro | most advanced for complex tasks and deep reasoning |
| `gemini-3.5-flash` | Gemini 3.5 Flash | most intelligent for agentic and coding tasks |
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro Preview | advanced reasoning, preview release |

**Default**: `gemini-2.5-flash-lite`

## Other Providers (Generic)

Any provider supported by [LiteLLM](https://docs.litellm.ai/) can be used by
setting `backend.provider` to the provider name (e.g. `groq`, `cohere`,
`azure`, `mistral`). A `GenericConfig` is created automatically. There is no
curated model list for generic providers — specify the model in your agent
definition or config:

```toml
[backend]
provider = "groq"

[backend.generic]
api_key = "${GROQ_API_KEY}"
model = "groq/llama-3.1-8b-instant"
```

## Known Model Limitations

The following limitations are noted in `src/yoker/bootstrap/providers.py`:

- **Gemma 3** (Ollama): Lacks native tool calling support; community
  workarounds are unreliable.
- **Gemini 3 via Ollama Cloud**: Has `thought_signature` issues with
  multi-turn tool calling.
- **Models smaller than 7B parameters**: May struggle with complex tool
  scenarios.

Provider-specific model lists change frequently. Check the official
documentation for the latest available models:

- OpenAI: <https://developers.openai.com/api/docs/models/all>
- Anthropic: <https://platform.claude.com/docs/en/about-claude/models/overview>
- Gemini: <https://ai.google.dev/gemini-api/docs/models>
- Ollama: <https://ollama.com/models> (look for the "tools" badge)

## Selecting a Model

You can select a model in three ways:

1. **Bootstrap wizard** — run `python -m yoker` with no config present. The
   wizard presents the curated list for your chosen provider.
2. **Config file** — set `model` under your provider's section in `yoker.toml`
   or `~/.yoker.toml`.
3. **Agent definition** — set `model` in the YAML frontmatter of an agent
   definition file. This overrides the config default.

```toml
# Example: Anthropic with Claude Sonnet 5
[backend]
provider = "anthropic"

[backend.anthropic]
api_key = "${ANTHROPIC_API_KEY}"
model = "claude-sonnet-5"
```