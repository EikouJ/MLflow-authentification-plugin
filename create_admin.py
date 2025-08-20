#!/usr/bin/env python3
"""
Script pour créer ou réinitialiser l'utilisateur admin
"""

import sys
from pathlib import Path

# Ajouter le chemin du plugin
sys.path.insert(0, str(Path(__file__).parent / "mlflow-auth-plugin"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from mlflow_auth.auth.models import Base, User

def create_admin():
    """Crée ou réinitialise l'utilisateur admin"""
    
    # Chemin vers la base de données
    base_dir = Path(__file__).parent / "deployment"
    db_path = base_dir / "data" / "mlflow_auth.db"
    
    # Créer le répertoire si nécessaire
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"📊 Base de données : {db_path}")
    
    # Connexion à la base
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)  # Créer les tables si elles n'existent pas
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Chercher l'admin existant
        admin = session.query(User).filter_by(username="admin").first()
        
        if admin:
            print("👤 Utilisateur admin existant trouvé")
            print("🔄 Réinitialisation du mot de passe...")
            
            # Réinitialiser le mot de passe
            admin.set_password("admin123")
            admin.is_active = True
            admin.role = "admin"
            
        else:
            print("👤 Création de l'utilisateur admin...")
            
            # Créer le nouvel admin
            admin = User(
                username="admin",
                email="admin@mlflow.local",
                role="admin",
                is_active=True
            )
            admin.set_password("admin123")
            session.add(admin)
        
        # Sauvegarder
        session.commit()
        
        # Vérifier que ça marche
        if admin.check_password("admin123"):
            print("✅ Admin créé/réinitialisé avec succès")
            print("🔑 Identifiants :")
            print("   Username: admin")
            print("   Password: admin123")
        else:
            print("❌ Erreur : le mot de passe ne fonctionne pas")
            
    except Exception as e:
        print(f"❌ Erreur : {e}")
        session.rollback()
    
    finally:
        session.close()

def main():
    print("🔧 Création/Réinitialisation de l'admin MLflow")
    print("=" * 45)
    create_admin()

if __name__ == "__main__":
    main()