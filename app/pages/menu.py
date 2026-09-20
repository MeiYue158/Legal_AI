"""
Main menu page for the Streamlit app
"""

import streamlit as st

def menu_page():
    """Render the main menu page."""
    # Check if user is logged in
    if "user" not in st.session_state:
        st.error("Please log in to access the menu.")
        st.session_state["route"] = "login"
        st.rerun()
        return
    
    user = st.session_state["user"]
    
    st.title(f"Welcome, {user['username']}! 👋")
    st.markdown("---")
    
    # Main menu options
    st.markdown("### Choose a feature to get started:")
    
    # Create four columns for the main options
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("#### 📋 Legal Summarization")
        st.markdown("Generate concise summaries of legal documents")
        if st.button("Open Legal Summarization", key="legal_summary", use_container_width=True):
            st.session_state["route"] = "legal_summary"
            st.rerun()
    
    with col2:
        st.markdown("#### ⚖️ Appeal Recommendation Analysis")
        st.markdown("Analyze cases and get appeal recommendations")
        if st.button("Open Appeal Analysis", key="appeal_analysis", use_container_width=True):
            st.session_state["route"] = "appeal_analysis"
            st.rerun()
    
    with col3:
        st.markdown("#### 🚨 Unfair Clause Detection")
        st.markdown("Detect potentially unfair clauses in contracts")
        if st.button("Open Unfair Clause Detection", key="unfair_detection", use_container_width=True):
            st.session_state["route"] = "analysis"
            st.rerun()

    with col4:
        st.markdown("#### 🔍 Case Research")
        st.markdown("Search cases with evidence highlighting")
        if st.button("Open Case Research", key="case_research", use_container_width=True):
            st.session_state["route"] = "case_research"
            st.rerun()

    # Additional information
    st.markdown("---")
    st.markdown("### Recent Activity")
    st.info("No recent activity to display")
    
    # User info
    st.markdown("---")
    with st.expander("Account Information"):
        st.write(f"**Username:** {user['username']}")
        st.write(f"**Email:** {user['email']}")
        st.write(f"**Member since:** {user['created_at'][:10]}")
        
        if st.button("Logout", type="secondary"):
            # Clear session and redirect to login
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state["route"] = "login"
            st.rerun()
