import os
import json
from enum import Enum
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO

import click
import qrcode
from authlib.integrations.flask_client import OAuth
from flask import (
    Flask, flash, redirect, render_template, request, session,
    url_for, jsonify, send_file, Blueprint
)
from flask_admin.base import AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user, login_user, logout_user, login_required
from markupsafe import Markup
from sqlalchemy import func

# Lokal imports
from extensions import db, migrate, admin, bcrypt, login_manager, oauth
from models import User, Patient, Slot, Appointment, MedicalRecord, AdminUser, UserRole

# =======================================================================
# 1. HELPER & DECORATOR
# =======================================================================
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


def profile_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        patient = Patient.query.filter_by(user_id=session['user']['id']).first()
        if not patient or not patient.telepon:
            flash("Harap lengkapi data diri Anda terlebih dahulu.", "info")
            return redirect(url_for('lengkapi_profil'))
        return f(*args, **kwargs)
    return decorated_function


# =======================================================================
# 2. FLASK-ADMIN VIEWS
# =======================================================================
scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/admin/scheduler')

@scheduler_bp.route('/generate', methods=['POST'])
@login_required
def generate_slots_action():
    try:
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
        duration = int(request.form['duration'])
        
        generated_count = 0
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:
                current_dt = datetime.combine(current_date, start_time)
                end_dt = datetime.combine(current_date, end_time)
                
                while current_dt < end_dt:
                    exists = Slot.query.filter_by(start_time=current_dt).first()
                    if not exists:
                        new_slot = Slot(start_time=current_dt, is_booked=False)
                        db.session.add(new_slot)
                        generated_count += 1
                    current_dt += timedelta(minutes=duration)
            
            current_date += timedelta(days=1)
            
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f"{generated_count} slot baru berhasil dibuat!"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}), 500

@scheduler_bp.route('/shift-time', methods=['POST'])
@login_required
def shift_time_action():
    shift_date_str = request.form['shift_date']
    minutes_to_shift = int(request.form['minutes_to_shift'])

    shift_date = datetime.strptime(shift_date_str, '%Y-%m-%d').date()
    start_of_day = datetime.combine(shift_date, datetime.min.time())
    end_of_day = datetime.combine(shift_date, datetime.max.time())

    slots_to_shift = Slot.query.filter(
        Slot.start_time.between(start_of_day, end_of_day),
        Slot.is_booked == False
    ).order_by(Slot.start_time.asc()).all()

    shifted_count = 0
    for slot in slots_to_shift:
        slot.start_time += timedelta(minutes=minutes_to_shift)
        shifted_count += 1

    db.session.commit()
    flash(f"{shifted_count} slot pada tanggal {shift_date_str} berhasil dimundurkan.", "success")
    return redirect(url_for('schedule_tool.index'))

@scheduler_bp.route('/reschedule-day', methods=['POST'])
@login_required
def reschedule_day_action():
    reschedule_date_str = request.form['reschedule_date']
    reschedule_date = datetime.strptime(reschedule_date_str, '%Y-%m-%d').date()

    # Temukan hari kerja berikutnya
    next_workday = reschedule_date + timedelta(days=1)
    while next_workday.weekday() >= 5: # Lewati Sabtu (5) dan Minggu (6)
        next_workday += timedelta(days=1)

    start_of_day = datetime.combine(reschedule_date, datetime.min.time())
    end_of_day = datetime.combine(reschedule_date, datetime.max.time())

    slots_to_reschedule = Slot.query.filter(
        Slot.start_time.between(start_of_day, end_of_day),
        Slot.is_booked == False
    ).all()

    # Cek apakah ada pasien yang sudah booking di hari itu
    booked_appointments = Appointment.query.join(Slot).filter(
        Slot.start_time.between(start_of_day, end_of_day)
    ).count()

    if booked_appointments > 0:
        flash(f"Tidak bisa memundurkan hari. Terdapat {booked_appointments} pasien yang sudah terdaftar pada tanggal {reschedule_date_str}. Harap batalkan manual.", "danger")
        return redirect(url_for('scheduler.index'))

    rescheduled_count = 0
    for slot in slots_to_reschedule:
        # Pindahkan ke hari kerja berikutnya dengan jam yang sama
        slot.start_time = slot.start_time.replace(
            year=next_workday.year, 
            month=next_workday.month, 
            day=next_workday.day
        )
        rescheduled_count += 1

    db.session.commit()
    flash(f"{rescheduled_count} slot dari tanggal {reschedule_date_str} berhasil dipindahkan ke {next_workday.strftime('%Y-%m-%d')}.", "success")
    return redirect(url_for('schedule_tool.index'))

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin_login'))
        if current_user.role.value == 'dokter':
            return redirect(url_for('doctor_dashboard.index'))
        if current_user.role.value == 'resepsionis':
            return redirect(url_for('receptionist.index'))
        return self.render('admin_dashboard.html', **kwargs)


