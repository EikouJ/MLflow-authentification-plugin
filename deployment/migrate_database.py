#!/usr/bin/env python3
"""
Script de migration de la base de données MLflow Auth
Ajoute les nouvelles colonnes et fonctionnalités
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Ajouter le chemin vers le plugin
sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))

def migrate_database():
    """Migre la base de données existante"""
    
    try:
        from mlflow_auth.auth.models import Base, User, LoginHistory
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        # Chemin de la base de données
        base_dir = Path(__file__).parent
        db_path = base_dir / "data" / "mlflow_auth.db"
        
        if not db_path.exists():
            print("❌ Base de données non trouvée")
            return False
        
        print(f"🔄 Migration de la base de données: {db_path}")
        
        engine = create_engine(f"sqlite:///{db_path}")
        
        # Créer une sauvegarde
        backup_path = db_path.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"💾 Sauvegarde créée: {backup_path}")
        
        # Appliquer les migrations
        with engine.connect() as conn:
            try:
                # Vérifier et ajouter la colonne last_login si elle n'existe pas
                result = conn.execute(text("PRAGMA table_info(users)")).fetchall()
                columns = [row[1] for row in result]
                
                if 'last_login' not in columns:
                    print("➕ Ajout de la colonne last_login")
                    conn.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))
                
                # Vérifier et ajouter la colonne activity_type dans login_history
                result = conn.execute(text("PRAGMA table_info(login_history)")).fetchall()
                columns = [row[1] for row in result]
                
                if 'activity_type' not in columns:
                    print("➕ Ajout de la colonne activity_type")
                    conn.execute(text("ALTER TABLE login_history ADD COLUMN activity_type VARCHAR(10) DEFAULT 'login'"))
                    # Mettre à jour les enregistrements existants
                    conn.execute(text("UPDATE login_history SET activity_type = 'login' WHERE activity_type IS NULL"))
                
                conn.commit()
                print("✅ Migration réussie")
                
            except Exception as e:
                print(f"❌ Erreur during migration: {e}")
                conn.rollback()
                return False
        
        # Recréer toutes les tables pour s'assurer de la cohérence
        Base.metadata.create_all(engine)
        
        # Vérifier l'intégrité
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            users_count = session.query(User).count()
            history_count = session.query(LoginHistory).count()
            
            print(f"📊 Vérification post-migration:")
            print(f"   • Utilisateurs: {users_count}")
            print(f"   • Historique: {history_count}")
            
        finally:
            session.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la migration: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_test_data():
    """Crée des données de test pour la démonstration"""
    
    try:
        from mlflow_auth.auth.models import User, LoginHistory
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        base_dir = Path(__file__).parent
        db_path = base_dir / "data" / "mlflow_auth.db"
        
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Créer quelques utilisateurs de test
        test_users = [
            {
                'username': 'alice',
                'email': 'alice@example.com',
                'role': 'user',
                'password': 'password123'
            },
            {
                'username': 'bob',
                'email': 'bob@example.com',
                'role': 'user',
                'password': 'password123'
            },
            {
                'username': 'charlie',
                'email': 'charlie@example.com',
                'role': 'admin',
                'password': 'password123'
            }
        ]
        
        created_users = []
        for user_data in test_users:
            # Vérifier si l'utilisateur existe déjà
            existing = session.query(User).filter_by(username=user_data['username']).first()
            if not existing:
                user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    role=user_data['role'],
                    is_active=True
                )
                user.set_password(user_data['password'])
                session.add(user)
                created_users.append(user_data['username'])
        
        if created_users:
            session.commit()
            print(f"👤 Utilisateurs de test créés: {', '.join(created_users)}")
        else:
            print("👤 Utilisateurs de test déjà existants")
        
        # Créer quelques entrées d'historique fictives
        import random
        from datetime import datetime, timedelta
        
        users = session.query(User).all()
        for user in users:
            # Générer quelques connexions/déconnexions fictives
            for i in range(random.randint(3, 10)):
                login_time = datetime.now() - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                
                # Connexion
                login_entry = LoginHistory(
                    user_id=user.id,
                    login_time=login_time,
                    ip_address=f"192.168.1.{random.randint(1, 254)}",
                    user_agent="Mozilla/5.0 (Test Browser) TestKit/1.0",
                    activity_type="login"
                )
                session.add(login_entry)
                
                # Parfois ajouter une déconnexion
                if random.choice([True, False]):
                    logout_time = login_time + timedelta(
                        hours=random.randint(1, 8),
                        minutes=random.randint(0, 59)
                    )
                    logout_entry = LoginHistory(
                        user_id=user.id,
                        login_time=logout_time,
                        ip_address=f"192.168.1.{random.randint(1, 254)}",
                        user_agent="Mozilla/5.0 (Test Browser) TestKit/1.0",
                        activity_type="logout"
                    )
                    session.add(logout_entry)
        
        session.commit()
        print("📊 Données d'historique de test créées")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Erreur création données de test: {e}")
        return False

def main():
    """Fonction principale"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrer la base de données MLflow Auth')
    parser.add_argument('--create-test-data', action='store_true', 
                       help='Créer des données de test après migration')
    parser.add_argument('--force', action='store_true',
                       help='Forcer la migration même si elle semble déjà effectuée')
    
    args = parser.parse_args()
    
    print("🔄 Migration Base de Données MLflow Auth")
    print("=" * 40)
    
    # Vérifier que le plugin est disponible
    try:
        import mlflow_auth.auth.models
        print("✅ Plugin mlflow-auth trouvé")
    except ImportError:
        print("❌ Plugin mlflow-auth non trouvé")
        print("   Assurez-vous que le plugin est installé et dans le bon répertoire")
        return 1
    
    # Exécuter la migration
    if migrate_database():
        print("✅ Migration terminée avec succès")
        
        if args.create_test_data:
            print("\n📊 Création des données de test...")
            if create_test_data():
                print("✅ Données de test créées")
            else:
                print("❌ Erreur lors de la création des données de test")
    else:
        print("❌ Échec de la migration")
        return 1
    
    print("\n🎉 Migration complète!")
    print("   Vous pouvez maintenant utiliser start_mlflow_enhanced.py")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())