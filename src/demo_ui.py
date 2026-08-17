"""Premium mini-product UI — Lab 17 memory agent demo.

Full +10 (live demo) when ALL of these work:
1. Load test cases from `data/sessions.json` (public). Golden file optional.
2. Pick a case; UI shows query, expected layer, user_id, thread_id.
3. Run student memory retrieval and show per-layer evidence + merged context.
4. Chat box continues as that user/thread with Gemini grounded in memory context.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import settings
from src.llm import gemini_available, generate_reply
from src.memory_student import StudentMemory
from src.short_term import ShortTermMemory
from src.utils import GOLDEN_PATH, load_dataset, load_json
from src.zep_common import get_zep_client

# === Design Tokens ===
LAYER_CONFIG = {
    "short_term": {
        "color": "#3b82f6",
        "bg": "#eff6ff",
        "icon": "⚡",
        "desc": "Current conversation",
        "budget_pct": 10,
    },
    "long_term": {
        "color": "#10b981",
        "bg": "#ecfdf5",
        "icon": "🗂️",
        "desc": "Cross-session facts",
        "budget_pct": 4,
    },
    "episodic": {
        "color": "#f59e0b",
        "bg": "#fffbeb",
        "icon": "📜",
        "desc": "Past trajectories",
        "budget_pct": 3,
    },
    "semantic": {
        "color": "#8b5cf6",
        "bg": "#f5f3ff",
        "icon": "📚",
        "desc": "Domain knowledge",
        "budget_pct": 3,
    },
}

MARKER_PATTERN = re.compile(r"\b[A-Z]{2,}[A-Z0-9-]{3,}\b")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* Reset & Base */
.stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%); }
.block-container { padding-top: 1.5rem; max-width: 1400px; }

/* Header */
.header-title { font-family: 'Inter', sans-serif; font-weight: 700; font-size: 1.8rem;
    background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6); -webkit-background-clip: text;
    -webkit-text-fill-color: transparent; }

/* Cards */
.lab-card {
    background: linear-gradient(135deg, rgba(30,41,59,0.9), rgba(51,65,85,0.7));
    border: 1px solid rgba(148,163,184,0.15); border-radius: 16px;
    padding: 20px 24px; margin-bottom: 16px; backdrop-filter: blur(10px);
    transition: transform 0.2s, box-shadow 0.2s;
}
.lab-card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.3); }

/* Query Display */
.query-text { font-family: 'Inter', sans-serif; font-size: 1.1rem; line-height: 1.6;
    color: #f1f5f9; padding: 16px; background: rgba(15,23,42,0.6);
    border-radius: 12px; border-left: 4px solid; margin: 12px 0; }

/* Layer Badges */
.layer-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;
    margin: 4px; transition: all 0.2s;
}
.layer-badge:hover { transform: scale(1.05); filter: brightness(1.1); }

/* Metrics */
.metric-card {
    background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(51,65,85,0.6));
    border-radius: 12px; padding: 16px; text-align: center;
    border: 1px solid rgba(148,163,184,0.1);
}
.metric-value { font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: 700; }
.metric-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }

/* Budget Bar */
.budget-bar { height: 8px; border-radius: 4px; background: rgba(148,163,184,0.2);
    overflow: hidden; margin-top: 8px; }
.budget-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease-out; }

/* Evidence Panel */
.evidence-panel {
    background: linear-gradient(135deg, rgba(15,23,42,0.9), rgba(30,41,59,0.7));
    border-radius: 12px; padding: 16px; margin: 8px 0;
    border: 1px solid rgba(148,163,184,0.1);
    max-height: 400px; overflow-y: auto;
}
.evidence-panel::-webkit-scrollbar { width: 6px; }
.evidence-panel::-webkit-scrollbar-track { background: transparent; }
.evidence-panel::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.3); border-radius: 3px; }

/* Code blocks */
.stCodeBlock { border-radius: 12px !important; }

/* Chat */
.stChatMessage { border-radius: 16px !important; }
[data-testid="stChatMessageContent"] { padding: 12px 16px; }

/* Sidebar */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1e293b, #0f172a) !important; }

/* Buttons */
.stButton > button { border-radius: 10px !important; font-weight: 600 !important;
    transition: all 0.2s !important; }
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }

/* Expander */
.streamlit-expanderHeader { border-radius: 8px !important; background: rgba(30,41,59,0.5) !important; }

/* Animations */
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.fade-in { animation: fadeIn 0.4s ease-out; }

/* Marker highlighting */
.marker {
    background: linear-gradient(90deg, #fbbf24, #f59e0b);
    color: #1e293b; padding: 2px 6px; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 0.85em;
}

/* Layer diagram */
.layer-diagram {
    display: flex; justify-content: center; gap: 8px; flex-wrap: wrap;
    padding: 20px; background: rgba(15,23,42,0.5); border-radius: 12px; margin: 16px 0;
}
.layer-node {
    padding: 12px 20px; border-radius: 10px; text-align: center; min-width: 100px;
    transition: transform 0.2s;
}
.layer-node:hover { transform: scale(1.05); }
.layer-arrow { color: #64748b; font-size: 1.5rem; align-self: center; }
</style>
"""


