"""
MLflow Authentication Plugin
============================

Plugin d'authentification et de gestion des rôles pour MLflow.

Installation:
    pip install mlflow-auth-plugin

Configuration:
    export MLFLOW_AUTH_ENABLED=true
    export MLFLOW_BACKEND_STORE_URI=sqlite:///mlflow.db
    
Usage:
    mlflow server --host 0.0.0.0 --port 5000
"""

__version__ = "1.0.0"
__author__ = "Votre Nom"

from .plugin import AuthExtension, AuthProvider

__all__ = ['AuthExtension', 'AuthProvider']
