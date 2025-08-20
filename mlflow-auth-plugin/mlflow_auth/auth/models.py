from sqlalchemy import Column, Integer, String, Boolean, DateTime, text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from flask_login import UserMixin
import hashlib
import uuid
from datetime import datetime, timedelta

Base = declarative_base()

class User(Base, UserMixin):
    __tablename__ = 'mlflow_users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default='user')  # 'admin', 'user', 'viewer'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    last_login = Column(DateTime)
    api_key = Column(String(255), unique=True)
    
    # Relations
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.api_key:
            self.api_key = str(uuid.uuid4())
    
    def set_password(self, password):
        """Hash le mot de passe avec une méthode simple mais sécurisée"""
        salt = "mlflow-salt-2024"
        combined = password + salt
        self.password_hash = hashlib.sha256(combined.encode()).hexdigest()
    
    def check_password(self, password):
        """Vérifie le mot de passe"""
        salt = "mlflow-salt-2024"
        combined = password + salt
        expected_hash = hashlib.sha256(combined.encode()).hexdigest()
        return self.password_hash == expected_hash
    
    def has_permission(self, permission):
        if self.role == 'admin':
            return True
        return permission in self.get_role_permissions()
    
    def get_role_permissions(self):
        role_permissions = {
            'viewer': ['read'],
            'user': ['read', 'write'],
            'admin': ['read', 'write', 'admin']
        }
        return role_permissions.get(self.role, [])
    
    def record_login(self, session, ip_address, user_agent):
        """Enregistre une connexion dans l'historique"""
        login_record = LoginHistory(
            user_id=self.id,
            ip_address=ip_address,
            user_agent=user_agent,
            login_time=datetime.utcnow()
        )
        session.add(login_record)
        
        # Mettre à jour last_login
        self.last_login = datetime.utcnow()
    
    def get_recent_logins(self, session, limit=10):
        """Récupère les dernières connexions"""
        return session.query(LoginHistory).filter_by(user_id=self.id)\
                      .order_by(LoginHistory.login_time.desc())\
                      .limit(limit).all()
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class LoginHistory(Base):
    __tablename__ = 'login_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('mlflow_users.id'), nullable=False)
    ip_address = Column(String(45), nullable=False)  # Support IPv6
    user_agent = Column(String(500))
    login_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    logout_time = Column(DateTime)
    session_duration = Column(Integer)  # en secondes
    
    # Relations
    user = relationship("User", back_populates="login_history")
    
    def record_logout(self):
        """Enregistre la déconnexion et calcule la durée de session"""
        self.logout_time = datetime.utcnow()
        if self.login_time:
            delta = self.logout_time - self.login_time
            self.session_duration = int(delta.total_seconds())
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else 'Unknown',
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'login_time': self.login_time.isoformat() if self.login_time else None,
            'logout_time': self.logout_time.isoformat() if self.logout_time else None,
            'session_duration': self.session_duration
        }