def load_cases() -> list[dict[str, Any]]:
    cases = list(load_dataset()["evaluations"])
    if GOLDEN_PATH.exists():
        try:
            cases.extend(load_json(GOLDEN_PATH).get("evaluations") or [])
        except Exception:
            pass
    return cases


def format_case(case: dict[str, Any]) -> str:
    return f"{case['id']} · {case['expected_layer']}"


def highlight_markers(text: str) -> str:
    """Highlight Zep markers in text for visual emphasis."""
    if not text:
        return text
    return MARKER_PATTERN.sub(r'<span class="marker">\g<0></span>', text)


def render_layer_diagram(active_layers: list[str]) -> str:
    """Render a visual diagram of the 4 memory layers."""
    html = ['<div class="layer-diagram">']
    for i, (name, config) in enumerate(LAYER_CONFIG.items()):
        is_active = name in active_layers
        opacity = "1" if is_active else "0.35"
        html.append(
            f'<div class="layer-node" style="background:{config["bg"]}; opacity:{opacity}">'
            f'<div style="font-size:1.5rem">{config["icon"]}</div>'
            f'<div style="font-weight:600;color:{config["color"]};font-size:0.8rem">{name}</div>'
            f'<div style="font-size:0.7rem;color:#94a3b8">{config["budget_pct"]}%</div>'
            f'</div>'
        )
        if i < 3:
            html.append('<div class="layer-arrow">→</div>')
    html.append('</div>')
    return "".join(html)


def render_budget_meter(layer: str, budget: dict) -> str:
    """Render a budget usage meter for a layer."""
    cfg = LAYER_CONFIG.get(layer, {})
    used = budget.get("used_tokens", 0)
    limit = budget.get("limit_tokens", 1)
    raw = budget.get("raw_tokens", 0)
    pct = min(100, (used / limit * 100) if limit else 0)
    color = cfg.get("color", "#64748b")
    bg = cfg.get("bg", "#1e293b")

    return f"""
    <div style="padding:12px;background:{bg};border-radius:10px;margin:6px 0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-weight:600;color:{color}">{cfg.get("icon","")} {layer}</span>
            <span style="font-family:'JetBrains Mono';font-size:0.85rem;color:#94a3b8">{used}/{limit}</span>
        </div>
        <div class="budget-bar">
            <div class="budget-fill" style="width:{pct}%;background:{color}"></div>
        </div>
        <div style="font-size:0.75rem;color:#64748b;margin-top:6px">
            raw: {raw} tokens · {cfg.get("desc","")}
        </div>
    </div>
    """


def render_evidence_panel(layer: str, text: str) -> str:
    """Render a styled evidence panel for a layer."""
    cfg = LAYER_CONFIG.get(layer, {})
    highlighted = highlight_markers(text)
    return f"""
    <div class="evidence-panel fade-in">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
            <span style="font-size:1.2rem">{cfg.get("icon","📄")}</span>
            <span style="font-weight:700;color:{cfg.get("color","#94a3b8")}">{layer.upper()}</span>
            <span style="font-size:0.8rem;color:#64748b">{cfg.get("desc","")}</span>
        </div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.85rem;line-height:1.6;color:#e2e8f0">
            {highlighted or "<em style='color:#64748b'>No evidence retrieved</em>"}
        </div>
    </div>
    """


