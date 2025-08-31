"""
Login page for the Streamlit app
"""

import streamlit as st
from app.auth import authenticate_user

def login_page():
    """Render the login page."""
    st.title("Login")
    st.markdown("---")
    
    # Login form
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        
        submit_button = st.form_submit_button("Login", type="primary")
        
        if submit_button:
            if not username or not password:
                st.error("Please enter both username and password")
                return
            
            # Authenticate user
            success, message, user_data = authenticate_user(username, password)
            
            if success:
                st.success(message)
                
                # Set session state
                st.session_state["user"] = user_data
                st.session_state["route"] = "menu"
                
                # Auto-redirect to menu
                st.experimental_rerun()
            else:
                st.error(message)
    
    # Link to registration page
    st.markdown("---")
    st.markdown("Don't have an account?")
    if st.button("Create Account", key="register_link"):
        st.session_state["route"] = "register"
        st.experimental_rerun()
