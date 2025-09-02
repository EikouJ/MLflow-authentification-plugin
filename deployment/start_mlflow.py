#!/usr/bin/env python3
"""
MLflow startup with authentication and admin dashboard
- Front <-> Backend via JSON REST APIs
- Users CRUD from dashboard
- Login/Logout tracked in DB (username, email, ip, timestamps) — user_agent is stored but NOT exposed in API
- Works even if the full plugin package is missing (fallback mode)

Key fixes/features:
- Use Session(expire_on_commit=False) to avoid DetachedInstanceError
- Use Session.get() (SQLAlchemy 2.x style)
- Insert only existing columns on LoginHistory (support ip_address/ip)
- Roll back the session if history insert fails (avoid PendingRollbackError)
- Update logout_time only if the column exists
- Use timezone-aware UTC datetimes (no utcnow deprecation)
- Allow favicon without auth to avoid spurious 500
- Force re-login after each server restart (unique cookie name + boot_id check)
"""

import os
import sys
import argparse
import logging
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone  # timezone-aware

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_environment():
    """Load environment variables from .env file if present."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print("📄 Loading configuration from .env")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    else:
        print("⚠️ .env file not found, using defaults")


def start_mlflow_backend(port=5001):
    """Start MLflow server in background and wait until /health is ready."""
    cmd = [
        sys.executable, "-m", "mlflow", "server",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--serve-artifacts"
    ]

    print(f"🚀 Starting MLflow backend on port {port}...")
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Wait MLflow readiness using /health
        import requests
        for _ in range(30):
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
                if resp.status_code == 200:
                    print("✅ MLflow backend is up")
                    return process, port
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)

        print("❌ Timeout - MLflow backend did not start")
        process.terminate()
        return None, None

    except Exception as e:
        print(f"❌ MLflow start error: {e}")
        return None, None


def create_auth_app(backend_port):
    """Create Flask application with authentication and admin APIs."""

    from flask import (
        Flask, request, redirect, url_for, session,
        render_template, jsonify, flash, render_template_string, Response, abort
    )
    from flask_login import (
        LoginManager, login_required, current_user, login_user, logout_user
    )

    # Flask app
    app = Flask(__name__, template_folder='templates')
    app.secret_key = os.getenv('MLFLOW_AUTH_SECRET_KEY', 'dev-secret-key-2024')
    app.permanent_session_lifetime = timedelta(minutes=10)

    # --- Force re-login after each server restart ---
    # Generate a boot-scoped id; change session cookie name per boot.
    app.boot_id = os.urandom(8).hex()
    # Using a unique cookie name ensures browser won't send an old cookie after restart
    app.config['SESSION_COOKIE_NAME'] = f"mlflow_auth_{app.boot_id}"

    # DB location (SQLite file in ./data/)
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "mlflow_auth.db"
    db_path.parent.mkdir(exist_ok=True)

    # Built-in minimal login template (fallback when file template missing)
    LOGIN_TEMPLATE = '''
    <!DOCTYPE html><html lang="fr"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MLflow - Login</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto; background: #0f172a; margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; }
      .card { background: #ffffff; border-radius: 16px; padding: 28px; width: 100%; max-width: 420px; box-shadow: 0 12px 32px rgba(0,0,0,.15) }
      h1 { margin: 0 0 8px; font-size: 22px; }
      p { margin: 0 0 18px; color: #475569 }
      label { display:block; margin: 10px 0 6px; font-weight: 600; }
      input { width: 100%; padding: 10px 12px; border: 2px solid #e2e8f0; border-radius: 10px; }
      button { width: 100%; padding: 12px; margin-top: 16px; border:0; border-radius: 10px; background: #2563eb; color: #fff; font-weight: 700; cursor:pointer }
      .err { background: #fee2e2; color:#991b1b; padding: 10px; border-radius: 10px; margin-bottom: 10px; }
      .hint { margin-top:10px; color:#64748b; font-size: 12px }
    </style></head><body>
      <div class="card">
        <h1>MLflow</h1><p>Authentication required</p>
        {% if error %}<div class="err">{{ error }}</div>{% endif %}
        <form method="POST">
          <label for="username">Username</label>
          <input id="username" name="username" required autofocus>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" required>
          <button type="submit">Sign in</button>
        </form>
        <div class="hint">Default: admin / admin123</div>
      </div>
    </body></html>
    '''

    # Try importing the full plugin models (User, LoginHistory)
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))
        from mlflow_auth.auth.models import Base, User, LoginHistory
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        # IMPORTANT: keep attributes after commit to avoid DetachedInstanceError
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        app.auth_db_session = Session

        print("✅ Auth plugin loaded")
    except Exception as e:
        print(f"⚠️ Full plugin not available ({e}) — using basic mode")
        app.auth_db_session = None
        User = None  # avoid accidental use in basic mode
        LoginHistory = None

    # Flask-Login configuration
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    # --- Enforce session freshness after server restart ---
    @app.before_request
    def _enforce_fresh_session_after_boot():
        """
        Enforce that session belongs to the current server boot.
        If the app was restarted, invalidate any previously issued session
        so the user must sign in again.
        """
        sid_boot = session.get("boot_id")
        if sid_boot is None:
            # Not logged in or set yet -> nothing to do. Protected routes will trigger login flow.
            return
        if sid_boot != app.boot_id:
            # Server restarted: clear session and let @login_required handle redirect.
            try:
                logout_user()
            except Exception:
                pass
            session.clear()
            return  # next request to a protected route will go to /login

    # ---------- DB helpers & serializers (used by JSON APIs) ----------
    from contextlib import contextmanager
    from sqlalchemy import inspect as sa_inspect

    def _now():
        """Return timezone-aware UTC datetime (avoid deprecated utcnow())."""
        return datetime.now(timezone.utc)

    @contextmanager
    def db():
        """Context manager for SQLAlchemy session with commit/rollback."""
        session_db = None
        try:
            session_db = app.auth_db_session() if app.auth_db_session else None
            yield session_db
            if session_db:
                session_db.commit()
        except Exception:
            if session_db:
                session_db.rollback()
            raise
        finally:
            if session_db:
                session_db.close()

    # Detect columns available on LoginHistory (runtime-safe)
    try:
        _lh_cols = set(sa_inspect(LoginHistory).columns.keys())
    except Exception:
        _lh_cols = set()

    def _lh_has(colname: str) -> bool:
        return colname in _lh_cols

    def _client_ip(req) -> str:
        """Resolve client IP string (X-Forwarded-For or remote_addr). Always return a non-None string."""
        xf = req.headers.get("X-Forwarded-For")
        if xf:
            ip = xf.split(",")[0].strip()  # take first IP from list
            if ip:
                return ip
        return req.remote_addr or ""

    def user_to_dict(u):
        """Serialize User -> dict for API responses."""
        return {
            "id": getattr(u, "id", None),
            "username": getattr(u, "username", None),
            "email": getattr(u, "email", None),
            "role": getattr(u, "role", "user"),
            "is_active": getattr(u, "is_active", True),
            "created_at": getattr(u, "created_at", None).isoformat() if getattr(u, "created_at", None) else None,
            "last_login": getattr(u, "last_login", None).isoformat() if getattr(u, "last_login", None) else None,
            "password_change_required": getattr(u, "password_change_required", False),
        }

    def history_to_dict(h, email_value=None):
        """Serialize LoginHistory -> dict for API responses.
        - Do NOT expose user_agent
        - Normalize ip/ip_address to 'ip'
        - Include 'username' and 'email'
        """
        ip_val = getattr(h, "ip", None)
        if ip_val is None:
            ip_val = getattr(h, "ip_address", None)
        return {
            "id": getattr(h, "id", None),
            "user_id": getattr(h, "user_id", None),
            "username": getattr(h, "username", None),
            "email": email_value,  # provided by API via User join
            "ip": ip_val,
            "login_time": getattr(h, "login_time", None).isoformat() if getattr(h, "login_time", None) else None,
            "logout_time": getattr(h, "logout_time", None).isoformat() if getattr(h, "logout_time", None) else None,
            "success": getattr(h, "success", None),
        }

    # ---------- User loader (Flask-Login) ----------
    @login_manager.user_loader
    def load_user(user_id):
        if app.auth_db_session:
            with db() as s:
                try:
                    # SQLAlchemy 1.4+/2.0 style (no legacy Query.get)
                    return s.get(User, int(user_id))
                except Exception:
                    return None
        else:
            # Very basic fallback user model
            from flask_login import UserMixin
            class SimpleUser(UserMixin):
                def __init__(self, username):
                    self.id = username
                    self.username = username
                    self.role = 'admin' if username == 'admin' else 'user'
                    # Ensure Flask-Login never tries to refresh from DB
                    self.is_active = True
            if user_id == 'admin':
                return SimpleUser(user_id)
        return None

    # ---------- Auth routes ----------
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username'].strip()
            password = request.form['password']

            # Full plugin auth
            if app.auth_db_session:
                with db() as s:
                    user = s.query(User).filter_by(username=username, is_active=True).first()
                    if user and user.check_password(password):
                        login_user(user, remember=False)
                        # Optional: expunge to avoid any lazy load outside the session
                        try:
                            s.expunge(user)
                        except Exception:
                            pass

                        session['last_activity'] = datetime.now().isoformat()
                        session['boot_id'] = app.boot_id  # bind session to current boot
                        session.permanent = True

                        # Track login in history (username + IP + user_agent if exists; timestamps)
                        try:
                            lh_kwargs = {}
                            if _lh_has("user_id"):     lh_kwargs["user_id"] = user.id
                            if _lh_has("username"):    lh_kwargs["username"] = user.username
                            # ip column name can be 'ip' or 'ip_address' depending on schema
                            client_ip = _client_ip(request)
                            if _lh_has("ip_address"):
                                lh_kwargs["ip_address"] = client_ip
                            elif _lh_has("ip"):
                                lh_kwargs["ip"] = client_ip
                            # store user_agent if the column exists — but we won't expose it in API
                            if _lh_has("user_agent"):
                                lh_kwargs["user_agent"] = request.headers.get("User-Agent")
                            if _lh_has("login_time"):  lh_kwargs["login_time"] = _now()
                            if _lh_has("success"):     lh_kwargs["success"] = True

                            if lh_kwargs:  # only if at least one column exists
                                lh = LoginHistory(**lh_kwargs)
                                s.add(lh)
                                s.flush()
                                session['login_history_id'] = getattr(lh, "id", None)
                        except Exception as e:
                            # IMPORTANT: rollback this session to clear "failed" state,
                            # otherwise the context manager will raise PendingRollbackError on commit.
                            try:
                                s.rollback()
                            except Exception:
                                pass
                            logger.warning(f"Login history insert failed: {e}")

                        # Update last_login if column exists (non-critical)
                        try:
                            if hasattr(user, "last_login"):
                                user.last_login = _now()
                        except Exception:
                            pass

                        logger.info(f"✅ Login success: {username}")
                        next_page = request.args.get('next')
                        return redirect(next_page or '/')
            else:
                # Fallback auth: single admin account
                if username == 'admin' and password == 'admin123':
                    from flask_login import UserMixin
                    class SimpleUser(UserMixin):
                        def __init__(self, username):
                            self.id = username
                            self.username = username
                            self.role = 'admin'
                            self.is_active = True
                    user = SimpleUser(username)
                    login_user(user, remember=False)
                    session['boot_id'] = app.boot_id  # bind fallback session to current boot
                    logger.info(f"✅ Basic login success: {username}")
                    next_page = request.args.get('next')
                    return redirect(next_page or '/')

            logger.warning(f"❌ Login failed: {username}")
            error = "Invalid credentials"
        else:
            error = None

        # Prefer file template; fallback to inline template
        try:
            return render_template('auth/login.html', error=error)
        except Exception:
            return render_template_string(LOGIN_TEMPLATE, error=error)

    @app.route('/logout')
    @login_required
    def logout():
        """Record logout time and clear session."""
        username = getattr(current_user, 'username', 'unknown')

        # Update logout_time on last LoginHistory row for this session
        if app.auth_db_session:
            try:
                lh_id = session.get("login_history_id")
                if lh_id and _lh_has("logout_time"):
                    with db() as s:
                        lh = s.get(LoginHistory, int(lh_id))
                        if lh and not getattr(lh, "logout_time", None):
                            lh.logout_time = _now()
            except Exception as e:
                logger.warning(f"Logout history update failed: {e}")

        logout_user()
        session.clear()
        logger.info(f"👋 Logout: {username}")
        return redirect(url_for('login'))

    # Allow favicon without auth (avoid 500 on /favicon.ico with login_required)
    @app.route('/favicon.ico')
    def favicon():
        return Response(status=204)

    # ---------- Admin helpers ----------
    def require_admin():
        """Abort with 403 when the current user is not admin."""
        if not (hasattr(current_user, 'role') and current_user.role == 'admin'):
            abort(403, description="Admin only")

    # ---------- JSON APIs for dashboard ----------
    @app.route('/admin/api/stats')
    @login_required
    def api_stats():
        """Return counters for dashboard cards."""
        require_admin()
        if not app.auth_db_session:
            return jsonify({"error": "auth DB disabled"}), 501
        with db() as s:
            total = s.query(User).count()
            active = s.query(User).filter_by(is_active=True).count()
            admins = s.query(User).filter_by(role='admin').count()
            twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_q = 0
            try:
                if _lh_has("login_time"):
                    recent_q = s.query(LoginHistory).filter(LoginHistory.login_time >= twenty_four_hours_ago).count()
            except Exception:
                recent_q = 0
            return jsonify({
                "total_users": total,
                "active_users": active,
                "admin_users": admins,
                "recent_logins": recent_q
            })

    @app.route('/admin/api/users', methods=['GET', 'POST'])
    @login_required
    def api_users():
        """List users (paginated) or create a new user."""
        require_admin()
        if not app.auth_db_session:
            return jsonify({"error": "auth DB disabled"}), 501

        with db() as s:
            if request.method == 'GET':
                q = s.query(User)
                search = request.args.get('q')
                if search:
                    q = q.filter(User.username.ilike(f"%{search}%"))
                page = int(request.args.get('page', 1))
                size = int(request.args.get('size', 20))
                total = q.count()
                users = q.order_by(User.id.desc()).offset((page - 1) * size).limit(size).all()
                return jsonify({
                    "total": total,
                    "page": page,
                    "size": size,
                    "items": [user_to_dict(u) for u in users]
                })

            # POST -> create user
            data = request.get_json(force=True)
            username = (data.get('username') or '').strip()
            email = (data.get('email') or '').strip()
            role = data.get('role') or 'user'
            password = data.get('password') or ''
            is_active = bool(data.get('is_active', True))

            if not username or not password:
                return jsonify({"error": "username and password are required"}), 400

            if s.query(User).filter_by(username=username).first():
                return jsonify({"error": "username already taken"}), 409

            u = User(username=username, email=email, role=role, is_active=is_active)
            if hasattr(u, 'set_password'):
                u.set_password(password)
            elif hasattr(u, 'password_hash'):
                from werkzeug.security import generate_password_hash
                u.password_hash = generate_password_hash(password)
            else:
                return jsonify({"error": "User model has no password setter"}), 500

            if hasattr(u, "created_at") and not u.created_at:
                u.created_at = _now()

            s.add(u)
            s.flush()
            return jsonify(user_to_dict(u)), 201

    @app.route('/admin/api/users/<int:user_id>', methods=['GET', 'PATCH', 'DELETE'])
    @login_required
    def api_user_detail(user_id):
        """Get / Update / Delete one user."""
        require_admin()
        if not app.auth_db_session:
            return jsonify({"error": "auth DB disabled"}), 501

        with db() as s:
            u = s.get(User, user_id)
            if not u:
                return jsonify({"error": "user not found"}), 404

            if request.method == 'GET':
                return jsonify(user_to_dict(u))

            if request.method == 'PATCH':
                data = request.get_json(force=True)

                if 'email' in data: u.email = (data['email'] or '').strip()
                if 'role' in data: u.role = data['role'] or u.role
                if 'is_active' in data: u.is_active = bool(data['is_active'])
                if 'password' in data and data['password']:
                    if hasattr(u, 'set_password'):
                        u.set_password(data['password'])
                    elif hasattr(u, 'password_hash'):
                        from werkzeug.security import generate_password_hash
                        u.password_hash = generate_password_hash(data['password'])
                if 'password_change_required' in data and hasattr(u, 'password_change_required'):
                    u.password_change_required = bool(data['password_change_required'])

                return jsonify(user_to_dict(u))

            # DELETE
            s.delete(u)
            return jsonify({"status": "deleted", "id": user_id})

    @app.route('/admin/api/users/<int:user_id>/reset-password', methods=['POST'])
    @login_required
    def api_user_reset_password(user_id):
        """Reset a user's password."""
        require_admin()
        if not app.auth_db_session:
            return jsonify({"error": "auth DB disabled"}), 501
        data = request.get_json(force=True) or {}
        new_pw = data.get("password")
        change_required = bool(data.get("password_change_required", True))
        if not new_pw:
            return jsonify({"error": "password is required"}), 400
        with db() as s:
            u = s.get(User, user_id)
            if not u:
                return jsonify({"error": "user not found"}), 404
            if hasattr(u, "set_password"):
                u.set_password(new_pw)
            elif hasattr(u, "password_hash"):
                from werkzeug.security import generate_password_hash
                u.password_hash = generate_password_hash(new_pw)
            if hasattr(u, "password_change_required"):
                u.password_change_required = change_required
            return jsonify({"status": "ok"})

    @app.route('/admin/api/login-history', methods=['GET'])
    @login_required
    def api_login_history():
        """List login history (username + email + ip + times; user_agent is stored but NOT exposed)."""
        require_admin()
        if not app.auth_db_session:
            return jsonify({"error": "auth DB disabled"}), 501

        with db() as s:
            q = s.query(LoginHistory)
            user = request.args.get('user')
            if user:
                if user.isdigit() and _lh_has("user_id"):
                    q = q.filter(LoginHistory.user_id == int(user))
                elif _lh_has("username"):
                    q = q.filter(LoginHistory.username == user)

            since = request.args.get('since')  # ISO 8601
            if since and _lh_has("login_time"):
                try:
                    dt = datetime.fromisoformat(since)
                    q = q.filter(LoginHistory.login_time >= dt)
                except Exception:
                    pass

            page = int(request.args.get('page', 1))
            size = int(request.args.get('size', 50))
            total = q.count()
            rows = q.order_by(LoginHistory.id.desc()).offset((page - 1) * size).limit(size).all()

            # Batch load emails for all user_ids present to avoid N+1
            email_by_user_id = {}
            try:
                user_ids = [getattr(h, "user_id", None) for h in rows]
                user_ids = [uid for uid in user_ids if isinstance(uid, int)]
                if user_ids:
                    result = s.query(User.id, User.email).filter(User.id.in_(set(user_ids))).all()
                    email_by_user_id = {uid: mail for (uid, mail) in result}
            except Exception:
                email_by_user_id = {}

            items = []
            for h in rows:
                uid = getattr(h, "user_id", None)
                email_value = email_by_user_id.get(uid) if isinstance(uid, int) else None
                items.append(history_to_dict(h, email_value=email_value))

            return jsonify({
                "total": total,
                "page": page,
                "size": size,
                "items": items
            })

    # ---------- HTML pages (render templates) ----------
    @app.route('/admin')
    @login_required
    def admin_dashboard():
        """Render dashboard page."""
        require_admin()
        try:
            return render_template('admin/dashboard.html')
        except Exception:
            # Very small fallback when template missing
            return "<h1>Admin Dashboard</h1><p>Template not found.</p>"

    @app.route('/admin/users')
    @login_required
    def admin_users_page():
        """Render users management page."""
        require_admin()
        return render_template('admin/users.html')

    @app.route('/admin/login_history')
    @login_required
    def admin_login_history_page():
        """Render login history page."""
        require_admin()
        return render_template('admin/login_history.html')

    # ---------- Health ----------
    @app.route('/health')
    def health():
        return jsonify({
            'status': 'ok',
            'backend': f'http://127.0.0.1:{backend_port}',
            'auth': 'enabled'
        })

    # ---------- Proxy to MLflow (requires auth) ----------
    @app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    @login_required
    def proxy_to_mlflow(path):
        """Authenticated reverse proxy to the MLflow backend."""
        # Redirect admin root to dashboard for convenience
        if not path and hasattr(current_user, 'role') and current_user.role == 'admin':
            return redirect('/admin')

        import requests
        backend_url = f"http://127.0.0.1:{backend_port}/{path}"

        try:
            method = request.method
            headers = dict(request.headers)
            data = request.get_data()
            params = request.args

            resp = requests.request(
                method, backend_url, params=params, data=data, headers=headers, timeout=30
            )
            return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Proxy error: {e}")
            return f"Error contacting MLflow backend: {e}", 502

    return app


