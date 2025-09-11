# 🏥 Manajemen Praktik Pribadi

Aplikasi manajemen klinik berbasis web yang dirancang untuk mempermudah proses pelayanan pasien serta koordinasi staf (admin, dokter, resepsionis). Aplikasi ini membantu meningkatkan efisiensi, transparansi, dan kenyamanan dalam operasional klinik.

## ✨ Fitur Utama

### 👤 Pasien
- Registrasi/Login dengan Google
- Melengkapi profil pribadi
- Melihat jadwal tersedia
- Membuat janji temu
- Melihat riwayat pemeriksaan

### 🏥 Resepsionis
- Melihat daftar janji temu hari ini
- Check-in pasien
- Melihat daftar semua pasien dengan fitur pencarian
- Melihat dan mengelola slot jadwal

### 👨‍⚕️ Dokter
- Dashboard khusus untuk melihat antrean
- Ringkasan harian
- Membuka form rekam medis
- Menyimpan dan mengedit rekam medis pasien

### 🔐 Login Multi-Role
Selain pasien, tersedia login untuk Admin, Dokter, dan Resepsionis dengan hak akses berbeda.

### 📊 Riwayat & Statistik
Ringkasan jumlah pasien, slot tersedia, dan status pemeriksaan.

### ⚡ Otomatisasi Alur
Pasien bergerak otomatis dari antrean → siap diperiksa → selesai diperiksa.

### ⏰ Reset Data Harian
Data antrean otomatis direset setiap jam 04:00 pagi untuk menyesuaikan dengan jam operasional klinik.

## 🛠️ Teknologi yang Digunakan

- **Backend**: Flask (Python), Flask-Admin, Flask-Login
- **Database**: SQLAlchemy, Flask-Migrate (dengan SQLite)
- **Frontend**: Bootstrap 5, Jinja2, JavaScript
- **Autentikasi**: Google OAuth & Flask-Login (untuk staf)
- **Keamanan**: Flask-Bcrypt untuk keamanan password staf

## 🚀 Instalasi & Setup Lokal

Berikut adalah cara untuk menjalankan proyek ini di komputer lokal Anda.

### 1. Prasyarat
- Python 3.8+
- Git

### 2. Langkah-langkah Setup

#### Clone Repository
```bash
git clone [URL_REPOSITORY_ANDA]
cd [NAMA_FOLDER_PROYEK]
```

#### Buat dan Aktifkan Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

#### Install Dependencies
```bash
pip install -r requirements.txt
```
> **Catatan**: Anda perlu membuat file requirements.txt terlebih dahulu dengan perintah `pip freeze > requirements.txt`

#### Konfigurasi Environment Variables
Buat file bernama `.env` di folder utama proyek dan isi dengan kunci rahasia Anda:

```env
SECRET_KEY='kunci_rahasia_anda_yang_sangat_panjang'
GOOGLE_CLIENT_ID='client_id_anda_dari_google_console'
GOOGLE_CLIENT_SECRET='client_secret_anda_dari_google_console'
```

#### Inisialisasi Database
```bash
flask db upgrade
```

#### Buat Akun Staf Pertama Kali
Gunakan perintah CLI yang sudah kita buat untuk membuat akun dokter atau resepsionis:

```bash
# Contoh membuat akun dokter
flask create-staff nama_dokter password_dokter --role dokter

# Contoh membuat akun resepsionis
flask create-staff nama_resepsionis password_resepsionis --role resepsionis
```

#### Jalankan Aplikasi
```bash
flask run
```

Aplikasi akan berjalan di http://127.0.0.1:5000.

## 📄 Alur Penggunaan

### 👤 Alur Pasien
Login → Lengkapi Profil → Pilih Tanggal & Jam → Booking

### 🏥 Alur Resepsionis
Login → Lihat Janji Temu → Check-in Pasien

### 👨‍⚕️ Alur Dokter
Login → Lihat Pasien Berikutnya → Buka Rekam Medis → Isi & Simpan

## 📄 Lisensi

Proyek ini dilisensikan di bawah MIT License.

---

**Dibuat oleh Julius Lie**
