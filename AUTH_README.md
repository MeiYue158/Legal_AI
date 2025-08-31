# 🔐 Authentication System - Legal AI Deep Research

## 🚀 **Quick Start**

### **Run the Application**
```bash
streamlit run app/main.py
```

### **Default Flow**
1. **First Visit** → Register page
2. **Create Account** → Login page  
3. **Login** → Main Menu
4. **Select Feature** → Analysis/Features

## 🏗️ **Architecture Overview**

### **File Structure**
```
app/
├── auth.py                 # Authentication helper module
├── main.py                 # Main router and app entry point
├── pages/                  # Page modules
│   ├── __init__.py
│   ├── register.py         # User registration
│   ├── login.py           # User login
│   ├── menu.py            # Main menu hub
│   ├── analysis.py        # Unfair clause detection (existing UI)
│   ├── legal_summary.py   # Legal summarization (placeholder)
│   └── appeal_analysis.py # Appeal analysis (placeholder)
└── components/             # Existing UI components
    └── contract_analysis_ui.py
```

### **Authentication Flow**
```
Register → Success → Login → Menu → Analysis
    ↓           ↓        ↓      ↓       ↓
  Create    Show      Verify  Choose  Access
  Account   Success   Creds   Feature Feature
```

## 🔧 **Technical Implementation**

### **Database**
- **SQLite** database (`auth.db` by default)
- **Configurable** via `AUTH_DB_PATH` environment variable
- **Auto-initialized** on first app load

### **Password Security**
- **bcrypt** hashing with salt
- **Never stored** in plain text
- **Secure verification** using constant-time comparison

### **Session Management**
- **Streamlit session state** for user data
- **Route-based navigation** with protection
- **Automatic logout** on session clear

## 📱 **User Experience**

### **Registration Page**
- Username (min 3 chars)
- Email validation
- Password (min 6 chars)
- Password confirmation
- Duplicate username/email handling

### **Login Page**
- Username/password authentication
- Error handling for invalid credentials
- Link to registration

### **Main Menu**
- Welcome message with username
- Three feature options:
  - 📋 Legal Summarization (Coming Soon)
  - ⚖️ Appeal Recommendation Analysis (Coming Soon)
  - 🚨 Unfair Clause Detection (Available)

### **Analysis Page**
- **Reuses existing UI** from `ContractAnalysisUI.render_pipeline_upload()`
- **Login required** to access
- **Back to Menu** navigation
- **User context** displayed

## 🛡️ **Security Features**

### **Route Protection**
- **Authentication required** for all features
- **Automatic redirect** to login if not authenticated
- **Session validation** on each page

### **Input Validation**
- **Client-side validation** for immediate feedback
- **Server-side validation** for security
- **SQL injection protection** via parameterized queries

### **Error Handling**
- **Graceful degradation** on database errors
- **User-friendly error messages**
- **Logging** for debugging

## 🔄 **Navigation System**

### **Router Implementation**
```python
ROUTES = {
    "register": register_page,
    "login": login_page,
    "menu": menu_page,
    "analysis": analysis_page,
    "legal_summary": legal_summary_page,
    "appeal_analysis": appeal_analysis_page
}

def go(route: str):
    st.session_state["route"] = route
    st.experimental_rerun()
```

### **Navigation Patterns**
- **Page-to-page** navigation via buttons
- **Sidebar shortcuts** for logged-in users
- **Automatic routing** based on authentication status

## 🧪 **Testing the System**

### **1. Start the App**
```bash
streamlit run app/main.py
```

### **2. Create Account**
- Navigate to Register page
- Fill in username, email, password
- Submit and verify success message

### **3. Login**
- Use created credentials
- Verify redirect to Menu page

### **4. Access Features**
- Click "Unfair Clause Detection"
- Verify existing analysis UI loads
- Test "Back to Menu" functionality

### **5. Logout**
- Use sidebar logout button
- Verify redirect to Login page

## 🔧 **Configuration**

### **Environment Variables**
```bash
# Optional: Custom database path
export AUTH_DB_PATH="/path/to/custom/auth.db"

# Default: auth.db in project root
```

### **Database Schema**
```sql
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

## 🚧 **Coming Soon Features**

### **Legal Summarization**
- Document upload and processing
- AI-powered summarization
- Summary storage and organization

### **Appeal Recommendation Analysis**
- Case analysis interface
- Appeal success probability
- Strategy recommendations

## 📝 **Notes**

- **Existing imports** preserved for `ContractAnalysisUI`
- **CSS styling** maintained from original app
- **Session state** used for navigation and user data
- **Error boundaries** implemented for graceful failures
- **Backward compatibility** maintained for existing components

## 🆘 **Troubleshooting**

### **Common Issues**
1. **Database errors**: Check file permissions for `auth.db`
2. **Import errors**: Ensure all dependencies installed (`pip install -r requirements.txt`)
3. **Navigation issues**: Clear browser cache or restart Streamlit

### **Debug Mode**
- Check Streamlit console for error messages
- Verify database file creation
- Test individual page imports

The authentication system is now fully integrated with your existing unfair clause detection UI, providing a secure and user-friendly experience while maintaining all existing functionality.
