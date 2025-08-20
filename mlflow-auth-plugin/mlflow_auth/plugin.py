import os
import logging
from flask import Flask, request, redirect, url_for, g
from flask_login import LoginManager, current_user
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthExtension:
    """Extension principale qui s'intègre à MLflow"""
    
    def __init__(self):
        self.db_engine = None
        self.Session = None
        self.login_manager = None
        logger.info("🔐 Initialisation du plugin d'authentification MLflow")
    
    def init_app(self, app):
        """Initialise le plugin avec l'app Flask de MLflow"""
        
        # Vérifier si l'auth est activée
        if not os.getenv('MLFLOW_AUTH_ENABLED', 'false').lower() == 'true':
            logger.info("⚠️  Authentification désactivée")
            return
        
        logger.info("🚀 Activation de l'authentification MLflow")
        
        # Configuration de la base de données
        self._setup_database(app)
        
        # Configuration de Flask-Login
        self._setup_login_manager(app)
        
        # Enregistrement des routes
        self._register_routes(app)
        
        # Configuration du middleware
        self._setup_middleware(app)
        
        logger.info("✅ Plugin d'authentification activé avec succès")
    
    def _setup_database(self, app):
        """Configure la connexion à la base de données"""
        try:
            db_uri = os.environ.get('MLFLOW_BACKEND_STORE_URI', 'sqlite:///mlflow.db')
            
            # Adapter l'URI pour l'auth
            if db_uri.startswith('sqlite:///'):
                db_path = db_uri.replace('sqlite:///', '')
                auth_db_path = db_path.replace('.db', '_auth.db')
                db_uri = f'sqlite:///{auth_db_path}'
            
            self.db_engine = create_engine(db_uri)
            self.Session = sessionmaker(bind=self.db_engine)
            
            # Créer les tables
            from .auth.models import Base
            Base.metadata.create_all(self.db_engine)
            
            # Stocker dans l'app
            app.auth_db_session = self.Session
            
            logger.info(f"📊 Base de données configurée : {db_uri}")
            
        except Exception as e:
            logger.error(f"❌ Erreur configuration DB : {e}")
            raise
    
    def _setup_login_manager(self, app):
        """Configure Flask-Login"""
        try:
            self.login_manager = LoginManager()
            self.login_manager.init_app(app)
            self.login_manager.login_view = 'auth.login'
            self.login_manager.login_message = 'Connexion requise pour accéder à cette page.'
            
            @self.login_manager.user_loader
            def load_user(user_id):
                session = app.auth_db_session()
                try:
                    from .auth.models import User
                    return session.query(User).get(int(user_id))
                finally:
                    session.close()
            
            logger.info("🔑 Flask-Login configuré")
            
        except Exception as e:
            logger.error(f"❌ Erreur configuration Flask-Login : {e}")
            raise
    
    def _register_routes(self, app):
        """Enregistre les routes d'authentification"""
        try:
            from .auth.routes import auth_bp
            from .admin.routes import admin_bp
            
            app.register_blueprint(auth_bp, url_prefix='/auth')
            app.register_blueprint(admin_bp, url_prefix='/admin')
            
            logger.info("🛣️  Routes d'authentification enregistrées")
            
        except Exception as e:
            logger.error(f"❌ Erreur enregistrement routes : {e}")
            raise
    
    def _setup_middleware(self, app):
        """Configure le middleware d'authentification"""
        
        # Routes publiques
        PUBLIC_ROUTES = ['/auth/', '/static/', '/health', '/version']
        
        @app.before_request
        def authenticate_request():
            """Vérifie l'authentification avant chaque requête"""
            
            # Ignorer les routes publiques
            if any(request.path.startswith(route) for route in PUBLIC_ROUTES):
                return
            
            # Vérifier l'authentification
            if not current_user.is_authenticated:
                logger.info(f"🚫 Accès non autorisé à {request.path}")
                return redirect(url_for('auth.login', next=request.url))
            
            # Log de l'accès autorisé
            logger.debug(f"✅ Accès autorisé : {current_user.username} -> {request.path}")
        
        @app.context_processor
        def inject_auth_context():
            """Injecte le contexte d'authentification dans les templates"""
            return {
                'current_user': current_user if current_user.is_authenticated else None,
                'auth_enabled': True
            }

class AuthProvider:
    """Fournisseur d'authentification pour MLflow"""
    
    def authenticate_request(self, request):
        """Authentifie une requête HTTP"""
        
        # Vérifier l'API key
        api_key = request.headers.get('X-API-Key')
        if api_key:
            return self._authenticate_api_key(api_key)
        
        # Vérifier la session
        if current_user and current_user.is_authenticated:
            return current_user.username
        
        return None
    
    def _authenticate_api_key(self, api_key):
        """Authentifie via API key"""
        try:
            from flask import current_app
            session = current_app.auth_db_session()
            from .auth.models import User
            
            user = session.query(User).filter_by(
                api_key=api_key, 
                is_active=True
            ).first()
            
            return user.username if user else None
            
        except Exception as e:
            logger.error(f"❌ Erreur authentification API key : {e}")
            return None
        finally:
            session.close()

# Auto-chargement du plugin
def _load_auth_extension():
    """Charge automatiquement l'extension au démarrage de MLflow"""
    
    if os.environ.get('MLFLOW_AUTH_ENABLED', 'false').lower() == 'true':
        try:
            from mlflow.server import app
            extension = AuthExtension()
            extension.init_app(app)
        except ImportError:
            logger.warning("⚠️  MLflow server non disponible, plugin non chargé")
        except Exception as e:
            logger.error(f"❌ Erreur chargement plugin : {e}")

# Chargement automatique
_load_auth_extension()
