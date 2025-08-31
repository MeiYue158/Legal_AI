import os
import streamlit as st
import sys

# Fix OpenMP conflict issue
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import authentication module
from app.auth import init_db

# Import page functions
from app.pages.register import register_page
from app.pages.login import login_page
from app.pages.menu import menu_page
from app.pages.analysis_simple import analysis_simple_page  # Use simplified version
from app.pages.legal_summary import legal_summary_page
from app.pages.appeal_analysis import appeal_analysis_page

# Page configuration
st.set_page_config(
    page_title="Legal AI Deep Research",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add custom CSS
st.markdown(
    """
    <style>
    /* Main content area */
    .main > div {
        max-width: 1200px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    /* Ensure consistent sidebar width */
    .css-1d391kg {
        width: 14rem !important;
    }

    /* Main container styles */
    .stApp {
        max-width: 100%;
        width: 100%;
    }

    /* Form container styles */
    .stForm {
        width: 100%;
        max-width: 1200px;
        margin: 0 auto;
    }

    /* Text area consistent sizing */
    .stTextArea textarea {
        min-height: 100px;
        width: 100% !important;
        box-sizing: border-box;
    }

    /* Headers */
    h1, h2, h3 {
        color: #1E4175;
        margin: 1rem 0;
        width: 100%;
    }

    /* Button styles */
    .stButton button {
        background-color: #1E4175;
        color: white;
        width: 100%;
        margin: 0.5rem 0;
    }

    /* Download button exception */
    .stDownloadButton button {
        width: auto;
        margin: 1rem 0;
        padding: 0.5rem 1rem;
    }

    /* Progress bar */
    .stProgress .st-bo {
        background-color: #1E4175;
    }

    /* Prevent horizontal scroll */
    .element-container {
        width: 100% !important;
        overflow-x: hidden;
    }

    /* Ensure markdown containers don't cause shifts */
    .stMarkdown {
        width: 100% !important;
    }

    /* Tab container styles */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        width: 100%;
    }

    .stTabs [data-baseweb="tab-panel"] {
        width: 100%;
    }

    /* Add padding at the bottom to prevent content from being hidden behind the footer */
    .main .block-container {
        padding-bottom: 5rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize database on first load
if "db_initialized" not in st.session_state:
    try:
        init_db()
        st.session_state["db_initialized"] = True
    except Exception as e:
        st.error(f"Failed to initialize database: {e}")
        st.stop()

# Navigation helper
def go(route: str):
    """Navigate to a specific route."""
    st.session_state["route"] = route
    st.experimental_rerun()

# Route definitions
ROUTES = {
    "register": register_page,
    "login": login_page,
    "menu": menu_page,
    "analysis": analysis_simple_page,  # Use simplified version
    "legal_summary": legal_summary_page,
    "appeal_analysis": appeal_analysis_page
}

# Sidebar
with st.sidebar:
    st.markdown("## ⚖️ Legal AI Deep Research")
    
    # Check authentication status
    user = st.session_state.get("user")
    
    if user:
        st.markdown(f"**Welcome, {user['username']}!**")
        st.markdown(f"*{user['email']}*")
        st.markdown("---")
        
        # Logout button
        if st.button("🚪 Logout", type="secondary", use_container_width=True):
            # Clear session and redirect to login
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state["route"] = "login"
            st.experimental_rerun()
        
        st.markdown("---")
        st.markdown("**Quick Navigation:**")
        
        if st.button("🏠 Menu", key="sidebar_menu"):
            go("menu")
        
        if st.button("🚨 Analysis", key="sidebar_analysis"):
            go("analysis")
            
    else:
        st.markdown("**Please log in to access features**")
        st.markdown("---")
        
        if st.button("🔐 Login", key="sidebar_login"):
            go("login")
        
        if st.button("📝 Register", key="sidebar_register"):
            go("register")
    
    st.markdown("---")
    st.markdown("### 📚 Features")
    st.markdown("""
    - **Legal Summarization** - Coming Soon
    - **Appeal Analysis** - Coming Soon  
    - **Unfair Clause Detection** - Available (Simplified)
    """)
    
    st.markdown("---")
    st.markdown("### ⚙️ About")
    st.info("""
    Advanced legal AI system for:
    - Contract analysis
    - Legal document processing
    - AI-powered legal insights
    """)

# Main routing logic
def main():
    """Main routing function."""
    # Get current route and user status
    route = st.session_state.get("route")
    user = st.session_state.get("user")
    
    # Route protection: redirect to login if not authenticated
    if not user and route not in ("login", "register"):
        route = "login"
    
    # Default route logic
    if not route:
        route = "menu" if user else "login"
    
    # Get the page function
    page_fn = ROUTES.get(route, login_page)
    
    # Render the page
    try:
        page_fn()
    except Exception as e:
        st.error(f"Error rendering page: {e}")
        st.info("Redirecting to login page...")
        go("login")

# Run the main function
if __name__ == "__main__":
    main()
