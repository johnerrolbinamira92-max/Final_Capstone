from __future__ import annotations

import streamlit as st


def apply_styles(dark: bool) -> None:
    colors = (
        {
            "bg": "#122323",
            "card": "#19302F",
            "soft": "#203A38",
            "ink": "#F5F4E9",
            "muted": "#AFC0BC",
            "line": "#34504D",
            "deep": "#346D69",
            "teal": "#88C0B8",
            "mint": "#294B46",
            "coral": "#DF8A7D",
        }
        if dark
        else {
            "bg": "#F8F7EF",
            "card": "#FFFEF9",
            "soft": "#EFEEE3",
            "ink": "#203B3B",
            "muted": "#667674",
            "line": "#D8D9CC",
            "deep": "#244C4B",
            "teal": "#4F8D88",
            "mint": "#DCEBE0",
            "coral": "#DB7F72",
        }
    )
    st.markdown(
        f"""
        <style>
        :root {{
          --hf-bg: {colors["bg"]};
          --hf-card: {colors["card"]};
          --hf-soft: {colors["soft"]};
          --hf-ink: {colors["ink"]};
          --hf-muted: {colors["muted"]};
          --hf-line: {colors["line"]};
          --hf-deep: {colors["deep"]};
          --hf-teal: {colors["teal"]};
          --hf-mint: {colors["mint"]};
          --hf-coral: {colors["coral"]};
        }}
        .stApp {{ background: var(--hf-bg); color: var(--hf-ink); }}
        [data-testid="stHeader"] {{ background: color-mix(in srgb, var(--hf-bg) 92%, transparent); }}
        [data-testid="stSidebar"] {{ background: var(--hf-soft); }}
        h1, h2, h3 {{ font-family: Georgia, "Times New Roman", serif !important; color: var(--hf-ink) !important; }}
        p, label, [data-testid="stCaptionContainer"] {{ color: var(--hf-muted); }}
        .hf-kicker {{
          color: var(--hf-teal); font-weight: 800; font-size: .78rem;
          letter-spacing: .16em; text-transform: uppercase;
        }}
        .hf-hero {{
          padding: 2rem; border: 1px solid var(--hf-line); border-radius: 1.75rem;
          background: radial-gradient(circle at 90% 20%, var(--hf-mint), transparent 42%), var(--hf-card);
          margin-bottom: 1.4rem;
        }}
        .hf-hero h1 {{ font-size: clamp(2.6rem, 7vw, 5rem); line-height: 1.02; letter-spacing: -.045em; margin: .6rem 0 1rem; }}
        .hf-hero p {{ max-width: 44rem; font-size: 1.08rem; line-height: 1.7; }}
        .hf-crisis {{
          border-radius: 1.25rem; padding: 1.1rem 1.3rem; margin: .5rem 0 1.5rem;
          background: var(--hf-deep); color: white;
        }}
        .hf-crisis strong, .hf-crisis p {{ color: white; }}
        .hf-card {{
          border: 1px solid var(--hf-line); border-radius: 1.35rem;
          background: var(--hf-card); padding: 1.25rem; margin-bottom: 1rem;
        }}
        .hf-badge {{
          display: inline-block; border-radius: 999px; padding: .3rem .7rem;
          background: var(--hf-mint); color: var(--hf-deep); font-size: .75rem; font-weight: 800;
        }}
        .stButton > button, .stFormSubmitButton > button {{
          border-radius: 999px; border: 1px solid var(--hf-line); font-weight: 750;
        }}
        .stFormSubmitButton > button {{
          background: var(--hf-coral); color: white; border: 0; min-height: 3rem;
        }}
        div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div {{ background: var(--hf-card); border-color: var(--hf-line); }}
        @media (max-width: 640px) {{
          .hf-hero {{ padding: 1.35rem; border-radius: 1.25rem; }}
          .hf-hero h1 {{ font-size: 2.75rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
