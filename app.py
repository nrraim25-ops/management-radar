"""app.py — Management Radar: Streamlit frontend with HDFC AMC theming."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from src.config import DB_PATH, GEMINI_API_KEY
from src.db import get_conn, init_db
from src.rag_pipeline import answer
from src.security import check_rate_limit

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Management Radar | HDFC AMC",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS: HDFC AMC palette ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Global */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Header */
.radar-header {
    background: linear-gradient(135deg, #0B1F3A 0%, #1a3560 100%);
    color: white;
    padding: 2rem 2.5rem 1.5rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.radar-header h1 {
    font-size: 2rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.5px;
}
.radar-header p {
    font-size: 0.95rem;
    opacity: 0.75;
    margin: 0.3rem 0 0;
}
.hdfc-accent { color: #ED1C24; }

/* Company selector */
.company-pill {
    display: inline-block;
    background: #F4F6F9;
    border: 2px solid #e0e4ea;
    border-radius: 999px;
    padding: 0.4rem 1.2rem;
    font-weight: 500;
    cursor: pointer;
    margin-right: 0.5rem;
    transition: all 0.2s;
    color: #0B1F3A;
}
.company-pill.active {
    background: #ED1C24;
    border-color: #ED1C24;
    color: white;
}

/* Source cards */
.source-card {
    background: white;
    border: 1px solid #e8edf2;
    border-left: 4px solid #ED1C24;
    border-radius: 10px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(11,31,58,0.07);
    transition: box-shadow 0.2s;
}
.source-card:hover { box-shadow: 0 4px 16px rgba(11,31,58,0.12); }
.source-card.failed {
    border-left-color: #f0a500;
    background: #fffbf0;
}

/* Badges */
.badge {
    display: inline-block;
    border-radius: 999px;
    padding: 0.15rem 0.7rem;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-right: 0.3rem;
}
.badge-pdf  { background: #e8f0fe; color: #1a56db; }
.badge-yt   { background: #fce8e6; color: #c0392b; }
.badge-fail { background: #fff3cd; color: #856404; }

/* Tag chips */
.tag-chip {
    display: inline-block;
    background: #F4F6F9;
    border: 1px solid #d0d8e4;
    color: #0B1F3A;
    border-radius: 6px;
    padding: 0.15rem 0.6rem;
    font-size: 0.75rem;
    font-weight: 500;
    margin-right: 0.3rem;
    margin-top: 0.3rem;
}

/* Chat area */
.chat-container {
    background: #F4F6F9;
    border-radius: 12px;
    padding: 1.5rem;
    min-height: 200px;
}
.chat-q {
    background: #0B1F3A;
    color: white;
    border-radius: 12px 12px 4px 12px;
    padding: 0.75rem 1.1rem;
    margin-bottom: 0.5rem;
    max-width: 80%;
    margin-left: auto;
}
.chat-a {
    background: white;
    border: 1px solid #e0e4ea;
    border-radius: 4px 12px 12px 12px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.5rem;
    max-width: 90%;
    line-height: 1.6;
}
.citation-chip {
    display: inline-block;
    background: #fff0f0;
    border: 1px solid #f5c6c6;
    color: #c0392b;
    border-radius: 6px;
    padding: 0.15rem 0.65rem;
    font-size: 0.75rem;
    font-weight: 500;
    margin: 0.2rem 0.2rem 0 0;
}

/* Section headers */
.section-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #0B1F3A;
    border-bottom: 2px solid #ED1C24;
    padding-bottom: 0.4rem;
    margin-bottom: 1rem;
}

/* Warning banner */
.warning-banner {
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    color: #664d03;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)


# ── Helper: DB ready check ────────────────────────────────────────────────────
def is_db_ready() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM sources WHERE fetch_status='ok'").fetchone()[0]
        return count > 0
    except Exception:
        return False


def get_companies() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT id, name FROM companies ORDER BY name").fetchall()]


def get_sources_for_company(company_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.title, s.source_type, s.published_date, s.fetch_status, s.fetch_error,
                   t.summary, t.tags
            FROM sources s
            LEFT JOIN source_tags t ON t.source_id = s.id
            WHERE s.company_id = ?
            ORDER BY CASE WHEN s.published_date GLOB '????-??-??' THEN s.published_date ELSE '9999' END ASC,
                     s.id ASC
            """,
            (company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_source_by_id(source_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT id, title, source_type, published_date FROM sources WHERE id=?", (source_id,)).fetchone()
    return dict(row) if row else {}


# ── Header ────────────────────────────────────────────────────────────────────
st.html("""
<div class="radar-header">
  <div style="font-size:2.5rem">📡</div>
  <div>
    <h1>Management <span class="hdfc-accent">Radar</span></h1>
    <p>Track management signals from BSE filings &amp; leadership interviews · Powered by HDFC AMC Research</p>
  </div>
</div>
""")

# ── Pipeline not run warning ───────────────────────────────────────────────────
if not is_db_ready():
    st.html("""
    <div class="warning-banner">
      &#9888; <strong>Pipeline not yet run.</strong>
      The database is empty or missing. Run the pipeline first:<br><br>
      <code>python scripts/run_pipeline.py</code>
    </div>
    """)
    st.stop()

# Ensure schema exists (in case DB file is there but uninitialized)
try:
    init_db()
except Exception:
    pass

# ── Company selector ──────────────────────────────────────────────────────────
companies = get_companies()
if not companies:
    st.warning("No companies found in the database. Run `python scripts/run_pipeline.py` first.")
    st.stop()

company_names = [c["name"] for c in companies]
company_ids   = {c["name"]: c["id"] for c in companies}

col_sel, col_info = st.columns([3, 7])
with col_sel:
    selected_company = st.radio(
        "**Select Company**",
        company_names,
        horizontal=False,
        key="company_selector",
    )

selected_company_id = company_ids[selected_company]

# ── Layout: two columns (timeline | chat) ─────────────────────────────────────
col_timeline, col_chat = st.columns([5, 4], gap="large")

# ── Timeline ──────────────────────────────────────────────────────────────────
with col_timeline:
    st.html(f'<div class="section-title">&#128197; Disclosure Timeline — {selected_company}</div>')

    sources = get_sources_for_company(selected_company_id)

    if not sources:
        st.info("No sources loaded yet for this company.")
    else:
        for s in sources:
            is_failed = s["fetch_status"] == "failed"
            card_cls = "source-card failed" if is_failed else "source-card"
            badge_cls = "badge-yt" if s["source_type"] == "youtube" else "badge-pdf"
            badge_label = "YouTube" if s["source_type"] == "youtube" else "BSE PDF"
            date_str = s["published_date"] or "—"

            if is_failed:
                fail_html = f'<span class="badge badge-fail">⚠ fetch failed</span>'
                fail_detail = f'<div style="font-size:0.78rem;color:#856404;margin-top:0.4rem">Error: {s["fetch_error"] or "unknown"}</div>'
            else:
                fail_html = ""
                fail_detail = ""

            summary_html = ""
            tags_html = ""
            if s.get("summary"):
                summary_html = f'<div style="font-size:0.87rem;color:#3d4f63;margin-top:0.6rem;line-height:1.55">{s["summary"]}</div>'

            if s.get("tags"):
                tag_list = [t.strip() for t in s["tags"].split(",") if t.strip()]
                chips = "".join(f'<span class="tag-chip">{t}</span>' for t in tag_list)
                tags_html = f'<div style="margin-top:0.5rem">{chips}</div>'

            card_html = f"""
            <div class="{card_cls}">
              <div style="display:flex;align-items:flex-start;gap:1rem">
                <div style="flex:1">
                  <div style="font-weight:600;color:#0B1F3A;font-size:0.95rem;line-height:1.4">{s["title"]}</div>
                  <div style="font-size:0.8rem;color:#6b7a8d;margin-top:0.25rem">
                    <span class="badge {badge_cls}">{badge_label}</span>
                    {fail_html}
                    &nbsp;{date_str}
                  </div>
                </div>
              </div>
              {summary_html}
              {tags_html}
              {fail_detail}
            </div>
            """
            st.html(card_html)


# ── Chat ──────────────────────────────────────────────────────────────────────
with col_chat:
    st.html(f'<div class="section-title">&#128172; Ask About {selected_company}</div>')

    if not GEMINI_API_KEY:
        st.warning("⚠️ GEMINI_API_KEY not set. Add it to `.env` to enable chat.")
    else:
        # Session state init
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = {}
        if "session_id" not in st.session_state:
            import uuid
            st.session_state.session_id = str(uuid.uuid4())
        if "question_counts" not in st.session_state:
            st.session_state.question_counts = {}

        session_id = st.session_state.session_id
        company_key = f"history_{selected_company_id}"
        history = st.session_state.chat_history.get(company_key, [])

        # Render chat history
        if history:
            chat_html = '<div class="chat-container">'
            for turn in history:
                q_html = f'<div class="chat-q">{turn["question"]}</div>'
                a_html = f'<div class="chat-a">{turn["answer"]}</div>'
                # Citation chips
                if turn.get("citations"):
                    cit_chips = "".join(
                        f'<span class="citation-chip">📄 {c["title"]} · {c["locator"]}</span>'
                        for c in turn["citations"]
                    )
                    a_html += f'<div style="margin-top:0.4rem">{cit_chips}</div>'
                chat_html += q_html + a_html
            chat_html += "</div>"
            st.html(chat_html)
        else:
            st.html('<div class="chat-container" style="display:flex;align-items:center;justify-content:center;color:#9aa5b4;font-size:0.9rem">Ask a question about this company\'s disclosures...</div>')

        # Input
        with st.form(key=f"chat_form_{selected_company_id}", clear_on_submit=True):
            user_q = st.text_input(
                "Your question",
                placeholder=f"e.g. What did {selected_company} say about revenue guidance?",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Ask →", use_container_width=True)

        if submitted and user_q.strip():
            # Rate limit check
            rate_err = check_rate_limit(session_id)
            if rate_err:
                st.error(rate_err)
            else:
                with st.spinner("Retrieving and generating answer..."):
                    result = answer(user_q.strip(), selected_company_id)

                # Build citations from chunks_used + cited_source_ids
                citations = []
                cited_ids_set = set(result.get("cited_source_ids", []))
                seen = set()
                for chunk in result.get("chunks_used", []):
                    sid = chunk["source_id"]
                    if sid in cited_ids_set and sid not in seen:
                        citations.append({
                            "title": chunk["source_title"],
                            "locator": chunk["locator"],
                            "source_id": sid,
                        })
                        seen.add(sid)

                turn = {
                    "question": user_q.strip(),
                    "answer": result["answer"],
                    "citations": citations,
                }
                history.append(turn)
                st.session_state.chat_history[company_key] = history
                st.rerun()

        # Clear chat button
        if history:
            if st.button("🗑 Clear chat", key=f"clear_{selected_company_id}"):
                st.session_state.chat_history[company_key] = []
                st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.html(
    '<div style="text-align:center;color:#9aa5b4;font-size:0.8rem">'
    "Management Radar · HDFC AMC Intern Challenge · Answers are grounded in indexed disclosures only"
    "</div>"
)
