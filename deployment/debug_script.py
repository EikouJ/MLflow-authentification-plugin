#!/usr/bin/env python3
"""
Script de diagnostic pour identifier les problèmes de start_mlflow.py
"""

import sys
import traceback
from pathlib import Path

def test_imports():
    """Test des imports"""
    print("🔍 Test des imports...")
    
    try:
        import os
        print("✅ os")
    except Exception as e:
        print(f"❌ os: {e}")
    
    try:
        import argparse
        print("✅ argparse")
    except Exception as e:
        print(f"❌ argparse: {e}")
    
    try:
        import logging
        print("✅ logging")
    except Exception as e:
        print(f"❌ logging: {e}")
    
    try:
        from flask import Flask
        print("✅ Flask")
    except Exception as e:
        print(f"❌ Flask: {e}")
    
    try:
        from flask_login import LoginManager
        print("✅ Flask-Login")
    except Exception as e:
        print(f"❌ Flask-Login: {e}")
    
    try:
        import requests
        print("✅ requests")
    except Exception as e:
        print(f"❌ requests: {e}")
    
    try:
        from sqlalchemy import create_engine
        print("✅ SQLAlchemy")
    except Exception as e:
        print(f"❌ SQLAlchemy: {e}")

def test_plugin_import():
    """Test de l'import du plugin MLflow"""
    print("\n🔍 Test du plugin MLflow...")
    
    try:
        plugin_path = Path(__file__).parent.parent / "mlflow-auth-plugin"
        sys.path.insert(0, str(plugin_path))
        
        from mlflow_auth.auth.models import Base, User, LoginHistory
        print("✅ Plugin MLflow importé avec succès")
        return True
    except ImportError as e:
        print(f"❌ Erreur import plugin: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue plugin: {e}")
        return False

def test_template_structure():
    """Test de la structure des templates"""
    print("\n🔍 Test de la structure des templates...")
    
    templates_dir = Path(__file__).parent / "templates"
    auth_dir = templates_dir / "auth"
    admin_dir = templates_dir / "admin"
    
    print(f"📁 Dossier templates: {templates_dir.exists()}")
    print(f"📁 Dossier auth: {auth_dir.exists()}")
    print(f"📁 Dossier admin: {admin_dir.exists()}")
    
    login_template = auth_dir / "login.html"
    change_pwd_template = auth_dir / "change_password.html"
    dashboard_template = admin_dir / "dashboard.html"
    
    print(f"📄 login.html: {login_template.exists()}")
    print(f"📄 change_password.html: {change_pwd_template.exists()}")
    print(f"📄 dashboard.html: {dashboard_template.exists()}")

def test_database():
    """Test de la base de données"""
    print("\n🔍 Test de la base de données...")
    
    db_path = Path(__file__).parent / "data" / "mlflow_auth.db"
    print(f"💾 Base de données existe: {db_path.exists()}")
    
    if db_path.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Lister les tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"📊 Tables: {[t[0] for t in tables]}")
            
            # Vérifier la table mlflow_users
            if ('mlflow_users',) in tables:
                cursor.execute("PRAGMA table_info(mlflow_users)")
                columns = cursor.fetchall()
                print(f"🏗️  Colonnes mlflow_users: {[c[1] for c in columns]}")
            
            conn.close()
            print("✅ Base de données accessible")
        except Exception as e:
            print(f"❌ Erreur base de données: {e}")

def test_start_mlflow_syntax():
    """Test de la syntaxe du script start_mlflow.py"""
    print("\n🔍 Test de syntaxe start_mlflow.py...")
    
    script_path = Path(__file__).parent / "start_mlflow.py"
    
    if not script_path.exists():
        print("❌ start_mlflow.py non trouvé")
        return
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Test de compilation
        compile(content, str(script_path), 'exec')
        print("✅ Syntaxe correcte")
        
    except SyntaxError as e:
        print(f"❌ Erreur de syntaxe: {e}")
        print(f"   Ligne {e.lineno}: {e.text}")
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")

def test_main_function():
    """Test d'exécution de la fonction main"""
    print("\n🔍 Test d'exécution de main()...")
    
    try:
        # Importer et tester la fonction main
        import start_mlflow
        print("✅ Module start_mlflow importé")
        
        # Test avec --help pour éviter le démarrage complet
        sys.argv = ['start_mlflow.py', '--help']
        
        try:
            start_mlflow.main()
        except SystemExit as e:
            if e.code in [0, 2]:  # 0 = succès, 2 = help affiché
                print("✅ Function main() accessible")
            else:
                print(f"⚠️  SystemExit avec code: {e.code}")
        
    except ImportError as e:
        print(f"❌ Erreur import start_mlflow: {e}")
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        traceback.print_exc()

def main():
    """Fonction principale de diagnostic"""
    print("🩺 DIAGNOSTIC MLflow Authentication")
    print("=" * 50)
    
    test_imports()
    test_plugin_import()
    test_template_structure()
    test_database()
    test_start_mlflow_syntax()
    test_main_function()
    
    print("\n" + "=" * 50)
    print("🩺 Diagnostic terminé")
    print("\n💡 Conseils:")
    print("   - Vérifiez les erreurs marquées ❌")
    print("   - Installez les dépendances manquantes")
    print("   - Créez les templates manquants")

if __name__ == '__main__':
    main()