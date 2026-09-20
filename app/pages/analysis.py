"""
Analysis page for unfair clause detection
Reuses the existing ContractAnalysisUI component
"""

import streamlit as st
from app.components.contract_analysis_ui import ContractAnalysisUI

def analysis_page():
    """Render the unfair clause detection analysis page."""
    # Check if user is logged in
    if "user" not in st.session_state:
        st.error("Please log in to access the analysis.")
        st.session_state["route"] = "login"
        st.rerun()
        return
    
    user = st.session_state["user"]
    
    # Page header
    st.title("🚨 Unfair Clause Detection")
    st.markdown(f"*Analyzing contracts for user: {user['username']}*")
    st.markdown("---")
    
    # Back to menu button
    if st.button("← Back to Menu", key="back_to_menu"):
        st.session_state["route"] = "menu"
        st.rerun()
    
    st.markdown("---")
    
    # Render the existing analysis UI
    try:
        ContractAnalysisUI.render_pipeline_upload()
    except Exception as e:
        st.error(f"Error loading analysis interface: {e}")
        st.info("Please try refreshing the page or contact support if the issue persists.")
    
    # Additional navigation
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("← Back to Menu", key="back_to_menu_bottom"):
            st.session_state["route"] = "menu"
            st.rerun()
    
    with col2:
        if st.button("🔄 Refresh Analysis", key="refresh_analysis"):
            st.rerun()