class UserView(ModelView):
    column_list = ('name', 'email', 'patient.telepon')
    column_labels = {'patient.telepon': 'No. Telepon Pasien'}
    can_create = False
    can_edit = False

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value == 'admin' # <-- DIPERBAIKI


class AppointmentView(ModelView):
    column_list = ('patient', 'slot.start_time', 'booking_uuid')
    column_labels = {'patient': 'Nama Pasien', 'slot.start_time': 'Waktu Janji Temu'}
    can_create = False
    can_edit = False

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value == 'admin' # <-- DIPERBAIKI


class PatientView(ModelView):
    column_list = ('nama', 'telepon', 'user.email')
    column_labels = {'nama': 'Nama Pasien', 'telepon': 'No. Telepon', 'user.email': 'Email Akun'}
    column_searchable_list = ('nama', 'telepon')
    can_delete = False
    actions_disallowed_list = ['delete']

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value in ['admin', 'dokter', 'resepsionis'] # <-- DIPERBAIKI


class SlotView(ModelView):
    # TAMBAHKAN BARIS INI
    form_excluded_columns = ['appointment']

    column_list = ('start_time', 'is_booked')
    column_filters = ['is_booked', 'start_time']
    column_formatters = {
        'start_time': lambda v, c, m, p: m.start_time.strftime('%A, %d %b %Y - %H:%M')
    }

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value in ['admin', 'resepsionis']


class MedicalRecordView(ModelView):
    edit_template = 'admin/medical_record_edit.html'
    form_columns = ['anamnesa', 'diagnosa', 'terapi']
    
    can_create = True
    can_view_details = True
    can_edit = True

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value in ['admin', 'dokter']

    # --- KITA GANTI METODE RENDER DENGAN YANG LEBIH BAIK ---
    def on_form_prefill(self, form, id):
        # Metode ini lebih aman untuk mengisi data tambahan saat edit
        model = self.get_one(id)
        if model:
            form.patient_name = model.patient.nama
            form.patient_age = model.patient.age
            # Anda bisa menambahkan data lain di sini jika perlu

    # --- TAMBAHKAN METODE BARU INI UNTUK MENANGANI PEMBUATAN REKOD BARU ---
    def create_model(self, form):
        try:
            # 1. Buat instance model kosong
            model = self.model()
            # 2. Isi dengan data dari form (anamnesa, diagnosa, terapi)
            form.populate_obj(model)
            
            # 3. Ambil ID dari hidden input yang kita kirim
            appointment_id = request.form.get('appointment')
            patient_id = request.form.get('patient')

            # 4. Validasi dan isi foreign key yang hilang
            if not appointment_id or not patient_id:
                flash('ID Janji Temu atau Pasien tidak valid.', 'danger')
                return False
            
            model.appointment_id = int(appointment_id)
            model.patient_id = int(patient_id)

            # 5. Simpan model yang sudah lengkap ke database
            self.session.add(model)
            self._on_model_change(form, model, True)
            self.session.commit()
            return True # Beritahu Flask-Admin bahwa proses berhasil

        except Exception as ex:
            if not self.handle_view_exception(ex):
                flash(f'Gagal membuat rekam medis. Error: {str(ex)}', 'error')
            self.session.rollback()
            return False

    def render(self, template, **kwargs):
        # Tambahkan data pasien saat berada di halaman edit
        if template == self.edit_template:
            model = kwargs.get('model')
            if model:
                kwargs['patient'] = model.patient
        
        return super(MedicalRecordView, self).render(template, **kwargs)

