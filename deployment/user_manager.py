#!/usr/bin/env python3
"""
Gestionnaire d'utilisateurs MLflow Auth
Utilitaire en ligne de commande pour gérer les utilisateurs
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from getpass import getpass
from tabulate import tabulate

# Ajouter le chemin vers le plugin
sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))

def get_db_session():
    """Obtient une session de base de données"""
    try:
        from mlflow_auth.auth.models import Base, User, LoginHistory
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        base_dir = Path(__file__).parent
        db_path = base_dir / "data" / "mlflow_auth.db"
        
        if not db_path.exists():
            print("❌ Base de données non trouvée. Exécutez d'abord start_mlflow.py")
            return None, None, None
        
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        session = Session()
        
        return session, User, LoginHistory
        
    except ImportError:
        print("❌ Plugin mlflow-auth non trouvé")
        return None, None, None
    except Exception as e:
        print(f"❌ Erreur connexion base de données: {e}")
        return None, None, None

def list_users(args):
    """Liste tous les utilisateurs"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        users = session.query(User).order_by(User.username).all()
        
        if not users:
            print("Aucun utilisateur trouvé.")
            return 0
        
        # Préparer les données pour le tableau
        headers = ["ID", "Utilisateur", "Email", "Rôle", "Statut", "Dernière Connexion", "Créé le"]
        data = []
        
        for user in users:
            status = "✅ Actif" if user.is_active else "❌ Inactif"
            last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "Jamais"
            created = user.created_at.strftime("%Y-%m-%d") if hasattr(user, 'created_at') and user.created_at else "N/A"
            
            data.append([
                user.id,
                user.username,
                user.email,
                user.role.upper(),
                status,
                last_login,
                created
            ])
        
        print(f"\n👥 {len(users)} utilisateur(s) trouvé(s):")
        print(tabulate(data, headers=headers, tablefmt="grid"))
        
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return 1
    finally:
        session.close()

def create_user(args):
    """Crée un nouvel utilisateur"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        username = args.username or input("Nom d'utilisateur: ")
        email = args.email or input("Email: ")
        
        if args.password:
            password = args.password
        else:
            password = getpass("Mot de passe: ")
            password_confirm = getpass("Confirmer le mot de passe: ")
            if password != password_confirm:
                print("❌ Les mots de passe ne correspondent pas")
                return 1
        
        role = args.role or 'user'
        
        # Vérifier si l'utilisateur existe déjà
        existing = session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing:
            print(f"❌ Utilisateur ou email déjà existant: {existing.username}")
            return 1
        
        # Créer le nouvel utilisateur
        user = User(
            username=username,
            email=email,
            role=role,
            is_active=True
        )
        user.set_password(password)
        
        session.add(user)
        session.commit()
        
        print(f"✅ Utilisateur créé: {username} ({role})")
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        session.rollback()
        return 1
    finally:
        session.close()

def update_user(args):
    """Met à jour un utilisateur"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        user = session.query(User).filter_by(username=args.username).first()
        if not user:
            print(f"❌ Utilisateur non trouvé: {args.username}")
            return 1
        
        # Mettre à jour les champs spécifiés
        updated_fields = []
        
        if args.email:
            user.email = args.email
            updated_fields.append(f"email -> {args.email}")
        
        if args.role:
            user.role = args.role
            updated_fields.append(f"rôle -> {args.role}")
        
        if args.activate is not None:
            user.is_active = args.activate
            status = "activé" if args.activate else "désactivé"
            updated_fields.append(f"statut -> {status}")
        
        if args.password:
            user.set_password(args.password)
            updated_fields.append("mot de passe -> ****")
        
        if updated_fields:
            session.commit()
            print(f"✅ Utilisateur {args.username} mis à jour:")
            for field in updated_fields:
                print(f"   • {field}")
        else:
            print("⚠️ Aucune modification spécifiée")
        
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        session.rollback()
        return 1
    finally:
        session.close()

