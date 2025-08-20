from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="mlflow-auth-plugin",
    version="1.0.0",
    author="EikouJ",
    author_email="votre.email@example.com",
    description="An authentification system with role management for MLflow",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EikouJ/MLflow-authentification-plugin",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "mlflow>=2.0.0",
        "flask-login>=0.6.0",
        "flask-bcrypt>=1.0.0",
        "sqlalchemy>=1.4.0",
        "wtforms>=3.0.0",
        "flask-wtf>=1.0.0",
        "alembic>=1.8.0",
    ],
    entry_points={
        "mlflow.request_auth_provider": [
            "auth = mlflow_auth.plugin:AuthProvider"
        ],
        "mlflow.app_extension": [
            "auth = mlflow_auth.plugin:AuthExtension"
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    package_data={
        "mlflow_auth": [
            "templates/**/*.html",
            "static/**/*.css",
            "static/**/*.js",
        ]
    },
)
