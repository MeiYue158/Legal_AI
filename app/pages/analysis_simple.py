"""
Simplified Analysis page for unfair clause detection
This version avoids importing problematic dependencies
"""

import streamlit as st

def analysis_simple_page():
    """Render a simplified unfair clause detection page."""
    # Check if user is logged in
    if "user" not in st.session_state:
        st.error("Please log in to access the analysis.")
        st.session_state["route"] = "login"
        st.experimental_rerun()
        return
    
    user = st.session_state["user"]
    
    # Page header
    st.title("🚨 Unfair Clause Detection")
    st.markdown(f"*Analyzing contracts for user: {user['username']}*")
    st.markdown("---")
    
    # Back to menu button
    if st.button("← Back to Menu", key="back_to_menu"):
        st.session_state["route"] = "menu"
        st.experimental_rerun()
    
    st.markdown("---")
    
    # Simplified interface
    st.markdown("### 📄 Contract Analysis")
    st.markdown("""
    This feature analyzes contracts to detect potentially unfair clauses using advanced NLP models.
    
    **Note**: The full analysis interface is temporarily simplified due to dependency compatibility issues.
    """)
    
    # File upload (simplified)
    uploaded_file = st.file_uploader(
        "Choose a contract file",
        type=['pdf', 'txt'],
        help="Upload a contract document for analysis"
    )
    
    # Text input
    st.markdown("**Or paste contract text directly:**")
    contract_text = st.text_area(
        "Contract Text",
        height=200,
        placeholder="Paste your contract text here..."
    )
    
    # Analysis button
    if st.button("🔍 Analyze Contract", type="primary"):
        if uploaded_file or contract_text.strip():
            st.info("🚧 Analysis feature is being restored. Please check back soon!")
            
            # Show what would be analyzed
            if uploaded_file:
                st.success(f"✅ File uploaded: {uploaded_file.name}")
            if contract_text.strip():
                st.success(f"✅ Text input received ({len(contract_text)} characters)")
        else:
            st.warning("⚠️ Please upload a file or enter contract text to analyze.")
    
    # Placeholder for results
    st.markdown("---")
    st.markdown("### 📊 Analysis Results")
    st.info("""
    **Coming Soon**: Full unfair clause detection with:
    - Pattern-based detection
    - Machine learning classification
    - Risk assessment
    - Detailed recommendations
    - Export capabilities
    """)
    
    # Additional navigation
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("← Back to Menu", key="back_to_menu_bottom"):
            st.session_state["route"] = "menu"
            st.experimental_rerun()
    
    with col2:
        if st.button("🔄 Refresh Page", key="refresh_analysis"):
            st.experimental_rerun()