def render_case_card(case: dict[str, Any]) -> str:
    """Render a styled case information card."""
    layer = case.get("expected_layer", "?")
    cfg = LAYER_CONFIG.get(layer, {"color": "#94a3b8", "bg": "#1e293b", "icon": "❓"})
    border_color = cfg.get("color", "#64748b")

    return f"""
    <div class="lab-card fade-in">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
            <span style="font-size:1.5rem">{cfg.get("icon","")}</span>
            <div>
                <div style="font-size:1.4rem;font-weight:700;color:#f1f5f9">{case.get("id","?")}</div>
                <div style="font-size:0.8rem;color:#94a3b8">{case.get("description","")}</div>
            </div>
        </div>
        <div class="query-text" style="border-color:{border_color}">
            <div style="font-size:0.75rem;color:#64748b;margin-bottom:8px">QUERY</div>
            {case.get("query","")}
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px">
            <div><span style="color:#64748b">User:</span> <code style="color:#94a3b8">{case.get("user_id","-")}</code></div>
            <div><span style="color:#64748b">Thread:</span> <code style="color:#94a3b8">{case.get("thread_id","-")}</code></div>
        </div>
        {f"<div style='margin-top:12px;padding:8px 12px;background:rgba(239,68,68,0.1);border-radius:8px;font-size:0.85rem'>"
         f"<span style='color:#fca5a5'>Must NOT contain:</span> {', '.join(case.get('must_not_contain', []))}"
         f"</div>" if case.get("must_not_contain") else ""}
    </div>
    """


