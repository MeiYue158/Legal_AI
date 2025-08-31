"""
Legal Summarization page (placeholder)
"""

import streamlit as st

def legal_summary_page():
    """Render the legal summarization page."""
    # Check if user is logged in
    if "user" not in st.session_state:
        st.error("Please log in to access this feature.")
        st.session_state["route"] = "login"
        st.experimental_rerun()
        return
    
    user = st.session_state["user"]
    
    st.title("📋 Legal Summarization")
    st.markdown(f"*Welcome, {user['username']}*")
    st.markdown("---")
    
    # Placeholder content
    st.info("🚧 This feature is coming soon!")
    st.markdown("""
    **Legal Summarization** will allow you to:
    - Upload legal documents
    - Generate concise summaries
    - Extract key points and findings
    - Save and organize summaries
    """)
    
    # Back to menu button
    if st.button("← Back to Menu", key="back_to_menu"):
        st.session_state["route"] = "menu"
        st.experimental_rerun()