class DoctorDashboardView(BaseView):
    @expose('/')
    def index(self):
        now = datetime.now()
        if now.hour < 4:
            start_of_day = now.replace(hour=4, minute=0, second=0, microsecond=0) - timedelta(days=1)
            end_of_day = now.replace(hour=3, minute=59, second=59, microsecond=0)
        else:
            start_of_day = now.replace(hour=4, minute=0, second=0, microsecond=0)
            end_of_day = (now + timedelta(days=1)).replace(hour=3, minute=59, second=59, microsecond=0)
        
        appointments_today = Appointment.query.join(Slot).filter(Slot.start_time.between(start_of_day, end_of_day)).all()
        slots_available_today = Slot.query.filter(Slot.start_time.between(start_of_day, end_of_day), Slot.is_booked == False).count()
        total_registered = len(appointments_today)
        total_handled = sum(1 for app in appointments_today if app.medical_record is not None)
        percentage_handled = round((total_handled / total_registered) * 100) if total_registered > 0 else 0
        summary_data = {"available_slots": slots_available_today, "registered": total_registered, "percentage_handled": percentage_handled}
        antrean_pasien = Appointment.query.join(Slot).filter(Slot.start_time.between(start_of_day, end_of_day), Appointment.medical_record == None).order_by(Slot.start_time.asc()).all()
        pasien_siap_periksa = None
        sisa_antrean = []
        found_next = False
        for app in antrean_pasien:
            if app.checked_in and not found_next:
                pasien_siap_periksa = app
                found_next = True
            else:
                sisa_antrean.append(app)
        pasien_selesai_diperiksa = MedicalRecord.query.join(Appointment).join(Slot).filter(Slot.start_time.between(start_of_day, end_of_day)).order_by(MedicalRecord.tanggal_periksa.desc()).all()

        return self.render('dashboard_doctor.html', summary=summary_data, antrean=sisa_antrean, pasien_diperiksa=pasien_siap_periksa, riwayat_hari_ini=pasien_selesai_diperiksa)
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value == 'dokter'


class PatientManagementView(BaseView):
    @expose('/')
    def index(self):
        return self.render('patient_management.html')

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value in ['admin', 'dokter']

    def is_visible(self): return False
    
class ReceptionistPatientView(BaseView):
    @expose('/')
    def index(self):
        # Ambil query pencarian dari URL
        search_query = request.args.get('search', '')
        
        # Siapkan query dasar
        query = Patient.query.join(User)

        # Jika ada query pencarian, filter datanya
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    Patient.nama.ilike(search_term),
                    User.email.ilike(search_term),
                    db.cast(Patient.tanggal_lahir, db.String).ilike(search_term)
                )
            )

        # Ambil halaman saat ini untuk pagination, default ke halaman 1
        page = request.args.get('page', 1, type=int)
        # Tampilkan 10 pasien per halaman
        patients = query.order_by(Patient.nama.asc()).paginate(page=page, per_page=10)

        return self.render('_receptionist_patient_list_content.html', patients=patients, search_query=search_query)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value in ['admin', 'resepsionis']

    def is_visible(self):
        # Sembunyikan dari menu utama, kita akan akses via sidebar
        return False


class ReceptionistHomeView(BaseView):
    @expose('/')
    def index(self):
        # Kita gunakan logika waktu yang sama dengan dashboard dokter untuk konsistensi (reset jam 4 pagi)
        now = datetime.now()
        if now.hour < 4:
            start_of_day = now.replace(hour=4, minute=0, second=0, microsecond=0) - timedelta(days=1)
            end_of_day = now.replace(hour=3, minute=59, second=59, microsecond=0)
        else:
            start_of_day = now.replace(hour=4, minute=0, second=0, microsecond=0)
            end_of_day = (now + timedelta(days=1)).replace(hour=3, minute=59, second=59, microsecond=0)

        # Ambil semua janji temu untuk hari ini, urutkan berdasarkan waktu
        appointments_today = Appointment.query.join(Slot).filter(
            Slot.start_time.between(start_of_day, end_of_day)
        ).order_by(Slot.start_time.asc()).all()

        return self.render('receptionist_home.html', appointments=appointments_today)
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value == 'resepsionis'

    # TAMBAHKAN FUNGSI INI
    def is_visible(self):
        return False
    
