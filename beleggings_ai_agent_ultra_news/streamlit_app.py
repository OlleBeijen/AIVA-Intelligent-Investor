import streamlit as st
st.write('ULTRA++ minimal')


# ------- AI Chat -------
with tabs[2]:
    st.subheader("AI Chat (educatief)")
    st.caption("Vermijdt bindende koop/verkopen; praat in scenario's. Headlines dienen als context, niet als bewijs.")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    q = st.chat_input("Stel je vraag over tickers, sectoren of risico's...")
    if q:
        st.session_state["chat_history"].append({"role":"user", "content": q})
        with st.chat_message("assistant"):
            with st.spinner("Denken..."):
                ans = chat_answer(q, provider=cfg.get("news",{}).get("provider","auto"))
                st.markdown(ans["text"])
                # Show sources
                if ans["sources"]:
                    st.markdown("**Bronnen (laatste headlines):**")
                    for it in ans["sources"]:
                        st.markdown(f"- {it.get('publisher','?')}: [{it.get('title','(zonder titel)')}]({it.get('link','#')}) — _{it.get('ticker','')}_")
        st.session_state["chat_history"].append({"role":"assistant", "content": ans["text"]})
