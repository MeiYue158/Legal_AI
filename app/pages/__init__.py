"""
Pages package for the Streamlit app
"""

from .register import register_page
from .login import login_page
from .menu import menu_page
from .analysis import analysis_page
from .legal_summary import legal_summary_page
from .appeal_analysis import appeal_analysis_page

__all__ = [
    "register_page",
    "login_page", 
    "menu_page",
    "analysis_page",
    "legal_summary_page",
    "appeal_analysis_page"
]
