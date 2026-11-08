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
        [data-testid="stHeader"], [data-testid="stSidebar"],
        [data-testid="collapsedControl"], [data-testid="stToolbar"],
        [data-testid="stDecoration"] {{ display: none !important; }}
        .block-container {{
          max-width: 1120px; padding-top: 6.3rem; padding-bottom: 3rem;
          padding-left: 1.25rem; padding-right: 1.25rem;
        }}
        .hf-site-header {{
          position: fixed; inset: 0 0 auto 0; z-index: 999999;
          height: 78px; background: color-mix(in srgb, var(--hf-bg) 94%, transparent);
          border-bottom: 1px solid var(--hf-line); backdrop-filter: blur(16px);
        }}
        .hf-header-inner {{
          max-width: 1120px; height: 100%; margin: 0 auto; padding: 0 1.25rem;
          display: flex; align-items: center; justify-content: space-between; gap: 1rem;
        }}
        .hf-brand {{ display: flex; align-items: center; gap: .85rem; min-width: 0; }}
        .hf-brand img {{ width: 48px; height: 48px; border-radius: 10px; flex: 0 0 auto; }}
        .hf-brand div {{ display: grid; gap: .14rem; min-width: 0; }}
        .hf-brand strong {{ color: var(--hf-ink); font-size: .78rem; letter-spacing: .12em; }}
        .hf-brand span {{ color: var(--hf-muted); font-size: .78rem; white-space: nowrap; }}
        .hf-call {{
          border-radius: 999px; padding: .65rem 1rem; background: var(--hf-deep);
          color: white !important; text-decoration: none; font-size: .86rem;
          font-weight: 750; white-space: nowrap;
        }}
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
        div[data-testid="stTabs"] button {{ font-weight: 750; }}
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap: .6rem; }}
        div[data-testid="stTabs"] [data-baseweb="tab"] {{
          border-radius: 999px; padding-left: 1.1rem; padding-right: 1.1rem;
          background: var(--hf-soft);
        }}
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
        .stButton > button[kind="primary"], .stFormSubmitButton > button {{
          color: white !important;
        }}
        .stFormSubmitButton > button {{
          background: var(--hf-coral); color: white; border: 0; min-height: 3rem;
        }}
        div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div {{ background: var(--hf-card); border-color: var(--hf-line); }}
        @media (max-width: 640px) {{
          .block-container {{ padding-top: 5.5rem; padding-left: 1rem; padding-right: 1rem; }}
          .hf-site-header {{ height: 68px; }}
          .hf-header-inner {{ padding: 0 .9rem; }}
          .hf-brand {{ gap: .6rem; }}
          .hf-brand img {{ width: 40px; height: 40px; }}
          .hf-brand strong {{ font-size: .66rem; letter-spacing: .08em; }}
          .hf-brand span {{ font-size: .66rem; max-width: 185px; overflow: hidden; text-overflow: ellipsis; }}
          .hf-call {{ padding: .55rem .7rem; font-size: 0; }}
          .hf-call::after {{ content: "Call"; font-size: .8rem; }}
          .hf-hero {{ padding: 1.35rem; border-radius: 1.25rem; margin-top: .3rem; }}
          .hf-hero h1 {{ font-size: 2.35rem; line-height: 1.04; }}
          .hf-hero p {{ font-size: .98rem; line-height: 1.65; }}
          .hf-crisis {{ padding: 1rem; border-radius: 1rem; }}
          div[data-testid="stHorizontalBlock"] {{ gap: .6rem; }}
          div[data-testid="stTextArea"] textarea {{ min-height: 210px !important; }}
          div[data-testid="stTabs"] [data-baseweb="tab-list"] {{ overflow-x: auto; }}
          div[data-testid="stTabs"] [data-baseweb="tab"] {{ padding-left: .7rem; padding-right: .7rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
