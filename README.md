# SIAKRED - Sistem Informasi Akreditasi UNISAN

Platform manajemen akreditasi terintegrasi untuk Universitas Ichsan Gorontalo (UNISAN).

## Fitur Utama

- Manajemen Sesi Akreditasi dengan periode multi-tahun (TS, TS-1, TS-2)
- Auto-collect dokumen sesuai instrumen & periode
- Timeline Gantt visual untuk milestone
- Dashboard executive dengan donut chart & stats
- Hybrid storage (local + Google Drive)
- Filter prodi by instrumen (mapping LAM/BAN-PT)
- Permission scope-based (Universitas/Fakultas/Prodi/Biro)
- Landing publik untuk transparansi dokumen FINAL
- Audit trail lengkap

## Tech Stack

- Backend: Django 6.0
- Database: PostgreSQL 18 (multi-schema)
- Frontend: Vanilla HTML/CSS/JS
- Server: Gunicorn + Nginx
- OS: Rocky Linux

## Setup Development

### Prerequisites
- Python 3.12+
- PostgreSQL 18+
- Git

### Install

```bash
git clone git@github.com:unisan-gtlo/akreditasi.git
cd akreditasi
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Akses: http://localhost:8000

## Setup Production

Lihat panduan lengkap di [DEPLOY.md](DEPLOY.md)

## License

Internal use - UNISAN

## Contact

PUSTIKOM UNISAN | https://unisan-g.id