from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_admin import Admin
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth

# Buat semua objek ekstensi di sini
db = SQLAlchemy()
migrate = Migrate()
admin = Admin(template_mode='bootstrap4')
bcrypt = Bcrypt()
login_manager = LoginManager()
oauth = OAuth() 