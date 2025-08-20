from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, Optional
from functools import wraps
import logging

from ..auth.models import User

admin_bp = Blueprint('admin', __name__, template_folder='../templates')
logger = logging.getLogger(__name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Accès refusé - Droits administrateur requis', 'error')
            logger.warning(f"🚫 Tentative d'accès admin refusée : {current_user.username if current_user.is_authenticated else 'Anonymous'}")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

class UserForm(FlaskForm):
    username = StringField('Nom d\'utilisateur', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[Optional(), Length(min=6)])
    role = SelectField('Rôle', choices=[
        ('viewer', 'Visualiseur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ])
    is_active = BooleanField('Compte actif', default=True)

@admin_bp.route('/users')
@login_required
@admin_required
def list_users():
    session = current_app.auth_db_session()
    try:
        users = session.query(User).all()
        return render_template('admin/users.html', users=users)
    finally:
        session.close()

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    form = UserForm()
    
    if form.validate_on_submit():
        session = current_app.auth_db_session()
        try:
            # Vérifier que l'utilisateur n'existe pas déjà
            existing = session.query(User).filter(
                (User.username == form.username.data) |
                (User.email == form.email.data)
            ).first()
            
            if existing:
                flash('Un utilisateur avec ce nom ou cet email existe déjà', 'error')
                return render_template('admin/create_user.html', form=form)
            
            user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data,
                is_active=form.is_active.data
            )
            user.set_password(form.password.data)
            
            session.add(user)
            session.commit()
            
            logger.info(f"👤 Utilisateur créé par {current_user.username} : {user.username}")
            flash(f'Utilisateur {user.username} créé avec succès', 'success')
            return redirect(url_for('admin.list_users'))
        
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erreur création utilisateur : {e}")
            flash(f'Erreur lors de la création : {str(e)}', 'error')
        finally:
            session.close()
    
    return render_template('admin/create_user.html', form=form)

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    session = current_app.auth_db_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            flash('Utilisateur non trouvé', 'error')
            return redirect(url_for('admin.list_users'))
        
        form = UserForm(obj=user)
        
        if form.validate_on_submit():
            user.username = form.username.data
            user.email = form.email.data
            user.role = form.role.data
            user.is_active = form.is_active.data
            
            if form.password.data:
                user.set_password(form.password.data)
            
            session.commit()
            
            logger.info(f"👤 Utilisateur modifié par {current_user.username} : {user.username}")
            flash(f'Utilisateur {user.username} modifié avec succès', 'success')
            return redirect(url_for('admin.list_users'))
        
        return render_template('admin/edit_user.html', form=form, user=user)
    finally:
        session.close()

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Impossible de supprimer votre propre compte'}), 400
    
    session = current_app.auth_db_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            flash('Utilisateur non trouvé', 'error')
            return redirect(url_for('admin.list_users'))
        
        username = user.username
        session.delete(user)
        session.commit()
        
        logger.info(f"🗑️  Utilisateur supprimé par {current_user.username} : {username}")
        flash(f'Utilisateur {username} supprimé', 'success')
        return redirect(url_for('admin.list_users'))
    finally:
        session.close()

@admin_bp.route('/api/users')
@login_required
@admin_required
def api_list_users():
    session = current_app.auth_db_session()
    try:
        users = session.query(User).all()
        return jsonify([user.to_dict() for user in users])
    finally:
        session.close()

@admin_bp.route('/api/stats')
@login_required
@admin_required
def api_stats():
    session = current_app.auth_db_session()
    try:
        total_users = session.query(User).count()
        active_users = session.query(User).filter_by(is_active=True).count()
        admin_users = session.query(User).filter_by(role='admin').count()
        
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'admin_users': admin_users
        })
    finally:
        session.close()
