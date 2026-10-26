"""Web search tool implementation for Yoker.

Provides the ``websearch`` async function for searching the web through
pluggable backends.

Output-size protection (T7 pattern, see ``yoker.builtin.search``):
backends have been observed to return full-page text as the per-result
"snippet" (Ollama web_search returning 300KB+ per hit). Two caps guard
against that:

  - MAX_SNIPPET_CHARS limits every result's snippet; excess is elided
    with a visible marker that names the remedy (webfetch the URL).
  - A total byte budget (``WebSearchToolConfig.max_output_kb``, default
    50) stops result inclusion when the serialized size is exceeded:
    results stop, ``truncated`` flips true and a hint names the remedies.
    The same value backs the hard central gate
    (``_enforce_output_limit``), which rejects anything the graceful
    budget still lets through; the budget is enforced at 90% so the gate
    never false-trips on a graceful result.
"""

from typing import TYPE_CHECKING, Annotated

from structlog import get_logger

from yoker.tools.annotations import Query
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult
from yoker.tools.web import WebSearchError

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)

MAX_SNIPPET_CHARS: int = 500
_RESULT_BUDGET_FRACTION: float = 0.9


def _serialize_size(data: object) -> int:
  """Measure the serialized size of ``data`` like the central gate does (T7).

  ``_enforce_output_limit`` runs ``str(result)`` then UTF-8-encodes it — use
  the identical measurement so in-tool budget and hard backstop agree.
  """
  return len(str(data).encode("utf-8"))


def _cap_snippet(snippet: str) -> str:
  """Cap a single snippet at MAX_SNIPPET_CHARS with a visible marker."""
  if len(snippet) <= MAX_SNIPPET_CHARS:
    return snippet
  omitted = len(snippet) - MAX_SNIPPET_CHARS
  return f"{snippet[:MAX_SNIPPET_CHARS]}… (+{omitted} chars truncated — use webfetch on the URL for full content)"


async def websearch(
  query: Annotated[str, Query("Search query")],
  ctx: ToolContext,
  max_results: int = 10,
) -> ToolResult:
  """Search the web for information."""
  # Get backend from context
  backend = ctx.backends.get("websearch")

  if not query:
    return ToolResult(success=False, error="Query is required")

  if isinstance(query, str):
    if not query.strip():
      return ToolResult(success=False, error="Query cannot be empty or whitespace")

  if not isinstance(max_results, int):
    try:
      max_results = int(max_results)
    except (ValueError, TypeError):
      max_results = 10

  max_results = max(1, min(50, max_results))

  if backend is None:
    return ToolResult(success=False, error="No backend configured for web search")

  try:
    results = await backend.search(query=query, max_results=max_results)

    # T7: graceful output budget from config (same knob backs the central
    # gate); 0 disables it. Enforced at _RESULT_BUDGET_FRACTION so the
    # graceful result never false-trips the hard backstop.
    budget_bytes = 0
    if ctx.config is not None:
      budget_bytes = int(getattr(ctx.config, "max_output_kb", 50) or 0) * 1024
    budget_bytes = int(budget_bytes * _RESULT_BUDGET_FRACTION)

    included: list[dict[str, str]] = []
    truncated = False
    for r in results:
      entry = {
        "title": r.title,
        "url": r.url,
        "snippet": _cap_snippet(r.snippet),
        "source": r.source,
      }
      if budget_bytes > 0 and _serialize_size({"results": [*included, entry]}) > budget_bytes:
        truncated = True
        break
      included.append(entry)

    result: dict[str, object] = {"results": included, "count": len(included)}
    if truncated:
      result["total_hits"] = len(results)
      result["truncated"] = True
      result["hint"] = (
        "Result truncated by the output-size budget — narrow the search: "
        "reduce max_results, repeat the query with more specific terms, or "
        "webfetch one of the matched URLs for full content"
      )

    return ToolResult(
      success=True,
      result=result,
    )
  except WebSearchError as e:
    logger.error("Web search error: %s", e)
    return ToolResult(success=False, error=str(e))
  except Exception as e:
    logger.error("Unexpected error in web search: %s", e)
    return ToolResult(success=False, error=f"Search failed: {e}")


__all__ = ["websearch"]
