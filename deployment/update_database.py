#!/usr/bin/env python3
"""
Script pour mettre à jour la base de données avec les nouvelles tables
"""

import sys
from pathlib import Path

# Ajouter le chemin du plugin
sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from mlflow_auth.auth.models import Base, User, LoginHistory

def update_database():
    """Met à jour la base de données avec les nouvelles tables"""
    
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "mlflow_auth.db"
    
    print(f"📊 Mise à jour de la base : {db_path}")
    
    # Créer le répertoire si nécessaire
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connexion à la base
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Créer toutes les tables (nouvelles et existantes)
    print("🔄 Création/mise à jour des tables...")
    Base.metadata.create_all(engine)
    
    print("✅ Base de données mise à jour avec succès !")
    print("📋 Tables disponibles :")
    print("   - mlflow_users (utilisateurs)")
    print("   - login_history (historique des connexions)")

def main():
    print("🔧 Mise à jour de la base de données MLflow Auth")
    print("=" * 50)
    update_database()

if __name__ == "__main__":
    main()