def create_admin_user():
    """Create default admin user (admin/admin123) if none exists."""
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "mlflow_auth.db"

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))
        from mlflow_auth.auth.models import Base, User
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            existing_admin = s.query(User).filter_by(role="admin").first()
            if not existing_admin:
                admin = User(
                    username="admin",
                    email="admin@mlflow.local",
                    role="admin",
                    is_active=True
                )
                admin.set_password("admin123")
                if hasattr(admin, 'password_change_required'):
                    admin.password_change_required = False
                s.add(admin)
                s.commit()
                print("👤 Admin created: admin / admin123")
            else:
                print("👤 Admin already exists")

    except Exception as e:
        print(f"⚠️ Admin creation error: {e}")
        print("   Fallback basic auth will be used (admin/admin123)")


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description='Start MLflow with authentication')
    parser.add_argument('--host', default='0.0.0.0', help='Flask host')
    parser.add_argument('--port', type=int, default=5000, help='Flask port')
    parser.add_argument('--no-auth', action='store_true', help='Disable authentication layer')
    parser.add_argument('--backend-port', type=int, default=5001, help='MLflow backend port')
    args = parser.parse_args()

    print("🔐 MLflow with Authentication")
    print("=" * 40)

    load_environment()

    # No-auth mode: direct MLflow
    if args.no_auth:
        print("⚠️ Starting MLflow WITHOUT authentication")
        cmd = [
            sys.executable, "-m", "mlflow", "server",
            "--host", args.host,
            "--port", str(args.port),
            "--serve-artifacts"
        ]
        subprocess.run(cmd)
        return 0

    # Ensure admin exists
    create_admin_user()

    # Start MLflow backend
    mlflow_process, backend_port = start_mlflow_backend(args.backend_port)
    if not mlflow_process:
        logger.error("❌ Cannot start MLflow backend")
        return 1

    try:
        # Build auth app
        app = create_auth_app(backend_port)

        print(f"\n🌐 UI:    http://{args.host}:{args.port}")
        print(f"🛡️ Admin: http://{args.host}:{args.port}/admin")
        print("🔑 Login: admin / admin123")
        print("   (Ctrl+C to stop)")

        app.run(host=args.host, port=args.port, debug=False, use_reloader=False)

    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if mlflow_process:
            print("🛑 Stopping MLflow backend")
            mlflow_process.terminate()
            mlflow_process.wait()

    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Uncaught fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