# === BONUS TODO: Core retrieval logic ===
def retrieve_for_case(
    memory: StudentMemory,
    case: dict[str, Any],
    extra_messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Run student retrieval for the loaded case."""
    user_id = case.get("user_id", "")
    thread_id = case.get("thread_id", "")
    query = case.get("query", "")
    expected_layer = case.get("expected_layer", "mixed")

    layers: dict[str, str] = {
        "short_term": "", "long_term": "", "episodic": "", "semantic": "",
    }

    # 1. Short-term memory
    stm = ShortTermMemory(strategy="sliding", max_recent_messages=6)
    if case.get("fixture_messages"):
        for msg in case["fixture_messages"]:
            stm.add(msg["role"], msg["content"])
    else:
        dataset = load_dataset()
        for user in dataset.get("users", []):
            if user["user_id"] == user_id:
                for session in user.get("sessions", []):
                    if session["thread_id"] == thread_id:
                        for msg in session.get("messages", []):
                            stm.add(msg["role"], msg["content"])
                        break
        for msg in extra_messages:
            stm.add(msg["role"], msg["content"])
    layers["short_term"] = stm.render()

    # 2. Determine layers to retrieve
    retrieve_layers = []
    if expected_layer == "mixed":
        retrieve_layers = ["long_term", "semantic"]
    elif expected_layer != "short_term":
        retrieve_layers = [expected_layer]

    # 3. Long-term
    if "long_term" in retrieve_layers and user_id and thread_id:
        layers["long_term"] = memory.retrieve_long_term(user_id, thread_id, query)

    # 4. Episodic
    if "episodic" in retrieve_layers and user_id:
        layers["episodic"] = memory.retrieve_episodic(user_id, query)

    # 5. Semantic
    if "semantic" in retrieve_layers:
        semantic_graph_id = settings.semantic_graph_id or "vinuni-lab17-domain-kb"
        layers["semantic"] = memory.retrieve_semantic(semantic_graph_id, query)

    # 6. Assemble
    merged_context, budget = memory.assemble_context(layers)
    return {"merged_context": merged_context, "layers": layers, "budget": budget}


# === Main UI ===
def main() -> None:
    st.set_page_config(
        page_title="🧠 Lab 17 Memory Agent",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    # === Header ===
    col_logo, col_title, col_status = st.columns([1, 3, 2])
    with col_logo:
        st.markdown("## 🧠")
    with col_title:
        st.markdown('<div class="header-title">Memory Agent Demo</div>', unsafe_allow_html=True)
        st.caption("Lab 17 — Multi-Memory System with Zep Cloud")
    with col_status:
        zep_ok = bool(settings.zep_api_key)
        gemini_ok = gemini_available()
        st.markdown(
            f"**Zep:** {'✅' if zep_ok else '❌'} · **Gemini:** {'✅' if gemini_ok else '❌'}",
            unsafe_allow_html=False,
        )

    # === Sidebar: Case Selection ===
    with st.sidebar:
        st.header("📋 Test Cases")
        st.caption("Select a benchmark case to analyze")
        st.divider()

        cases = load_cases()
        if not cases:
            st.error("No evaluation cases found.")
            return

        # Group by layer
        grouped: dict[str, list] = {}
        for c in cases:
            layer = c.get("expected_layer", "?")
            grouped.setdefault(layer, []).append(c)

        # Tabs for layers
        layer_tabs = st.tabs(list(grouped.keys()) + ["All"])

        case_map: dict[str, dict] = {}
        for tab, (layer, layer_cases) in zip(layer_tabs[:-1], grouped.items()):
            with tab:
                for c in layer_cases:
                    key = f"{c['id']} · {c['description'][:40]}..."
                    case_map[key] = c
                    if st.button(key, use_container_width=True, key=f"case_{c['id']}"):
                        st.session_state.selected_case = c
                        st.session_state.chat = []
                        st.session_state.pop("last_result", None)

        with layer_tabs[-1]:
            for c in cases:
                key = f"{c['id']} ({c['expected_layer']})"
                case_map[key] = c
                if st.button(key, use_container_width=True, key=f"case_all_{c['id']}"):
                    st.session_state.selected_case = c
                    st.session_state.chat = []
                    st.session_state.pop("last_result", None)

        # Default selection
        if "selected_case" not in st.session_state and cases:
            st.session_state.selected_case = cases[0]
        case = st.session_state.selected_case

    # === Main Content ===
    if case:
        # Case Info Card
        st.markdown(render_case_card(case), unsafe_allow_html=True)

        # Run Button
        col_run, col_reset = st.columns([2, 1])
        with col_run:
            if st.button("▶️ Run Memory Retrieval", use_container_width=True, type="primary"):
                try:
                    with st.spinner("🔍 Retrieving from memory layers..."):
                        memory = StudentMemory(get_zep_client())
                        st.session_state.last_result = retrieve_for_case(
                            memory, case, st.session_state.chat
                        )
                        st.session_state.case_id = case["id"]
                except Exception as exc:
                    st.error(f"Retrieval failed: {exc}")

        with col_reset:
            if st.button("🔄 Reset Chat", use_container_width=True):
                st.session_state.chat = []
                st.session_state.pop("last_result", None)
                st.rerun()

        # Results
        result = st.session_state.get("last_result")
        if result:
            st.divider()

            # Layer Diagram
            active = [k for k, v in result["layers"].items() if v.strip()]
            st.markdown("#### Memory Architecture")
            st.markdown(render_layer_diagram(active), unsafe_allow_html=True)

            # Budget Overview
            st.markdown("#### Token Budget")
            cols = st.columns(4)
            for i, layer in enumerate(("short_term", "long_term", "episodic", "semantic")):
                with cols[i]:
                    cfg = LAYER_CONFIG[layer]
                    b = result["budget"].get(layer, {})
                    used = b.get("used_tokens", 0)
                    limit = b.get("limit_tokens", 1)
                    pct = min(100, (used / limit * 100) if limit else 0)

                    st.markdown(f"""
                    <div class="metric-card">
                        <div style="font-size:1.5rem">{cfg["icon"]}</div>
                        <div class="metric-value" style="color:{cfg["color"]}">{used}</div>
                        <div class="metric-label">{layer.replace("_", " ")}</div>
                        <div class="budget-bar">
                            <div class="budget-fill" style="width:{pct}%;background:{cfg["color"]}"></div>
                        </div>
                        <div style="font-size:0.7rem;color:#64748b;margin-top:4px">{pct:.0f}% of {limit}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Detailed Evidence Tabs
            st.divider()
            st.markdown("#### 📊 Evidence by Layer")

            tabs = st.tabs([f"{LAYER_CONFIG[l]['icon']} {l.title()}" for l in active] if active else ["No Evidence"])
            for i, layer in enumerate(active):
                with tabs[i]:
                    st.markdown(render_evidence_panel(layer, result["layers"][layer]), unsafe_allow_html=True)
                    with st.expander("📋 Raw Text"):
                        st.code(result["layers"][layer] or "(empty)", language="markdown")

            # Merged Context
            st.divider()
            st.markdown("#### 🔗 Merged Context")
            merged = result.get("merged_context", "")
            if merged:
                st.markdown(render_evidence_panel("merged", merged), unsafe_allow_html=True)
            else:
                st.warning("No merged context available")

            with st.expander("📄 Raw Merged Output"):
                st.code(merged or "(empty)", language="markdown")

    # === Chat Section ===
    st.divider()
    st.markdown("### 💬 Continue Chat as This User")

    # Chat history
    for msg in st.session_state.get("chat", []):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    prompt = st.chat_input("Type a message as this user...")
    if prompt and case:
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        try:
            memory = StudentMemory(get_zep_client())
            follow = retrieve_for_case(memory, {**case, "query": prompt}, st.session_state.chat)
            st.session_state.last_result = follow

            context = follow.get("merged_context", "")
            if gemini_available():
                with st.spinner("🤖 Generating response..."):
                    reply = generate_reply(context, st.session_state.chat[:-1], prompt)
            else:
                reply = f"_(Gemini not available — retrieved context preview)_\n\n{context[:1000] or '(no memory)'}"

            st.session_state.chat.append({"role": "assistant", "content": reply})
            with st.chat_message("assistant"):
                st.write(reply)
        except Exception as exc:
            st.error(f"Chat failed: {exc}")


if __name__ == "__main__":
    main()
