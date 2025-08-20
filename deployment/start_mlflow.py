#!/usr/bin/env python3
"""
Script de démarrage MLflow avec authentification avancée
- Session timeout (10 minutes)
- Dashboard admin pour gestion des utilisateurs
- Historique des connexions
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from flask import Flask, request, redirect, url_for, session, render_template_string, jsonify, flash
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
import threading
import time
import subprocess
from werkzeug.serving import make_server
from datetime import datetime, timedelta

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration des sessions (10 minutes)
SESSION_TIMEOUT_MINUTES = 10

def load_environment():
    """Charge les variables d'environnement depuis .env"""
    
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        print("📄 Chargement de la configuration depuis .env")
        
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    else:
        print("⚠️  Fichier .env non trouvé, utilisation des valeurs par défaut")

def start_mlflow_backend():
    """Démarre MLflow en arrière-plan sur un port interne"""
    
    backend_port = 5001
    
    cmd = [
        sys.executable, "-m", "mlflow", "server",
        "--host", "127.0.0.1",
        "--port", str(backend_port),
        "--serve-artifacts"
    ]
    
    print(f"🚀 Démarrage MLflow backend sur le port {backend_port}...")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    import requests
    for i in range(30):
        try:
            response = requests.get(f"http://127.0.0.1:{backend_port}/health")
            if response.status_code == 200:
                print("✅ MLflow backend démarré")
                return process, backend_port
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    
    print("❌ Échec du démarrage de MLflow")
    return None, None

