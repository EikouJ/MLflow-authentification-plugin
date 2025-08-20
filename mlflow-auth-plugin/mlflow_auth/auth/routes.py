from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Length
from sqlalchemy.sql import func
import logging

from .models import User

auth_bp = Blueprint('auth', __name__, template_folder='../templates')
logger = logging.getLogger(__name__)

class LoginForm(FlaskForm):
    username = StringField('Nom d\'utilisateur', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    remember_me = BooleanField('Se souvenir de moi')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')
    
    form = LoginForm()
    if form.validate_on_submit():
        session = current_app.auth_db_session()
        try:
            user = session.query(User).filter_by(
                username=form.username.data,
                is_active=True
            ).first()
            
            if user and user.check_password(form.password.data):
                # Mettre à jour le dernier login
                user.last_login = func.now()
                session.commit()
                
                login_user(user, remember=form.remember_me.data)
                logger.info(f"✅ Connexion réussie : {user.username}")
                
                next_page = request.args.get('next')
                return redirect(next_page or '/')
            
            logger.warning(f"🚫 Tentative de connexion échouée : {form.username.data}")
            flash('Nom d\'utilisateur ou mot de passe incorrect', 'error')
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de la connexion : {e}")
            flash('Erreur lors de la connexion', 'error')
        finally:
            session.close()
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info(f"👋 Déconnexion : {username}")
    flash('Vous avez été déconnecté', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')

@auth_bp.route('/api/user-info')
@login_required
def api_user_info():
    return jsonify(current_user.to_dict())

@auth_bp.route('/health')
def health():
    """Point de santé pour le monitoring"""
    return jsonify({
        'status': 'ok',
        'auth_enabled': True,
        'version': '1.0.0'
    })
