# SIAKRED — Sistem Informasi Arsip Akreditasi

**Universitas Ichsan Gorontalo (UNISAN)**
UNISAN Digital Campus — Fase 2.7

## Deskripsi
Sistem pengarsipan dokumen akreditasi program studi multi-instrumen (BAN-PT IAPS 4.0 & LAM). Dokumen dikelompokkan berdasarkan Standar, Sub-Standar, dan Kategori Kepemilikan (Universitas, Biro/Lembaga, Fakultas, Prodi).

## Tech Stack
- Python 3.12
- Django 6.x
- PostgreSQL 18 (schema: akreditasi)
- Integrasi SSO UNISAN + SIMDA

## Quick Start (Development)
\\\powershell
cd C:\unisan\akreditasi
.\venv\Scripts\Activate.ps1
python manage.py runserver
\\\

## Struktur App
- core — Helper, SSO middleware, permissions
- master_akreditasi — Instrumen, Standar, SubStandar, ButirDokumen
- dokumen — DokumenAkreditasi, upload, preview, verifikasi
- sesi — SesiAkreditasi, tim, progress
- sesor — Portal asesor, audit log
- laporan — Laporan & export

## Domain Production
https://akreditasi.unisan-g.id

© 2026 Pustikom — UNISAN
"# akreditasi" 
