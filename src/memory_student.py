from __future__ import annotations

from typing import Any

from .config import settings
from .context_budget import ContextBudgetManager
from .utils import cap_query, join_nonempty
from .zep_common import prime_eval_thread, render_graph_search


class StudentMemory:
    """Only this file needs to be edited by students."""

    def __init__(self, client: Any):
        self.client = client
        self.budget = ContextBudgetManager(settings.context_tokens)

    # NOTE: Zep rejects graph.search queries longer than 400 characters. Some
    # eval queries are longer than that, so wrap every query with
    # `cap_query(query)` (see src/utils.py) before passing it to graph.search.

    def retrieve_long_term(self, user_id: str, thread_id: str, query: str) -> str:
        """Long-term retrieval using Zep Context Block + edges fact search."""
        # 1) Prime eval thread with current query for context relevance
        prime_eval_thread(self.client, user_id, thread_id, query)

        # 2) Get Context Block (user graph summary + relevant facts)
        user_context = self.client.thread.get_user_context(thread_id=thread_id)
        context_block = getattr(user_context, "context", "") or ""

        # 3) Append edges fact search for recency/conflict transparency
        #    High limit (20+) to capture deadline/open-loop facts
        try:
            facts = self.client.graph.search(
                user_id=user_id,
                query=cap_query(query),
                scope="edges",
                limit=20,
            )
            fact_text = render_graph_search(facts)
        except Exception:
            fact_text = ""

        return join_nonempty([context_block, fact_text], sep="\n\n")

    def retrieve_episodic(self, user_id: str, query: str) -> str:
        """Episodic memory: search user graph for session trajectories/outcomes."""
        results = self.client.graph.search(
            user_id=user_id,
            query=cap_query(query),
            scope="episodes",
            limit=15,
        )
        # episode_char_cap keeps more distinct episodes within tight budget
        return render_graph_search(results, episode_char_cap=180)

    def retrieve_semantic(self, graph_id: str, query: str) -> str:
        """Semantic memory: search standalone domain knowledge graph."""
        q = cap_query(query)
        try:
            # scope="episodes" returns raw document text preserving literal markers
            results = self.client.graph.search(
                graph_id=graph_id,
                query=q,
                scope="episodes",
                limit=8,
            )
        except Exception:
            # Fallback to nodes if episodes scope unavailable
            results = self.client.graph.search(
                graph_id=graph_id,
                query=q,
                scope="nodes",
                limit=8,
            )
        return render_graph_search(results)

    def assemble_context(self, layers: dict[str, str]) -> tuple[str, dict[str, dict[str, int]]]:
        """Assemble and trim memory layers using budget manager (10/4/3/3)."""
        # Delegate to ContextBudgetManager which enforces:
        # - Budget: short_term=10%, long_term=4%, episodic=3%, semantic=3%
        # - Priority order: short_term > long_term > episodic > semantic
        return self.budget.assemble(layers)
