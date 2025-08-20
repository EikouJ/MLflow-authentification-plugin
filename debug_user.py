#!/usr/bin/env python3
"""
Script de diagnostic pour vérifier les utilisateurs dans la base
"""

import sys
from pathlib import Path

# Ajouter le chemin du plugin
sys.path.insert(0, str(Path(__file__).parent / "mlflow-auth-plugin"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from mlflow_auth.auth.models import Base, User

def main():
    # Chemin vers la base de données
    db_path = Path(__file__).parent / "deployment" / "data" / "mlflow_auth.db"
    
    if not db_path.exists():
        print("❌ Base de données non trouvée")
        print(f"Chemin recherché : {db_path}")
        return
    
    print(f"📊 Analyse de la base : {db_path}")
    
    # Connexion à la base
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Lister tous les utilisateurs
        users = session.query(User).all()
        
        if not users:
            print("❌ Aucun utilisateur trouvé dans la base")
        else:
            print(f"👥 {len(users)} utilisateur(s) trouvé(s) :")
            for user in users:
                print(f"   - ID: {user.id}")
                print(f"     Username: {user.username}")
                print(f"     Email: {user.email}")
                print(f"     Role: {user.role}")
                print(f"     Active: {user.is_active}")
                print(f"     Password hash: {user.password_hash[:50]}...")
                print()
        
        # Test du mot de passe admin
        admin = session.query(User).filter_by(username="admin").first()
        if admin:
            print("🔑 Test du mot de passe 'admin123' :")
            if admin.check_password("admin123"):
                print("   ✅ Mot de passe correct")
            else:
                print("   ❌ Mot de passe incorrect")
                
            # Essayer de réinitialiser le mot de passe
            print("🔄 Réinitialisation du mot de passe...")
            admin.set_password("admin123")
            session.commit()
            
            if admin.check_password("admin123"):
                print("   ✅ Mot de passe réinitialisé avec succès")
            else:
                print("   ❌ Échec de la réinitialisation")
        else:
            print("❌ Utilisateur 'admin' non trouvé")
    
    except Exception as e:
        print(f"❌ Erreur : {e}")
    
    finally:
        session.close()

if __name__ == "__main__":
    main()