import enum
import uuid
from datetime import datetime
from extensions import db, login_manager, bcrypt
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Enum untuk peran staf
class UserRole(enum.Enum):
    ADMIN = 'admin'
    DOKTER = 'dokter'
    RESEPSIONIS = 'resepsionis'

# Model untuk akun pasien (login via Google)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    picture = db.Column(db.String(255))
    patient = db.relationship('Patient', backref='user', uselist=False, cascade="all, delete-orphan")

# Model untuk data diri pasien
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    nama = db.Column(db.String(100))
    telepon = db.Column(db.String(20))
    tanggal_lahir = db.Column(db.Date)
    tujuan = db.Column(db.String(255))
    appointments = db.relationship('Appointment', backref='patient', lazy=True)
    medical_records = db.relationship('MedicalRecord', backref='patient', lazy=True)

    @property
    def age(self):
        if not self.tanggal_lahir:
            return None
        today = datetime.today().date()
        return today.year - self.tanggal_lahir.year - ((today.month, today.day) < (self.tanggal_lahir.month, self.tanggal_lahir.day))

# Model untuk akun staf (login via username/password)
@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

class AdminUser(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.RESEPSIONIS)

    def set_password(self, password):
        # Gunakan bcrypt yang sudah kita import
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        # Gunakan bcrypt yang sudah kita import
        return bcrypt.check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

# Model untuk slot waktu
class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False)
    is_booked = db.Column(db.Boolean, default=False, nullable=False)
    appointment = db.relationship('Appointment', backref='slot', uselist=False)

# Model untuk janji temu
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    slot_id = db.Column(db.Integer, db.ForeignKey('slot.id'), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    medical_record = db.relationship('MedicalRecord', backref='appointment', uselist=False)
    
    # Kolom yang sudah ada
    checked_in = db.Column(db.Boolean, default=False, nullable=False)
    
    # TAMBAHAN BARU: Kolom berat badan dan tekanan darah
    berat_badan = db.Column(db.Float, nullable=True)  # dalam kg
    tekanan_darah_sistol = db.Column(db.Integer, nullable=True)  # mmHg
    tekanan_darah_diastol = db.Column(db.Integer, nullable=True)  # mmHg

    @property
    def tekanan_darah_formatted(self):
        """Format tekanan darah menjadi string seperti '120/80'"""
        if self.tekanan_darah_sistol and self.tekanan_darah_diastol:
            return f"{self.tekanan_darah_sistol}/{self.tekanan_darah_diastol}"
        return "-"

# Model untuk rekam medis
class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False, unique=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    tanggal_periksa = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    anamnesa = db.Column(db.Text)
    diagnosa = db.Column(db.Text)
    terapi = db.Column(db.Text)