class ReceptionistScheduleView(BaseView):
    @expose('/')
    def index(self):
        future_dates_query = db.session.query(func.date(Slot.start_time))\
            .filter(func.date(Slot.start_time) >= date.today())\
            .distinct()\
            .order_by(func.date(Slot.start_time).asc())\
            .all()

        available_days = []
        for i, d_tuple in enumerate(future_dates_query):
            day_item = d_tuple[0]
            if isinstance(day_item, str):
                day_item = datetime.strptime(day_item, '%Y-%m-%d').date()
            if day_item:
                available_days.append(day_item)
        
        return self.render('admin/_receptionist_schedule_content.html', available_days=available_days)
    
class ScheduleManagementView(BaseView):
    @expose('/')
    def index(self):
        return self.render('_schedule_tool_content.html')

    def is_accessible(self):
        return current_user.is_authenticated and current_user.role.value in ['admin', 'resepsionis']

    def is_visible(self):
        return False # Sembunyikan dari menu utama, kita akan akses via tombol


# =======================================================================
# 3. APPLICATION FACTORY
# =======================================================================
def create_app():
    app = Flask(__name__)
    app.json_encoder = CustomJSONEncoder

    # Konfigurasi
    app.config["SECRET_KEY"] = "ini-adalah-kunci-rahasia-yang-sangat-aman-dan-sulit-ditebak"
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'clinic.db')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["GOOGLE_CLIENT_ID"] = "784815780071-0af7ff4667q26s6lnoga4u33bn2q0ub2.apps.googleusercontent.com"
    app.config["GOOGLE_CLIENT_SECRET"] = "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"

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)
    admin.init_app(app, index_view=MyAdminIndexView(url="/admin"))
    admin.name = "Dashboard"
    
    # Tambahkan views ke admin
    admin.add_view(UserView(User, db.session, category="Manajemen Data"))
    admin.add_view(PatientView(Patient, db.session, category="Manajemen Data"))
    admin.add_view(AppointmentView(Appointment, db.session, category="Manajemen Data"))
    admin.add_view(SlotView(Slot, db.session, category="Manajemen Data"))
    admin.add_view(
    MedicalRecordView(MedicalRecord, db.session, endpoint="medicalrecord", category="Manajemen Data")
)
    admin.add_view(DoctorDashboardView(name="Dashboard Dokter", endpoint='doctor_dashboard'))
    admin.add_view(PatientManagementView(name="Manajemen Pasien", endpoint='patient_management'))
    admin.add_view(ReceptionistHomeView(name="Home Resepsionis", endpoint='receptionist'))
    admin.add_view(ScheduleManagementView(name="Alat Pengelola Jadwal", endpoint='schedule_tool'))
    admin.add_view(ReceptionistPatientView(name="Daftar Pasien Resepsionis", endpoint='receptionist_patients'))
    admin.add_view(ReceptionistScheduleView(name="Lihat Jadwal Slot", endpoint='receptionist_schedule'))
    app.register_blueprint(scheduler_bp)
    return app


# =======================================================================
# 4. APP INSTANCE & OAUTH
# =======================================================================
app = create_app()

google = oauth.register(
    name='google',
    client_id=app.config["GOOGLE_CLIENT_ID"],
    client_secret=app.config["GOOGLE_CLIENT_SECRET"],
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
    jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
)


# =======================================================================
# 5. ROUTES
# =======================================================================
@app.context_processor
def inject_staff_user():
    if current_user.is_authenticated and isinstance(current_user, AdminUser):
        return dict(current_staff=current_user)
    return dict(current_staff=None)

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# --- Pasien & Publik Routes ---
@app.route("/")
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route("/login")
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/authorize")
def authorize():
    token = google.authorize_access_token()
    user_info = google.get('userinfo').json()

    user = User.query.filter_by(google_sub=user_info['id']).first()
    if not user:
        new_user = User(
            google_sub=user_info['id'],
            name=user_info['name'],
            email=user_info['email'],
            picture=user_info['picture']
        )
        db.session.add(new_user)
        db.session.commit()
        new_patient = Patient(user_id=new_user.id, nama=new_user.name)
        db.session.add(new_patient)
        db.session.commit()
        user = new_user

    session['user'] = {
        'id': user.id, 'name': user.name,
        'email': user.email, 'picture': user.picture
    }
    return redirect(url_for('dashboard'))


