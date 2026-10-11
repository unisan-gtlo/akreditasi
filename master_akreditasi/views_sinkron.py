"""
Pusat Sinkronisasi (khusus superadmin): tombol sinkron data dari SI-OBE, SIMDA,
dan portal. Proses berjalan di latar belakang (command `sinkron`), status
dipantau lewat Log Sinkronisasi.
"""
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models_sinkron import SinkronLog
from .sinkron import sedang_berjalan


def _superadmin(user):
    return user.is_authenticated and user.is_superuser


def _jalankan_latar(log_obj):
    """Jalankan `manage.py sinkron --log-id N` sebagai proses terpisah (tidak menunggu)."""
    manage = Path(settings.BASE_DIR) / "manage.py"
    try:
        subprocess.Popen(
            [sys.executable, str(manage), "sinkron", "--log-id", str(log_obj.pk)],
            cwd=str(settings.BASE_DIR),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
        return True
    except OSError as exc:
        log_obj.status = SinkronLog.Status.GAGAL
        log_obj.ringkasan = f"Gagal menjalankan proses latar: {exc}"[:500]
        log_obj.selesai = timezone.now()
        log_obj.save()
        return False


def _statistik():
    from dokumen.models import Dokumen, DokumenRevisi
    from dokumen.siobe_rps import MARKER, prodi_dengan_butir_rps
    from sesi.models import SesiAkreditasi

    from .models import MappingProdiInstrumen
    from .models_dosen_link import DTPSDosenSesi

    rev_aktif = DokumenRevisi.objects.filter(aktif=True, dokumen__status=Dokumen.Status.FINAL)
    sesi_aktif = SesiAkreditasi.objects.exclude(status__in=["SELESAI", "DIBATALKAN"]).order_by("kode_prodi")
    ditinjau = list(
        DTPSDosenSesi.objects.filter(sesi__in=sesi_aktif, aktif=True, perlu_ditinjau=True)
        .select_related("sesi").order_by("sesi__kode_prodi", "dosen_nama_snapshot")
    )
    tautan = rev_aktif.filter(storage_type=DokumenRevisi.StorageType.LINK)
    maps = MappingProdiInstrumen.objects.filter(aktif=True).order_by("kode_prodi")
    return {
        "rps_dokumen": rev_aktif.filter(catatan_revisi__startswith=MARKER).count(),
        "vmts_terisi": _vmts_terisi(),
        "rps_prodi": prodi_dengan_butir_rps(),
        "sesi_aktif": [
            {"sesi": s, "dtps": DTPSDosenSesi.objects.filter(sesi=s, aktif=True).count()} for s in sesi_aktif
        ],
        "dtps_ditinjau": ditinjau,
        "tautan_total": tautan.count(),
        "tautan_rusak": list(tautan.filter(is_link_broken=True).select_related("dokumen__butir_dokumen")),
        "portal_ada": [m for m in maps if m.portal_slug],
        "portal_kosong": [m for m in maps if not m.portal_slug],
    }


def _vmts_terisi():
    from core.models import FakultasProfile, ProdiProfile
    return {
        "fakultas": FakultasProfile.objects.exclude(visi="").count(),
        "prodi": ProdiProfile.objects.exclude(visi="").count(),
    }


def _terakhir(jenis):
    return SinkronLog.objects.filter(jenis__in=[jenis, SinkronLog.Jenis.SEMUA], lingkup="").first()


@user_passes_test(_superadmin, login_url="/app/")
def pusat_sinkron(request):
    kartu = [
        {"jenis": "RPS", "judul": "📚 RPS SI-OBE",
         "ket": "RPS yang disahkan di SI-OBE -> dokumen per mata kuliah (U2.01/U5.09) & MK penciri."},
        {"jenis": "DTPS", "judul": "👥 DTPS & Data Dosen SIMDA",
         "ket": "Tambah dosen homebase baru ke sesi aktif, perbarui snapshot, tandai dosen yang perlu ditinjau."},
        {"jenis": "TAUTAN", "judul": "🌐 Tautan Aplikasi & Portal",
         "ket": "Tautan LMS, SIAKAD, SIAMI, Digital Library, Portal UNISAN & Alumni; cek ulang tautan mati."},
        {"jenis": "VMTS", "judul": "🎯 VMTS SIMDA",
         "ket": "Visi, misi, tujuan, sasaran universitas/fakultas/prodi + profil lulusan dari SIMDA (sama dengan portal)."},
        {"jenis": "CACHE", "judul": "🧹 Cache",
         "ket": "Bersihkan cache beranda publik, sidebar, kelengkapan SIMDA, badge notifikasi."},
    ]
    for k in kartu:
        k["terakhir"] = _terakhir(k["jenis"])
        k["berjalan"] = sedang_berjalan(k["jenis"])
    context = {
        "page_title": "Pusat Sinkronisasi",
        "active_menu": "sinkron",
        "kartu": kartu,
        "berjalan": sedang_berjalan(SinkronLog.Jenis.SEMUA),
        "riwayat": SinkronLog.objects.select_related("dipicu_oleh")[:25],
        "stat": _statistik(),
    }
    return render(request, "master_akreditasi/sinkron.html", context)


@user_passes_test(_superadmin, login_url="/app/")
@require_POST
def sinkron_jalankan(request):
    jenis = request.POST.get("jenis", "SEMUA").upper()
    prodi = request.POST.get("prodi", "").strip().upper()[:20]
    kembali = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(kembali, allowed_hosts={request.get_host()}):
        kembali = ""
    kembali = kembali or "master_akreditasi:sinkron_home"

    if jenis not in SinkronLog.Jenis.values:
        messages.error(request, "Jenis sinkron tidak dikenal.")
        return redirect(kembali)
    bentrok = sedang_berjalan(jenis)
    if bentrok:
        messages.warning(request, f"Sinkron {bentrok.get_jenis_display()} masih berjalan (mulai "
                                  f"{timezone.localtime(bentrok.mulai):%H:%M}). Tunggu sampai selesai.")
        return redirect(kembali)
    log_obj = SinkronLog.objects.create(jenis=jenis, lingkup=prodi, sumber="TOMBOL", dipicu_oleh=request.user)
    if _jalankan_latar(log_obj):
        messages.success(request, f"Sinkron {log_obj.get_jenis_display()}"
                                  f"{' prodi ' + prodi if prodi else ''} dimulai di latar belakang. "
                                  f"Status diperbarui otomatis.")
    else:
        messages.error(request, log_obj.ringkasan)
    return redirect(kembali)


@user_passes_test(_superadmin, login_url="/app/")
def sinkron_status(request):
    """JSON status log aktif & terbaru (untuk pembaruan otomatis halaman)."""
    ids = [int(i) for i in request.GET.get("ids", "").split(",") if i.isdigit()][:20]
    qs = SinkronLog.objects.filter(pk__in=ids) if ids else SinkronLog.objects.all()[:5]
    return JsonResponse({"logs": [
        {"id": s.pk, "status": s.status, "status_label": s.get_status_display(), "ringkasan": s.ringkasan,
         "aktif": s.aktif, "output_tail": s.output[-1500:]}
        for s in qs
    ]})


@user_passes_test(_superadmin, login_url="/app/")
def sinkron_log_detail(request, pk):
    log_obj = get_object_or_404(SinkronLog.objects.select_related("dipicu_oleh"), pk=pk)
    return render(request, "master_akreditasi/sinkron_log.html", {
        "page_title": f"Log Sinkron #{log_obj.pk}", "active_menu": "sinkron", "log": log_obj,
    })
