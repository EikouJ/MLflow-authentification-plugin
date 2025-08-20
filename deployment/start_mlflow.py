#!/usr/bin/env python3
"""
Script de démarrage MLflow avec authentification
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

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

def check_plugin():
    """Vérifie que le plugin d'authentification est installé"""
    
    try:
        import mlflow_auth
        print("✅ Plugin d'authentification disponible")
        return True
    except ImportError:
        print("❌ Plugin d'authentification non installé")
        print("💡 Exécutez : python setup_environment.py")
        return False

def start_mlflow(host='0.0.0.0', port=5000, workers=None):
    """Démarre le serveur MLflow"""
    
    # Vérifier MLflow
    try:
        import mlflow
        print(f"🚀 MLflow version : {mlflow.__version__}")
    except ImportError:
        print("❌ MLflow non installé")
        return False
    
    # Construire la commande
    cmd = [
        sys.executable, "-m", "mlflow", "server",
        "--host", str(host),
        "--port", str(port)
    ]
    
    if workers:
        cmd.extend(["--workers", str(workers)])
    
    # Afficher la configuration
    print("\n" + "=" * 50)
    print("🔧 Configuration MLflow :")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Auth: {'✅ Activée' if os.getenv('MLFLOW_AUTH_ENABLED') == 'true' else '❌ Désactivée'}")
    print(f"   DB: {os.getenv('MLFLOW_BACKEND_STORE_URI', 'Par défaut')}")
    print(f"   Artifacts: {os.getenv('MLFLOW_DEFAULT_ARTIFACT_ROOT', 'Par défaut')}")
    print("=" * 50)
    
    print(f"\n🌐 MLflow sera accessible sur : http://{host}:{port}")
    if os.getenv('MLFLOW_AUTH_ENABLED') == 'true':
        print("🔐 Connexion requise : admin / admin123 (à changer !)")
    
    print("\n⏳ Démarrage du serveur MLflow...")
    print("   (Ctrl+C pour arrêter)")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n👋 Arrêt du serveur MLflow")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Erreur lors du démarrage : {e}")
        return False
    
    return True

def main():
    """Fonction principale"""
    
    parser = argparse.ArgumentParser(description='Démarrer MLflow avec authentification')
    parser.add_argument('--host', default=None, help='Host du serveur')
    parser.add_argument('--port', type=int, default=None, help='Port du serveur')
    parser.add_argument('--workers', type=int, help='Nombre de workers')
    parser.add_argument('--no-auth', action='store_true', help='Désactiver l\'authentification')
    
    args = parser.parse_args()
    
    # Charger la configuration
    load_environment()
    
    # Configuration des paramètres
    host = args.host or os.getenv('MLFLOW_HOST', '0.0.0.0')
    port = args.port or int(os.getenv('MLFLOW_PORT', 5000))
    
    # Gérer l'authentification
    if args.no_auth:
        os.environ['MLFLOW_AUTH_ENABLED'] = 'false'
        print("⚠️  Authentification désactivée")
    else:
        # Vérifier le plugin d'auth
        if not check_plugin():
            return False
    
    # Démarrer MLflow
    return start_mlflow(host=host, port=port, workers=args.workers)

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
