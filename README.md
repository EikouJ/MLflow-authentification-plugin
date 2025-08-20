#MLflow Authentication System

🔐 Authentication and role management system for MLflow with an administration interface.

## Features

- ✅ User/password authentication
- ✅ Role management (admin, user, viewer)
- ✅ Web administration interface
- ✅ API Keys for programmatic access
- ✅ Compatible with all MLflow versions 2.0+
- ✅ Deployment port independent
- ✅ Resistant to MLflow updates

## Quick Installation

```bash
# 1. Clone the project
git clone https://github.com/EikouJ/MLflow-authentification-plugin.git
cd MLflow-authentification-plugin

# 2. Automatic configuration
python deployment/setup_environment.py

# 3. Startup
source venv/bin/activate # Linux/Mac
# or venv\Scripts\activate # Windows
python deployment/start_mlflow.py

# 4. Access
MLflow UI : http://localhost:5000
Administration : http://localhost:5000/admin/users
Login par défaut : admin / admin123 (⚠️ à changer !)

# 5. Documentation
Installation détaillée
Configuration
Administration
API

# 6. Licence
MIT License