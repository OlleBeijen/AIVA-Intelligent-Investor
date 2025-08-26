import streamlit as st

def inject_css():
    st.markdown("""
    <style>
    :root {
      --radius: 16px;
      --pad: 12px;
    }
    .card {
      border: 1px solid #eaeaea;
      border-radius: var(--radius);
      padding: var(--pad);
      margin-bottom: 10px;
      background: rgba(255,255,255,0.6);
    }
    .muted { opacity: .8; font-size: .95rem; }
    .pill {
      display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid #ddd; margin-right:6px;
      font-size: .85rem; background: rgba(0,0,0,.03);
    }
    .hero h1 { margin-bottom: 0; }
    .hero p { margin-top: 6px; opacity: .85; }
    </style>
    """, unsafe_allow_html=True)

def hero(title: str, subtitle: str = ""):
    st.markdown(f"<div class='hero'><h1>{title}</h1><p class='muted'>{subtitle}</p></div>", unsafe_allow_html=True)