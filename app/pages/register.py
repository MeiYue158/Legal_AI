"""
Registration page for the Streamlit app
"""

import streamlit as st
import re
from app.auth import create_user

def register_page():
    """Render the registration page."""
    st.title("Create Account")
    st.markdown("---")
    
    # Registration form
    with st.form("registration_form"):
        username = st.text_input("Username", placeholder="Enter your username")
        email = st.text_input("Email", placeholder="Enter your email address")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")

        # Collected for stratified randomization + heterogeneous-effect analysis
        # (law vs non-law) in the citation-highlighting experiment.
        expertise_choice = st.radio(
            "Do you have a legal background (law student, paralegal, attorney, etc.)?",
            options=["Yes", "No"],
            horizontal=True,
        )

        submit_button = st.form_submit_button("Create Account", type="primary")
        
        if submit_button:
            # Validation
            if not username or not email or not password or not confirm_password:
                st.error("All fields are required")
                return
            
            if len(username) < 3:
                st.error("Username must be at least 3 characters long")
                return
            
            if len(password) < 6:
                st.error("Password must be at least 6 characters long")
                return
            
            if password != confirm_password:
                st.error("Passwords do not match")
                return
            
            # Basic email validation
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                st.error("Please enter a valid email address")
                return
            
            # Create user
            legal_expertise = "law" if expertise_choice == "Yes" else "non_law"
            success, message = create_user(username, email, password, legal_expertise)
            
            if success:
                st.success(message)
                st.markdown("---")
                
                # Navigation button
                if st.button("Go to Login", type="secondary"):
                    st.session_state["route"] = "login"
                    st.rerun()
            else:
                st.error(message)
    
    # Link to login page
    st.markdown("---")
    st.markdown("Already have an account?")
    if st.button("Go to Login", key="login_link"):
        st.session_state["route"] = "login"
        st.rerun()