@app.route("/logout")
def logout():
    session.pop('user', None)
    flash("Anda berhasil logout.", "success")
    return redirect(url_for('index'))


@app.route("/lengkapi-profil", methods=["GET", "POST"])
def lengkapi_profil():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['id']
    patient = Patient.query.filter_by(user_id=user_id).first()

    if request.method == "POST":
        nama = request.form.get("nama")
        telepon = request.form.get("telepon")
        tanggal_lahir_str = request.form.get("tanggal_lahir")
        tanggal_lahir = datetime.strptime(tanggal_lahir_str, '%Y-%m-%d').date() if tanggal_lahir_str else None

        tujuan = request.form.get("tujuan")
        if tujuan == "Lainnya":
            tujuan = request.form.get("tujuan_lainnya")

        if not patient:
            patient = Patient(user_id=user_id)
            db.session.add(patient)

        patient.nama = nama
        patient.telepon = telepon
        patient.tanggal_lahir = tanggal_lahir
        patient.tujuan = tujuan

        db.session.commit()

        flash("Profil Anda berhasil disimpan!", "success")
        return redirect(url_for("dashboard"))

    return render_template("lengkapi_profil.html", patient=patient)


@app.route("/dashboard", methods=["GET", "POST"])
@profile_required
def dashboard():
    user_id = session['user']['id']
    patient = Patient.query.filter_by(user_id=user_id).first()

    if request.method == "POST":
        slot_id = request.form.get("slot_id")
        if not slot_id:
            flash("Anda harus memilih jam janji temu.", "warning")
            return redirect(url_for('dashboard'))

        slot_to_book = Slot.query.get(slot_id)
        if slot_to_book and not slot_to_book.is_booked:
            slot_to_book.is_booked = True
            new_appointment = Appointment(
                user_id=user_id,
                patient_id=patient.id,
                slot_id=slot_to_book.id
            )
            db.session.add(new_appointment)
            db.session.commit()
            flash(f"Janji temu pada {slot_to_book.start_time.strftime('%d %b %Y, %H:%M')} berhasil dibuat!", "success")
        else:
            flash("Maaf, slot tersebut sudah terisi atau tidak valid.", "danger")
        return redirect(url_for("dashboard"))

    next_appointment = Appointment.query.join(Slot).filter(
        Appointment.patient_id == patient.id,
        Slot.start_time > datetime.now()
    ).order_by(Slot.start_time.asc()).first()

    today = date.today()
    fourteen_days_later = today + timedelta(days=14)

    # Query baru yang lebih andal
    results = db.session.query(
        Slot.start_time
    ).filter(
        Slot.is_booked == False,
        func.date(Slot.start_time).between(today, fourteen_days_later)
    ).order_by(Slot.start_time).all()

    # Proses hasilnya di Python untuk mendapatkan tanggal unik
    available_dates = sorted(list(set(d.start_time.date() for d in results)))

    history = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.medical_record != None
    ).join(Slot).order_by(Slot.start_time.desc()).all()

    return render_template(
        "dashboard.html",
        patient=patient,
        user=session['user'],
        next_appointment=next_appointment,
        available_dates=available_dates,
        history=history
    )


@app.route('/qr_code/<booking_uuid>')
def generate_qr_code(booking_uuid):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10, border=4
    )
    qr.add_data(booking_uuid)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


@app.route('/api/slots-for-date')
def get_slots_for_date():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify([])

    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    start_of_day = datetime.combine(selected_date, datetime.min.time())
    end_of_day = datetime.combine(selected_date, datetime.max.time())

    slots = Slot.query.filter(
        Slot.start_time.between(start_of_day, end_of_day),
        Slot.is_booked == False,
        Slot.start_time > datetime.now()
    ).order_by(Slot.start_time.asc()).all()

    return jsonify([
        {'id': s.id, 'time': s.start_time.strftime('%H:%M')}
        for s in slots
    ])
    
