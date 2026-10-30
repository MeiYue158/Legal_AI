"""
Case Research page — end-to-end demo of retrieval + evidence highlighting.

Given a free-text legal query, retrieves the most similar cases from the
corpus (app.rag.retriever.retrieve). Two highlighting modes:

  - Similarity mode (default, free): highlights the sentence(s) in each
    case most similar to the query itself (find_evidence_span /
    highlight_evidence_html) — no LLM call.
  - LLM mode (opt-in, costs OpenAI credits): generates an actual answer
    (app.rag.generate.generate_answer) and highlights the exact passage
    the model quoted for each citation, verified against the source text —
    green for a verbatim match, orange when the model paraphrased and we
    fell back to the similarity heuristic instead.
"""

import streamlit as st

from app.rag.balance import retrieve_balanced
from app.rag.generate import generate_answer, render_citations_html
from app.rag.retriever import highlight_evidence_html, retrieve, retrieve_hybrid
from app.rag.stance_retrieval import retrieve_stance_aware

# (function, score label, LLM calls per query) — mirrors app/api/main.py.
# Only `dense` returns a cosine similarity; the rest return RRF fusion
# scores, which rank correctly but must not be shown as similarities.
STRATEGIES = {
    "Dense (vector only)": (retrieve, "similarity", 0),
    "Hybrid (dense + BM25)": (retrieve_hybrid, "fusion rank score", 0),
    "Balanced (adverse-aware)": (retrieve_balanced, "fusion rank score", 1),
    "Stance-aware (widest pool)": (retrieve_stance_aware, "fusion rank score", 2),
}


def case_research_page():
    """Render the case research page."""
    if "user" not in st.session_state:
        st.error("Please log in to access this feature.")
        st.session_state["route"] = "login"
        st.rerun()
        return

    user = st.session_state["user"]

    st.title("🔍 Case Research")
    st.markdown(f"*Welcome, {user['username']}*")
    st.markdown("---")

    st.markdown("""
    Enter a legal question or claim. The system retrieves the most similar
    cases from the corpus and highlights the sentence(s) in each case that
    most likely support it, so you can verify the citation at a glance.
    """)

    query = st.text_area(
        "Legal question or claim",
        placeholder="e.g. Can a landlord terminate a lease without notice for late rent?",
        height=100,
    )
    strategy_name = st.selectbox("Retrieval strategy", list(STRATEGIES.keys()))
    retrieve_fn, score_label, llm_calls = STRATEGIES[strategy_name]
    if llm_calls:
        st.caption(
            f"⚠️ Makes {llm_calls} OpenAI call{'s' if llm_calls > 1 else ''} per search "
            "(stance classification / query rewriting) — costs credits and is noticeably slower."
        )

    top_k = st.slider("Number of cases to retrieve", min_value=1, max_value=10, value=5)
    use_llm = st.checkbox(
        "🤖 Generate an LLM answer with verified citations (calls OpenAI API — costs credits)",
        value=False,
    )

    if st.button("Search", type="primary"):
        if not query.strip():
            st.error("Please enter a query.")
            return

        with st.spinner(f"Retrieving cases ({strategy_name})..."):
            try:
                results = retrieve_fn(query, k=top_k)
            except FileNotFoundError as e:
                st.error(f"Retrieval index not available: {e}")
                return
            except Exception as e:
                st.error(f"Retrieval failed ({strategy_name}): {e}")
                return

        if not results:
            st.info("No matching cases found.")
            return

        st.markdown(f"### Found {len(results)} case(s)")

        citations_by_case = {}
        if use_llm:
            with st.spinner("Generating answer..."):
                try:
                    generation = generate_answer(query, results)
                except Exception as e:
                    st.error(f"Answer generation failed: {e}")
                    generation = None

            if generation:
                st.markdown("### 🤖 Generated answer")
                st.markdown(generation["answer"])
                st.caption(
                    "🟢 green = exact quote verified against the source · "
                    "🟠 orange = model paraphrased; showing the closest matching sentence instead"
                )
                for citation in generation["citations"]:
                    citations_by_case.setdefault(citation["case_id"], []).append(citation)
                st.markdown("---")

        for i, case in enumerate(results, 1):
            score_text = (
                f"{case['score']:.2f}" if score_label == "similarity" else f"{case['score']:.4f}"
            )
            with st.expander(
                f"{i}. {case['case_name']} — {case['citation']} "
                f"({score_label}: {score_text})",
                expanded=(i == 1),
            ):
                case_citations = citations_by_case.get(case["case_id"])
                if case_citations:
                    highlighted = render_citations_html(case["case_text"], case_citations)
                else:
                    highlighted = highlight_evidence_html(case["case_text"], query, top_n=2)
                st.markdown(
                    f'<div style="line-height:1.6; max-height:400px; overflow-y:auto; '
                    f'padding:10px; border:1px solid #ddd; border-radius:4px;">'
                    f'{highlighted}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("---")
    if st.button("← Back to Menu", key="back_to_menu"):
        st.session_state["route"] = "menu"
        st.rerun()