def delete_user(args):
    """Supprime un utilisateur"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        user = session.query(User).filter_by(username=args.username).first()
        if not user:
            print(f"❌ Utilisateur non trouvé: {args.username}")
            return 1
        
        if user.role == 'admin':
            # Compter les admins restants
            admin_count = session.query(User).filter_by(role='admin', is_active=True).count()
            if admin_count <= 1:
                print("❌ Impossible de supprimer le dernier administrateur actif")
                return 1
        
        if not args.force:
            confirm = input(f"⚠️ Êtes-vous sûr de vouloir supprimer {args.username}? (oui/non): ")
            if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
                print("❌ Suppression annulée")
                return 0
        
        # Supprimer l'historique associé
        session.query(LoginHistory).filter_by(user_id=user.id).delete()
        
        # Supprimer l'utilisateur
        session.delete(user)
        session.commit()
        
        print(f"✅ Utilisateur {args.username} supprimé")
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        session.rollback()
        return 1
    finally:
        session.close()

def show_history(args):
    """Affiche l'historique des connexions"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        from sqlalchemy import desc
        
        # Construire la requête
        query = session.query(LoginHistory).join(User)
        
        if args.username:
            user = session.query(User).filter_by(username=args.username).first()
            if not user:
                print(f"❌ Utilisateur non trouvé: {args.username}")
                return 1
            query = query.filter(LoginHistory.user_id == user.id)
        
        if args.activity_type:
            query = query.filter(LoginHistory.activity_type == args.activity_type)
        
        # Limiter les résultats
        limit = args.limit or 20
        history = query.order_by(desc(LoginHistory.login_time)).limit(limit).all()
        
        if not history:
            print("Aucun historique trouvé.")
            return 0
        
        # Préparer les données pour le tableau
        headers = ["Utilisateur", "Activité", "Date/Heure", "IP", "Navigateur"]
        data = []
        
        for entry in history:
            user_agent = entry.user_agent[:40] + "..." if len(entry.user_agent) > 40 else entry.user_agent
            activity_icon = "🟢" if entry.activity_type == "login" else "🔴"
            
            data.append([
                entry.user.username,
                f"{activity_icon} {entry.activity_type}",
                entry.login_time.strftime("%Y-%m-%d %H:%M:%S"),
                entry.ip_address,
                user_agent
            ])
        
        print(f"\n📊 Historique des activités ({len(history)} entrées):")
        print(tabulate(data, headers=headers, tablefmt="grid"))
        
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return 1
    finally:
        session.close()

def reset_password(args):
    """Remet à zéro le mot de passe d'un utilisateur"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        user = session.query(User).filter_by(username=args.username).first()
        if not user:
            print(f"❌ Utilisateur non trouvé: {args.username}")
            return 1
        
        if args.password:
            new_password = args.password
        else:
            new_password = getpass(f"Nouveau mot de passe pour {args.username}: ")
            password_confirm = getpass("Confirmer le nouveau mot de passe: ")
            if new_password != password_confirm:
                print("❌ Les mots de passe ne correspondent pas")
                return 1
        
        user.set_password(new_password)
        session.commit()
        
        print(f"✅ Mot de passe mis à jour pour {args.username}")
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        session.rollback()
        return 1
    finally:
        session.close()

def show_stats(args):
    """Affiche les statistiques de la base de données"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        from datetime import timedelta
        from sqlalchemy import func
        
        now = datetime.now()
        
        # Statistiques générales
        total_users = session.query(User).count()
        active_users = session.query(User).filter_by(is_active=True).count()
        admin_users = session.query(User).filter_by(role='admin').count()
        
        # Statistiques de connexion
        total_logins = session.query(LoginHistory).filter_by(activity_type='login').count()
        logins_24h = session.query(LoginHistory)\
            .filter(LoginHistory.login_time >= now - timedelta(hours=24))\
            .filter_by(activity_type='login')\
            .count()
        logins_7d = session.query(LoginHistory)\
            .filter(LoginHistory.login_time >= now - timedelta(days=7))\
            .filter_by(activity_type='login')\
            .count()
        
        print("📊 Statistiques MLflow Auth")
        print("=" * 30)
        print(f"👥 Utilisateurs:")
        print(f"   • Total: {total_users}")
        print(f"   • Actifs: {active_users}")
        print(f"   • Inactifs: {total_users - active_users}")
        print(f"   • Administrateurs: {admin_users}")
        print(f"   • Utilisateurs standards: {total_users - admin_users}")
        
        print(f"\n🔐 Connexions:")
        print(f"   • Total historique: {total_logins}")
        print(f"   • Dernières 24h: {logins_24h}")
        print(f"   • Derniers 7 jours: {logins_7d}")
        
        # Top utilisateurs par connexions
        top_users = session.query(
            User.username,
            func.count(LoginHistory.id).label('login_count')
        ).join(LoginHistory)\
         .filter(LoginHistory.activity_type == 'login')\
         .group_by(User.id)\
         .order_by(func.count(LoginHistory.id).desc())\
         .limit(5).all()
        
        if top_users:
            print(f"\n🏆 Utilisateurs les plus actifs:")
            for username, count in top_users:
                print(f"   • {username}: {count} connexions")
        
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return 1
    finally:
        session.close()