def create_auth_app():
    """Crée l'application Flask avec authentification avancée"""
    
    app = Flask(__name__)
    app.secret_key = os.getenv('MLFLOW_AUTH_SECRET_KEY', 'dev-secret-key')
    
    # Configuration des sessions
    app.permanent_session_lifetime = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    
    # Configuration de la base de données
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "mlflow_auth.db"
    db_path.parent.mkdir(exist_ok=True)
    
    # Initialiser la base de données
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))
        from mlflow_auth.auth.models import Base, User, LoginHistory
        
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        
        app.auth_db_session = Session
        
    except ImportError as e:
        print(f"❌ Erreur import plugin : {e}")
        return None
    
    # Configuration Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.session_protection = 'strong'
    
    @login_manager.user_loader
    def load_user(user_id):
        db_session = app.auth_db_session()
        try:
            return db_session.query(User).get(int(user_id))
        finally:
            db_session.close()
    
    # Middleware pour vérifier le timeout des sessions
    @app.before_request
    def check_session_timeout():
        # Ignorer pour les routes publiques
        if request.endpoint in ['login', 'static']:
            return
            
        if current_user.is_authenticated:
            # Vérifier le timeout
            last_activity = session.get('last_activity')
            if last_activity:
                last_activity = datetime.fromisoformat(last_activity)
                if datetime.now() - last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                    logout_user()
                    session.clear()
                    flash('Session expirée. Veuillez vous reconnecter.', 'warning')
                    return redirect(url_for('login'))
            
            # Mettre à jour la dernière activité
            session['last_activity'] = datetime.now().isoformat()
            session.permanent = True
    
    # Route de connexion
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            db_session = app.auth_db_session()
            try:
                user = db_session.query(User).filter_by(
                    username=username, 
                    is_active=True
                ).first()
                
                if user and user.check_password(password):
                    login_user(user, remember=False)
                    
                    # Enregistrer la connexion dans l'historique
                    user.record_login(
                        db_session,
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get('User-Agent', 'Unknown')
                    )
                    db_session.commit()
                    
                    # Initialiser la session
                    session['last_activity'] = datetime.now().isoformat()
                    session.permanent = True
                    
                    logger.info(f"✅ Connexion réussie : {username} depuis {request.remote_addr}")
                    return redirect('/')
                
                logger.warning(f"🚫 Échec connexion : {username} depuis {request.remote_addr}")
                return render_template_string(LOGIN_TEMPLATE, error="Identifiants incorrects")
            finally:
                db_session.close()
        
        return render_template_string(LOGIN_TEMPLATE)
    
    @app.route('/logout')
    @login_required
    def logout():
        # Enregistrer la déconnexion
        if current_user.is_authenticated:
            db_session = app.auth_db_session()
            try:
                # Trouver la dernière session
                last_login = db_session.query(LoginHistory)\
                    .filter_by(user_id=current_user.id, logout_time=None)\
                    .order_by(LoginHistory.login_time.desc())\
                    .first()
                
                if last_login:
                    last_login.record_logout()
                    db_session.commit()
                    
            except Exception as e:
                logger.error(f"Erreur enregistrement déconnexion : {e}")
            finally:
                db_session.close()
        
        logout_user()
        session.clear()
        flash('Vous avez été déconnecté.', 'info')
        return redirect(url_for('login'))
    
    # Dashboard admin
    @app.route('/admin')
    @login_required
    def admin_dashboard():
        if current_user.role != 'admin':
            flash('Accès refusé - Droits administrateur requis', 'error')
            return redirect('/')
        
        return render_template_string(ADMIN_DASHBOARD_TEMPLATE)
    
    # API pour gestion des utilisateurs
    @app.route('/admin/api/users', methods=['GET'])
    @login_required
    def api_get_users():
        if current_user.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        
        db_session = app.auth_db_session()
        try:
            users = db_session.query(User).all()
            return jsonify([user.to_dict() for user in users])
        finally:
            db_session.close()
    
    @app.route('/admin/api/users', methods=['POST'])
    @login_required
    def api_create_user():
        if current_user.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        
        data = request.get_json()
        
        db_session = app.auth_db_session()
        try:
            # Vérifier que l'utilisateur n'existe pas
            existing = db_session.query(User).filter(
                (User.username == data['username']) |
                (User.email == data['email'])
            ).first()
            
            if existing:
                return jsonify({'error': 'Utilisateur ou email déjà existant'}), 400
            
            # Créer l'utilisateur
            user = User(
                username=data['username'],
                email=data['email'],
                role=data.get('role', 'user'),
                is_active=data.get('is_active', True)
            )
            user.set_password(data['password'])
            
            db_session.add(user)
            db_session.commit()
            
            logger.info(f"👤 Utilisateur créé par {current_user.username} : {user.username}")
            return jsonify({'message': 'Utilisateur créé avec succès', 'user': user.to_dict()})
            
        except Exception as e:
            db_session.rollback()
            logger.error(f"Erreur création utilisateur : {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            db_session.close()
    
    @app.route('/admin/api/users/<int:user_id>', methods=['PUT'])
    @login_required
    def api_update_user(user_id):
        if current_user.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        
        data = request.get_json()
        
        db_session = app.auth_db_session()
        try:
            user = db_session.query(User).get(user_id)
            if not user:
                return jsonify({'error': 'Utilisateur non trouvé'}), 404
            
            # Mise à jour
            if 'username' in data:
                user.username = data['username']
            if 'email' in data:
                user.email = data['email']
            if 'role' in data:
                user.role = data['role']
            if 'is_active' in data:
                user.is_active = data['is_active']
            if 'password' in data and data['password']:
                user.set_password(data['password'])
            
            db_session.commit()
            
            logger.info(f"👤 Utilisateur modifié par {current_user.username} : {user.username}")
            return jsonify({'message': 'Utilisateur mis à jour', 'user': user.to_dict()})
            
        except Exception as e:
            db_session.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            db_session.close()
    
    @app.route('/admin/api/users/<int:user_id>', methods=['DELETE'])
    @login_required
    def api_delete_user(user_id):
        if current_user.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        
        if user_id == current_user.id:
            return jsonify({'error': 'Impossible de supprimer votre propre compte'}), 400
        
        db_session = app.auth_db_session()
        try:
            user = db_session.query(User).get(user_id)
            if not user:
                return jsonify({'error': 'Utilisateur non trouvé'}), 404
            
            username = user.username
            db_session.delete(user)
            db_session.commit()
            
            logger.info(f"🗑️ Utilisateur supprimé par {current_user.username} : {username}")
            return jsonify({'message': f'Utilisateur {username} supprimé'})
            
        except Exception as e:
            db_session.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            db_session.close()
    
    # API pour l'historique des connexions
    @app.route('/admin/api/login-history')
    @login_required
    def api_login_history():
        if current_user.role != 'admin':
            return jsonify({'error': 'Accès refusé'}), 403
        
        db_session = app.auth_db_session()
        try:
            limit = request.args.get('limit', 100, type=int)
            
            history = db_session.query(LoginHistory)\
                .order_by(LoginHistory.login_time.desc())\
                .limit(limit).all()
            
            return jsonify([record.to_dict() for record in history])
        finally:
            db_session.close()
    
    # Proxy vers MLflow
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    @login_required
    def proxy_to_mlflow(path):
        # Rediriger vers admin si c'est un admin et pas de path spécifique
        if not path and current_user.role == 'admin':
            return redirect('/admin')
        
        import requests
        
        backend_url = f"http://127.0.0.1:5001/{path}"
        
        # Forwarding de la requête
        if request.method == 'GET':
            response = requests.get(backend_url, params=request.args, 
                                  headers=dict(request.headers))
        elif request.method == 'POST':
            response = requests.post(backend_url, data=request.get_data(), 
                                   headers=dict(request.headers))
        else:
            response = requests.request(request.method, backend_url, 
                                      data=request.get_data(), 
                                      headers=dict(request.headers))
        
        # Retourner la réponse
        from flask import Response
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    
    return app

# Template de login avec indicateur de timeout
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MLflow - Connexion</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 40px; background: #f5f5f5; }
        .login-form { max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="password"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        .btn { background: #007bff; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
        .btn:hover { background: #0056b3; }
        .error { color: red; margin-top: 10px; }
        .info { color: #666; font-size: 12px; margin-top: 20px; text-align: center; }
        .header { text-align: center; margin-bottom: 30px; }
        .timeout-info { background: #e7f3ff; padding: 10px; border-radius: 4px; margin-bottom: 20px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="login-form">
        <div class="header">
            <h2>🔐 MLflow</h2>
            <p>Authentification requise</p>
        </div>
        
        <div class="timeout-info">
            ⏰ <strong>Session :</strong> 10 minutes d'inactivité maximum
        </div>
        
        <form method="POST">
            <div class="form-group">
                <label>Nom d'utilisateur:</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Mot de passe:</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">Se connecter</button>
            {% if error %}
                <div class="error">{{ error }}</div>
            {% endif %}
        </form>
        <div class="info">
            Login par défaut : admin / admin123
        </div>
    </div>
</body>
</html>
"""

# Template du dashboard admin
ADMIN_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard Admin - MLflow</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #f5f5f5; }
        .navbar { background: #343a40; color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .navbar h1 { margin: 0; }
        .user-info { font-size: 14px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .card h2 { margin-top: 0; color: #343a40; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px; }
        .btn-primary { background: #007bff; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn:hover { opacity: 0.9; }
        .table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        .table th { background: #f8f9fa; font-weight: bold; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
        .modal-content { background: white; margin: 50px auto; padding: 20px; width: 500px; border-radius: 8px; }
        .close { float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
        .status { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        .status.active { background: #d4edda; color: #155724; }
        .status.inactive { background: #f8d7da; color: #721c24; }
        .tabs { display: flex; border-bottom: 1px solid #ddd; margin-bottom: 20px; }
        .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent; }
        .tab.active { border-bottom-color: #007bff; color: #007bff; font-weight: bold; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; margin-bottom: 5px; }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>🛡️ Dashboard Admin MLflow</h1>
        <div class="user-info">
            👤 {{ current_user.username }} | 
            <a href="/" style="color: white;">MLflow</a> | 
            <a href="/logout" style="color: white;">Déconnexion</a>
        </div>
    </div>
    
    <div class="container">
        <div class="stats" id="stats">
            <!-- Les statistiques seront chargées ici -->
        </div>
        
        <div class="card">
            <div class="tabs">
                <div class="tab active" onclick="switchTab('users')">👥 Utilisateurs</div>
                <div class="tab" onclick="switchTab('history')">📊 Historique des connexions</div>
            </div>
            
            <div id="tab-users" class="tab-content active">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h2>Gestion des utilisateurs</h2>
                    <button class="btn btn-success" onclick="showCreateUserModal()">+ Nouvel utilisateur</button>
                </div>
                
                <table class="table" id="usersTable">
                    <thead>
                        <tr>
                            <th>Nom d'utilisateur</th>
                            <th>Email</th>
                            <th>Rôle</th>
                            <th>Statut</th>
                            <th>Dernière connexion</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Les utilisateurs seront chargés ici -->
                    </tbody>
                </table>
            </div>
            
            <div id="tab-history" class="tab-content">
                <h2>Historique des connexions</h2>
                <table class="table" id="historyTable">
                    <thead>
                        <tr>
                            <th>Utilisateur</th>
                            <th>Adresse IP</th>
                            <th>Connexion</th>
                            <th>Déconnexion</th>
                            <th>Durée</th>
                            <th>Navigateur</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- L'historique sera chargé ici -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <!-- Modal pour créer/modifier un utilisateur -->
    <div id="userModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeUserModal()">&times;</span>
            <h2 id="modalTitle">Créer un utilisateur</h2>
            <form id="userForm">
                <div class="form-group">
                    <label>Rôle:</label>
                    <select id="role" required>
                        <option value="viewer">Visualiseur</option>
                        <option value="user">Utilisateur</option>
                        <option value="admin">Administrateur</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="is_active" checked> Compte actif
                    </label>
                </div>
                <div style="text-align: right;">
                    <button type="button" class="btn" onclick="closeUserModal()" style="background: #6c757d; color: white;">Annuler</button>
                    <button type="submit" class="btn btn-primary">Enregistrer</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        let currentUserId = null;
        
        // Chargement initial
        document.addEventListener('DOMContentLoaded', function() {
            loadStats();
            loadUsers();
            loadHistory();
            
            // Actualisation automatique toutes les 30 secondes
            setInterval(() => {
                loadStats();
                if (document.getElementById('tab-users').classList.contains('active')) {
                    loadUsers();
                }
                if (document.getElementById('tab-history').classList.contains('active')) {
                    loadHistory();
                }
            }, 30000);
        });
        
        // Gestion des onglets
        function switchTab(tabName) {
            // Désactiver tous les onglets
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            // Activer l'onglet sélectionné
            event.target.classList.add('active');
            document.getElementById('tab-' + tabName).classList.add('active');
            
            // Charger les données si nécessaire
            if (tabName === 'history') {
                loadHistory();
            }
        }
        
        // Charger les statistiques
        async function loadStats() {
            try {
                const response = await fetch('/admin/api/users');
                const users = await response.json();
                
                const totalUsers = users.length;
                const activeUsers = users.filter(u => u.is_active).length;
                const adminUsers = users.filter(u => u.role === 'admin').length;
                const recentLogins = users.filter(u => {
                    if (!u.last_login) return false;
                    const lastLogin = new Date(u.last_login);
                    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
                    return lastLogin > oneDayAgo;
                }).length;
                
                document.getElementById('stats').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-number">${totalUsers}</div>
                        <div>Total Utilisateurs</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${activeUsers}</div>
                        <div>Comptes Actifs</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${adminUsers}</div>
                        <div>Administrateurs</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${recentLogins}</div>
                        <div>Connexions 24h</div>
                    </div>
                `;
            } catch (error) {
                console.error('Erreur chargement stats:', error);
            }
        }
        
        // Charger la liste des utilisateurs
        async function loadUsers() {
            try {
                const response = await fetch('/admin/api/users');
                const users = await response.json();
                
                const tbody = document.querySelector('#usersTable tbody');
                tbody.innerHTML = users.map(user => `
                    <tr>
                        <td>${user.username}</td>
                        <td>${user.email}</td>
                        <td>
                            <span class="status ${user.role === 'admin' ? 'active' : ''}" 
                                  style="background: ${getRoleColor(user.role)};">
                                ${getRoleLabel(user.role)}
                            </span>
                        </td>
                        <td>
                            <span class="status ${user.is_active ? 'active' : 'inactive'}">
                                ${user.is_active ? 'Actif' : 'Inactif'}
                            </span>
                        </td>
                        <td>${user.last_login ? formatDate(user.last_login) : 'Jamais'}</td>
                        <td>
                            <button class="btn btn-primary" onclick="editUser(${user.id})" style="font-size: 12px; padding: 4px 8px;">
                                ✏️ Modifier
                            </button>
                            ${user.id !== {{ current_user.id }} ? `
                                <button class="btn btn-danger" onclick="deleteUser(${user.id}, '${user.username}')" 
                                        style="font-size: 12px; padding: 4px 8px;">
                                    🗑️ Supprimer
                                </button>
                            ` : ''}
                        </td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error('Erreur chargement utilisateurs:', error);
            }
        }
        
        // Charger l'historique des connexions
        async function loadHistory() {
            try {
                const response = await fetch('/admin/api/login-history?limit=50');
                const history = await response.json();
                
                const tbody = document.querySelector('#historyTable tbody');
                tbody.innerHTML = history.map(record => `
                    <tr>
                        <td>${record.username}</td>
                        <td>${record.ip_address}</td>
                        <td>${formatDate(record.login_time)}</td>
                        <td>${record.logout_time ? formatDate(record.logout_time) : '🟢 En cours'}</td>
                        <td>${record.session_duration ? formatDuration(record.session_duration) : '-'}</td>
                        <td title="${record.user_agent}">${truncateUserAgent(record.user_agent)}</td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error('Erreur chargement historique:', error);
            }
        }
        
        // Afficher le modal de création d'utilisateur
        function showCreateUserModal() {
            currentUserId = null;
            document.getElementById('modalTitle').textContent = 'Créer un utilisateur';
            document.getElementById('userForm').reset();
            document.getElementById('is_active').checked = true;
            document.getElementById('passwordHelp').style.display = 'none';
            document.getElementById('userModal').style.display = 'block';
        }
        
        // Modifier un utilisateur
        async function editUser(userId) {
            try {
                const response = await fetch('/admin/api/users');
                const users = await response.json();
                const user = users.find(u => u.id === userId);
                
                if (user) {
                    currentUserId = userId;
                    document.getElementById('modalTitle').textContent = 'Modifier l\'utilisateur';
                    document.getElementById('username').value = user.username;
                    document.getElementById('email').value = user.email;
                    document.getElementById('password').value = '';
                    document.getElementById('role').value = user.role;
                    document.getElementById('is_active').checked = user.is_active;
                    document.getElementById('passwordHelp').style.display = 'block';
                    document.getElementById('userModal').style.display = 'block';
                }
            } catch (error) {
                console.error('Erreur chargement utilisateur:', error);
            }
        }
        
        // Supprimer un utilisateur
        async function deleteUser(userId, username) {
            if (confirm(`Êtes-vous sûr de vouloir supprimer l'utilisateur "${username}" ?`)) {
                try {
                    const response = await fetch(`/admin/api/users/${userId}`, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        alert('Utilisateur supprimé avec succès');
                        loadUsers();
                        loadStats();
                    } else {
                        const error = await response.json();
                        alert('Erreur: ' + error.error);
                    }
                } catch (error) {
                    console.error('Erreur suppression:', error);
                    alert('Erreur lors de la suppression');
                }
            }
        }
        
        // Fermer le modal
        function closeUserModal() {
            document.getElementById('userModal').style.display = 'none';
        }
        
        // Soumission du formulaire utilisateur
        document.getElementById('userForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = {
                username: document.getElementById('username').value,
                email: document.getElementById('email').value,
                role: document.getElementById('role').value,
                is_active: document.getElementById('is_active').checked
            };
            
            const password = document.getElementById('password').value;
            if (password) {
                formData.password = password;
            }
            
            try {
                let response;
                if (currentUserId) {
                    // Modification
                    response = await fetch(`/admin/api/users/${currentUserId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });
                } else {
                    // Création
                    if (!password) {
                        alert('Le mot de passe est requis pour créer un utilisateur');
                        return;
                    }
                    response = await fetch('/admin/api/users', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });
                }
                
                if (response.ok) {
                    alert(currentUserId ? 'Utilisateur modifié avec succès' : 'Utilisateur créé avec succès');
                    closeUserModal();
                    loadUsers();
                    loadStats();
                } else {
                    const error = await response.json();
                    alert('Erreur: ' + error.error);
                }
            } catch (error) {
                console.error('Erreur sauvegarde:', error);
                alert('Erreur lors de la sauvegarde');
            }
        });
        
        // Fonctions utilitaires
        function getRoleColor(role) {
            const colors = {
                'admin': '#dc3545',
                'user': '#28a745', 
                'viewer': '#6c757d'
            };
            return colors[role] || '#6c757d';
        }
        
        function getRoleLabel(role) {
            const labels = {
                'admin': 'Administrateur',
                'user': 'Utilisateur',
                'viewer': 'Visualiseur'
            };
            return labels[role] || role;
        }
        
        function formatDate(dateString) {
            if (!dateString) return '-';
            const date = new Date(dateString);
            return date.toLocaleString('fr-FR');
        }
        
        function formatDuration(seconds) {
            if (!seconds) return '-';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            
            if (hours > 0) {
                return `${hours}h ${minutes}m`;
            } else if (minutes > 0) {
                return `${minutes}m ${secs}s`;
            } else {
                return `${secs}s`;
            }
        }
        
        function truncateUserAgent(userAgent) {
            if (!userAgent) return 'Inconnu';
            if (userAgent.includes('Chrome')) return '🌐 Chrome';
            if (userAgent.includes('Firefox')) return '🦊 Firefox';
            if (userAgent.includes('Safari')) return '🧭 Safari';
            if (userAgent.includes('Edge')) return '🔷 Edge';
            return '🌐 Autre';
        }
        
        // Fermer le modal en cliquant à l'extérieur
        window.onclick = function(event) {
            const modal = document.getElementById('userModal');
            if (event.target === modal) {
                closeUserModal();
            }
        }
    </script>
</body>
</html>
"""

def create_admin_user():
    """Crée l'utilisateur admin s'il n'existe pas"""
    
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "mlflow_auth.db"
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))
        from mlflow_auth.auth.models import Base, User
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        existing_admin = session.query(User).filter_by(role="admin").first()
        
        if not existing_admin:
            admin = User(
                username="admin",
                email="admin@mlflow.local", 
                role="admin",
                is_active=True
            )
            admin.set_password("admin123")
            session.add(admin)
            session.commit()
            print("👤 Admin créé : admin / admin123")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Erreur création admin : {e}")

def main():
    """Fonction principale"""
    
    parser = argparse.ArgumentParser(description='Démarrer MLflow avec authentification avancée')
    parser.add_argument('--host', default='0.0.0.0', help='Host du serveur')
    parser.add_argument('--port', type=int, default=5000, help='Port du serveur')
    parser.add_argument('--no-auth', action='store_true', help='Désactiver l\'authentification')
    
    args = parser.parse_args()
    
    load_environment()
    
    if args.no_auth:
        print("⚠️  Démarrage de MLflow SANS authentification")
        cmd = [sys.executable, "-m", "mlflow", "server", 
               "--host", args.host, "--port", str(args.port)]
        subprocess.run(cmd)
        return
    
    print("🔐 Démarrage de MLflow AVEC authentification avancée")
    print("=" * 55)
    print(f"⏰ Timeout de session : {SESSION_TIMEOUT_MINUTES} minutes")
    print("🛡️  Dashboard admin intégré")
    print("📊 Historique des connexions")
    
    create_admin_user()
    
    mlflow_process, backend_port = start_mlflow_backend()
    if not mlflow_process:
        return False
    
    try:
        app = create_auth_app()
        if not app:
            return False
        
        print(f"\n🌐 Interface avec authentification : http://{args.host}:{args.port}")
        print(f"🛡️  Dashboard admin : http://{args.host}:{args.port}/admin")
        print("🔑 Login : admin / admin123")
        print("   (Ctrl+C pour arrêter)")
        
        app.run(host=args.host, port=args.port, debug=False)
        
    except KeyboardInterrupt:
        print("\n👋 Arrêt du serveur")
    finally:
        if mlflow_process:
            mlflow_process.terminate()
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)