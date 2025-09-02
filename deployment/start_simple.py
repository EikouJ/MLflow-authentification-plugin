#!/usr/bin/env python3
"""
Version simplifiée et robuste de start_mlflow.py
"""

import os
import sys
import argparse
import logging
import subprocess
import time
from pathlib import Path

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_dependencies():
    """Vérifier les dépendances critiques"""
    missing = []
    
    try:
        import flask
        logger.info("✅ Flask disponible")
    except ImportError:
        missing.append("flask")
    
    try:
        import flask_login
        logger.info("✅ Flask-Login disponible")
    except ImportError:
        missing.append("flask-login")
    
    try:
        import requests
        logger.info("✅ Requests disponible")
    except ImportError:
        missing.append("requests")
    
    try:
        import sqlalchemy
        logger.info("✅ SQLAlchemy disponible")
    except ImportError:
        missing.append("sqlalchemy")
    
    if missing:
        logger.error(f"❌ Dépendances manquantes: {', '.join(missing)}")
        logger.error("Installez avec: pip install " + " ".join(missing))
        return False
    
    return True

def start_mlflow_backend(port=5001):
    """Démarre MLflow en arrière-plan"""
    
    cmd = [
        sys.executable, "-m", "mlflow", "server",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--serve-artifacts"
    ]
    
    logger.info(f"🚀 Démarrage MLflow backend sur le port {port}...")
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Attendre que MLflow soit prêt
        import requests
        for i in range(30):
            try:
                response = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
                if response.status_code == 200:
                    logger.info("✅ MLflow backend démarré")
                    return process, port
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
            
        logger.error("❌ Timeout - MLflow backend n'a pas démarré")
        process.terminate()
        return None, None
        
    except Exception as e:
        logger.error(f"❌ Erreur démarrage MLflow: {e}")
        return None, None

def create_basic_auth_app(backend_port):
    """Crée une application Flask avec authentification basique"""
    
    from flask import Flask, request, redirect, url_for, session, jsonify, render_template_string
    from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
    
    app = Flask(__name__)
    app.secret_key = 'mlflow-auth-secret-key-2024'
    
    # Utilisateurs par défaut
    USERS = {
        'admin': 'admin123'
    }
    
    # Configuration Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    class User(UserMixin):
        def __init__(self, username):
            self.id = username
            self.username = username
    
    @login_manager.user_loader
    def load_user(user_id):
        return User(user_id) if user_id in USERS else None
    
    # Template de login inline
    LOGIN_TEMPLATE = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>MLflow - Connexion</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 50px; }
            .container { max-width: 400px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }
            h1 { text-align: center; color: #333; margin-bottom: 30px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; color: #555; }
            input[type="text"], input[type="password"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
            button:hover { background: #0056b3; }
            .error { color: red; text-align: center; margin-bottom: 20px; }
            .info { text-align: center; margin-top: 20px; font-size: 12px; color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 MLflow</h1>
            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}
            <form method="post">
                <div class="form-group">
                    <label>Nom d'utilisateur:</label>
                    <input type="text" name="username" required autofocus>
                </div>
                <div class="form-group">
                    <label>Mot de passe:</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">Se connecter</button>
            </form>
            <div class="info">
                Défaut: admin / admin123
            </div>
        </div>
    </body>
    </html>
    '''
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            if username in USERS and USERS[username] == password:
                user = User(username)
                login_user(user)
                logger.info(f"✅ Connexion réussie: {username}")
                
                next_page = request.args.get('next')
                return redirect(next_page or '/')
            else:
                error = "Identifiants incorrects"
                logger.warning(f"❌ Échec connexion: {username}")
        
        return render_template_string(LOGIN_TEMPLATE, error=error)
    
    @app.route('/logout')
    @login_required
    def logout():
        logger.info(f"👋 Déconnexion: {current_user.username}")
        logout_user()
        return redirect(url_for('login'))
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'backend': f'http://127.0.0.1:{backend_port}'})
    
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    @login_required
    def proxy_to_mlflow(path):
        import requests
        
        backend_url = f"http://127.0.0.1:{backend_port}/{path}"
        
        try:
            # Proxy vers MLflow
            if request.method == 'GET':
                response = requests.get(
                    backend_url, 
                    params=request.args, 
                    headers=dict(request.headers),
                    timeout=30
                )
            elif request.method == 'POST':
                response = requests.post(
                    backend_url, 
                    data=request.get_data(), 
                    headers=dict(request.headers),
                    timeout=30
                )
            else:
                response = requests.request(
                    request.method, 
                    backend_url, 
                    data=request.get_data(), 
                    headers=dict(request.headers),
                    timeout=30
                )
            
            from flask import Response
            return Response(
                response.content,
                status=response.status_code,
                headers=dict(response.headers)
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur proxy: {e}")
            return f"Erreur de connexion au backend MLflow: {e}", 502
    
    return app

def main():
    """Fonction principale"""
    
    print("🔐 MLflow avec Authentification Simplifiée")
    print("=" * 50)
    
    parser = argparse.ArgumentParser(description='Démarrer MLflow avec authentification')
    parser.add_argument('--host', default='0.0.0.0', help='Host du serveur')
    parser.add_argument('--port', type=int, default=5000, help='Port du serveur')
    parser.add_argument('--no-auth', action='store_true', help='Désactiver l\'authentification')
    parser.add_argument('--backend-port', type=int, default=5001, help='Port MLflow backend')
    
    try:
        args = parser.parse_args()
    except SystemExit:
        return 1
    
    # Vérifier les dépendances
    if not check_dependencies():
        return 1
    
    # Mode sans authentification
    if args.no_auth:
        logger.info("⚠️ Démarrage MLflow SANS authentification")
        cmd = [
            sys.executable, "-m", "mlflow", "server",
            "--host", args.host,
            "--port", str(args.port),
            "--serve-artifacts"
        ]
        subprocess.run(cmd)
        return 0
    
    # Démarrer MLflow backend
    mlflow_process, backend_port = start_mlflow_backend(args.backend_port)
    if not mlflow_process:
        logger.error("❌ Impossible de démarrer MLflow backend")
        return 1
    
    try:
        # Créer l'application d'authentification
        app = create_basic_auth_app(backend_port)
        
        logger.info(f"🌐 Interface avec authentification: http://{args.host}:{args.port}")
        logger.info(f"🔑 Login par défaut: admin / admin123")
        logger.info("   (Ctrl+C pour arrêter)")
        
        # Démarrer le serveur
        app.run(
            host=args.host,
            port=args.port,
            debug=False,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        logger.info("👋 Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur serveur: {e}")
        return 1
    finally:
        if mlflow_process:
            logger.info("🛑 Arrêt du backend MLflow")
            mlflow_process.terminate()
            mlflow_process.wait()
    
    return 0

if __name__ == '__main__':
    sys.exit(main())