@app.route('/api/medical-record/<int:appointment_id>')
@profile_required
def get_medical_record(appointment_id):
    user_id = session['user']['id']
    patient = Patient.query.filter_by(user_id=user_id).first()

    # Validasi bahwa janji temu ini milik pasien yang sedang login
    appointment = Appointment.query.filter_by(id=appointment_id, patient_id=patient.id).first_or_404()

    if appointment and appointment.medical_record:
        record = appointment.medical_record
        return jsonify({
            "tanggal_periksa": record.tanggal_periksa.strftime('%A, %d %B %Y'),
            "anamnesa": record.anamnesa or "-",
            "diagnosa": record.diagnosa or "-",
            "terapi": record.terapi or "-"
        })
    
    return jsonify({"error": "Rekam medis tidak ditemukan"}), 404

@app.route('/api/dates-with-slots')
@login_required
def get_dates_with_slots():
    # Query untuk mengambil semua tanggal unik yang sudah memiliki slot
    results = db.session.query(func.date(Slot.start_time)).distinct().all()
    
    # Ubah hasilnya menjadi list of strings (format YYYY-MM-DD)
    dates_with_slots = [d[0].strftime('%Y-%m-%d') for d in results if d[0]]
    
    return jsonify(dates_with_slots)

@app.route('/api/slots-by-date')
@login_required
def get_slots_by_date():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "Parameter tanggal dibutuhkan"}), 400

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_of_day = datetime.combine(selected_date, datetime.min.time())
        end_of_day = datetime.combine(selected_date, datetime.max.time())
        
        slots_query = db.session.query(Slot).options(
            db.joinedload(Slot.appointment).joinedload(Appointment.patient)
        ).filter(
            Slot.start_time.between(start_of_day, end_of_day)
        ).order_by(
            Slot.start_time.asc()
        ).all()

        result = []
        for slot in slots_query:
            patient_name = None
            if slot.is_booked and slot.appointment and slot.appointment.patient:
                patient_name = slot.appointment.patient.nama

            result.append({
                'id': slot.id,
                'time': slot.start_time.strftime('%H:%M'),
                'is_booked': slot.is_booked,
                'patient_name': patient_name
            })
        
        return jsonify(result)

    except ValueError:
        return jsonify({"error": "Format tanggal tidak valid. Gunakan YYYY-MM-DD"}), 400
    except Exception as e:
        # Menambahkan logging error untuk debugging di server
        app.logger.error(f"Error fetching slots: {e}")
        return jsonify({"error": "Terjadi kesalahan di server"}), 500
    
# --- Admin Panel Routes ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        staff = AdminUser.query.filter_by(username=username).first()
        if staff and staff.check_password(password):
            login_user(staff)
            flash('Login berhasil!', 'success')
            return redirect(url_for('admin.index'))
        else:
            flash('Username atau password salah.', 'danger')

    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/check-in/<int:appointment_id>')
@login_required
def check_in_patient(appointment_id):
    # Pastikan hanya resepsionis yang bisa mengakses
    if current_user.role.value != 'resepsionis':
        flash('Anda tidak memiliki akses untuk melakukan aksi ini.', 'danger')
        return redirect(url_for('admin.index'))

    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment:
        appointment.checked_in = True
        db.session.commit()
        flash(f"Pasien '{appointment.patient.nama}' berhasil di check-in.", "success")
    else:
        flash("Janji temu tidak ditemukan.", "danger")
        
    return redirect(url_for('receptionist.index'))


# =======================================================================
# 6. CLI COMMANDS
# =======================================================================
@app.cli.command("create-staff")
@click.argument("username")
@click.argument("password")
@click.option('--role', type=click.Choice(['admin', 'dokter', 'resepsionis']), default='resepsionis')
def create_staff(username, password, role):
    existing_staff = AdminUser.query.filter_by(username=username).first()
    if existing_staff:
        print(f"Staf dengan username '{username}' sudah ada.")
        return

    new_staff = AdminUser(username=username, role=UserRole[role.upper()])
    new_staff.set_password(password)
    db.session.add(new_staff)
    db.session.commit()
    print(f"Staf '{username}' dengan peran '{role}' berhasil dibuat.")


# =======================================================================
# 7. MAIN
# =======================================================================
if __name__ == '__main__':
    app.run(debug=True)