#!/usr/bin/env python3
"""
Configuration automatique de l'environnement MLflow avec authentification
"""

import os
import sys
import subprocess
import venv
from pathlib import Path

def create_virtual_environment():
    """Crée l'environnement virtuel"""
    
    venv_path = Path(__file__).parent / "venv"
    
    if venv_path.exists():
        print("📁 Environnement virtuel existant trouvé")
        return venv_path
    
    print("🐍 Création de l'environnement virtuel...")
    venv.create(venv_path, with_pip=True)
    print("✅ Environnement virtuel créé")
    
    return venv_path

def get_venv_paths(venv_path):
    """Retourne les chemins vers python et pip dans le venv"""
    
    if os.name == 'nt':  # Windows
        python_path = venv_path / "Scripts" / "python.exe"
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:  # Unix/Linux/Mac
        python_path = venv_path / "bin" / "python"
        pip_path = venv_path / "bin" / "pip"
    
    return str(python_path), str(pip_path)

def install_requirements(pip_path):
    """Installe les dépendances"""
    
    print("📦 Installation de MLflow et des dépendances...")
    
    requirements = [
        "mlflow>=2.0.0",
        "flask-login>=0.6.0", 
        "flask-bcrypt>=1.0.0",
        "sqlalchemy>=1.4.0",
        "wtforms>=3.0.0",
        "flask-wtf>=1.0.0",
        "alembic>=1.8.0",
    ]
    
    cmd = [pip_path, "install", "--upgrade"] + requirements
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Erreur installation : {result.stderr}")
        return False
    
    print("✅ Dépendances installées")
    return True

def install_auth_plugin(pip_path):
    """Installe le plugin d'authentification"""
    
    plugin_path = Path(__file__).parent.parent / "mlflow-auth-plugin"
    
    if not plugin_path.exists():
        print("❌ Plugin d'authentification non trouvé")
        return False
    
    print("🔐 Installation du plugin d'authentification...")
    
    cmd = [pip_path, "install", "-e", str(plugin_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Erreur installation plugin : {result.stderr}")
        return False
    
    print("✅ Plugin d'authentification installé")
    return True

def create_directories():
    """Crée les répertoires nécessaires"""
    
    base_dir = Path(__file__).parent
    directories = ["data", "artifacts", "logs", "config"]
    
    for dir_name in directories:
        dir_path = base_dir / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"📁 Répertoire créé : {dir_path}")

def create_env_file():
    """Crée le fichier de configuration d'environnement"""
    
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        print("⚠️  Fichier .env existant, conservation des paramètres")
        return
    
    base_dir = Path(__file__).parent
    
    env_content = f"""# Configuration MLflow avec authentification

# Authentification
MLFLOW_AUTH_ENABLED=true
MLFLOW_AUTH_SECRET_KEY=change-this-secret-key-in-production

# Base de données
MLFLOW_BACKEND_STORE_URI=sqlite:///{base_dir}/data/mlflow.db

# Stockage des artifacts
MLFLOW_DEFAULT_ARTIFACT_ROOT={base_dir}/artifacts

# Configuration serveur
MLFLOW_HOST=0.0.0.0
MLFLOW_PORT=5000

# Sécurité (à configurer en production)
# MLFLOW_AUTH_LDAP_ENABLED=false
# MLFLOW_AUTH_SESSION_TIMEOUT=3600
"""
    
    with open(env_file, "w") as f:
        f.write(env_content)
    
    print(f"📄 Fichier de configuration créé : {env_file}")

def create_initial_admin(python_path):
    """Crée l'utilisateur admin initial"""
    
    script_content = '''
import os
import sys
from pathlib import Path

# Configuration de l'environnement
os.environ["MLFLOW_AUTH_ENABLED"] = "true"
base_dir = Path(__file__).parent
os.environ["MLFLOW_BACKEND_STORE_URI"] = f"sqlite:///{base_dir}/data/mlflow.db"

try:
    from mlflow_auth.auth.models import Base, User
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Créer la base de données
    db_path = base_dir / "data" / "mlflow_auth.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    
    # Créer la session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Vérifier si un admin existe déjà
    existing_admin = session.query(User).filter_by(role="admin").first()
    
    if not existing_admin:
        # Créer l'admin initial
        admin = User(
            username="admin",
            email="admin@mlflow.local",
            role="admin",
            is_active=True
        )
        admin.set_password("admin123")
        
        session.add(admin)
        session.commit()
        
        print("👤 Utilisateur admin créé :")
        print("   Username: admin")
        print("   Password: admin123")
        print("   ⚠️  CHANGEZ LE MOT DE PASSE lors de la première connexion !")
    else:
        print("👤 Utilisateur admin existant trouvé")
    
    session.close()
    
except Exception as e:
    print(f"❌ Erreur création admin : {e}")
    sys.exit(1)
'''
    
    # Écrire et exécuter le script
    script_path = Path(__file__).parent / "create_admin_temp.py"
    with open(script_path, "w") as f:
        f.write(script_content)
    
    try:
        result = subprocess.run([python_path, str(script_path)], 
                              capture_output=True, text=True, cwd=Path(__file__).parent)
        
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"❌ Erreur création admin : {result.stderr}")
    finally:
        # Nettoyer le script temporaire
        script_path.unlink(missing_ok=True)

def main():
    """Fonction principale de configuration"""
    
    print("🔧 Configuration de l'environnement MLflow avec authentification")
    print("=" * 60)
    
    try:
        # 1. Créer l'environnement virtuel
        venv_path = create_virtual_environment()
        python_path, pip_path = get_venv_paths(venv_path)
        
        # 2. Installer les dépendances
        if not install_requirements(pip_path):
            return False
        
        # 3. Installer le plugin d'authentification
        if not install_auth_plugin(pip_path):
            return False
        
        # 4. Créer les répertoires
        create_directories()
        
        # 5. Créer le fichier de configuration
        create_env_file()
        
        # 6. Créer l'admin initial
        create_initial_admin(python_path)
        
        print("\n" + "=" * 60)
        print("✅ Configuration terminée avec succès !")
        print("\n🚀 Pour démarrer MLflow :")
        
        if os.name == 'nt':
            print("   venv\\Scripts\\activate")
        else:
            print("   source venv/bin/activate")
        
        print("   python start_mlflow.py")
        print("\n🌐 Accès :")
        print("   - Interface MLflow : http://localhost:5000")
        print("   - Administration : http://localhost:5000/admin/users")
        print("   - Login initial : admin / admin123")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur lors de la configuration : {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