def cleanup_history(args):
    """Nettoie l'historique ancien"""
    session, User, LoginHistory = get_db_session()
    if not session:
        return 1
    
    try:
        days = args.days or 90
        cutoff_date = datetime.now() - timedelta(days=days)
        
        old_entries = session.query(LoginHistory)\
            .filter(LoginHistory.login_time < cutoff_date)
        
        count = old_entries.count()
        
        if count == 0:
            print(f"Aucune entrée antérieure à {days} jours trouvée.")
            return 0
        
        if not args.force:
            confirm = input(f"⚠️ Supprimer {count} entrées antérieures à {days} jours? (oui/non): ")
            if confirm.lower() not in ['oui', 'o', 'yes', 'y']:
                print("❌ Nettoyage annulé")
                return 0
        
        old_entries.delete()
        session.commit()
        
        print(f"✅ {count} entrées d'historique supprimées")
        return 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        session.rollback()
        return 1
    finally:
        session.close()

def main():
    """Fonction principale"""
    
    parser = argparse.ArgumentParser(description='Gestionnaire d\'utilisateurs MLflow Auth')
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Liste des utilisateurs
    list_parser = subparsers.add_parser('list', help='Lister les utilisateurs')
    
    # Créer un utilisateur
    create_parser = subparsers.add_parser('create', help='Créer un utilisateur')
    create_parser.add_argument('--username', help='Nom d\'utilisateur')
    create_parser.add_argument('--email', help='Email')
    create_parser.add_argument('--password', help='Mot de passe')
    create_parser.add_argument('--role', choices=['user', 'admin'], default='user', help='Rôle')
    
    # Mettre à jour un utilisateur
    update_parser = subparsers.add_parser('update', help='Mettre à jour un utilisateur')
    update_parser.add_argument('username', help='Nom d\'utilisateur')
    update_parser.add_argument('--email', help='Nouvel email')
    update_parser.add_argument('--role', choices=['user', 'admin'], help='Nouveau rôle')
    update_parser.add_argument('--activate', action='store_true', help='Activer l\'utilisateur')
    update_parser.add_argument('--deactivate', dest='activate', action='store_false', help='Désactiver l\'utilisateur')
    update_parser.add_argument('--password', help='Nouveau mot de passe')
    
    # Supprimer un utilisateur
    delete_parser = subparsers.add_parser('delete', help='Supprimer un utilisateur')
    delete_parser.add_argument('username', help='Nom d\'utilisateur')
    delete_parser.add_argument('--force', action='store_true', help='Forcer la suppression')
    
    # Réinitialiser mot de passe
    reset_parser = subparsers.add_parser('reset-password', help='Réinitialiser le mot de passe')
    reset_parser.add_argument('username', help='Nom d\'utilisateur')
    reset_parser.add_argument('--password', help='Nouveau mot de passe')
    
    # Afficher l'historique
    history_parser = subparsers.add_parser('history', help='Afficher l\'historique des connexions')
    history_parser.add_argument('--username', help='Filtrer par utilisateur')
    history_parser.add_argument('--activity-type', choices=['login', 'logout'], help='Type d\'activité')
    history_parser.add_argument('--limit', type=int, default=20, help='Nombre d\'entrées à afficher')
    
    # Afficher les statistiques
    stats_parser = subparsers.add_parser('stats', help='Afficher les statistiques')
    
    # Nettoyer l'historique
    cleanup_parser = subparsers.add_parser('cleanup', help='Nettoyer l\'historique ancien')
    cleanup_parser.add_argument('--days', type=int, default=90, help='Supprimer les entrées plus anciennes que X jours')
    cleanup_parser.add_argument('--force', action='store_true', help='Forcer le nettoyage')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    print("👤 Gestionnaire d'Utilisateurs MLflow")
    print("=" * 35)
    
    # Router vers la fonction appropriée
    commands = {
        'list': list_users,
        'create': create_user,
        'update': update_user,
        'delete': delete_user,
        'reset-password': reset_password,
        'history': show_history,
        'stats': show_stats,
        'cleanup': cleanup_history
    }
    
    if args.command in commands:
        return commands[args.command](args)
    else:
        print(f"❌ Commande inconnue: {args.command}")
        return 1

if __name__ == '__main__':
    try:
        # Vérifier tabulate
        try:
            import tabulate
        except ImportError:
            print("⚠️ Module 'tabulate' non trouvé, installation...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "tabulate"])
            import tabulate
        
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n👋 Opération annulée par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)