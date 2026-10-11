"""
Pustaka Dokumen Institusi: daftar lintas sesi, tambah dokumen tanpa butir,
dan kelola Kategori Dokumen (superadmin/LPM). Aturan ada di dokumen/pustaka.py.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from master_akreditasi.models import Instrumen

from .forms import KategoriDokumenForm, PustakaDokumenForm
from .models import Dokumen, DokumenAccessLog, KategoriDokumen
from .pustaka import (
    EKSTENSI_DITERIMA,
    UKURAN_MAKS_MB,
    bangun_pustaka,
    can_access_pustaka,
    can_kelola_kategori,
    pilihan_pemilik,
    urai_pemilik,
)


def _tolak(request):
    messages.error(request, "Pustaka Dokumen hanya untuk pengguna internal kampus.")
    return redirect("core:dashboard")


@login_required
def pustaka_dokumen(request):
    """Semua dokumen Universitas/Rektorat, Biro/Lembaga, Fakultas tanpa masuk sesi."""
    if not can_access_pustaka(request.user):
        return _tolak(request)
    context = bangun_pustaka(request.GET, request.user)
    context.update({
        "active_menu": "pustaka",
        "instrumen_all": Instrumen.objects.order_by("nama_singkat"),
        "bisa_tambah": bool(pilihan_pemilik(request.user)),
        "bisa_kelola": can_kelola_kategori(request.user),
    })
    return render(request, "dokumen/pustaka.html", context)


@login_required
def pustaka_tambah(request):
    """Tambah dokumen arsip langsung di Pustaka (tidak terkait butir instrumen)."""
    if not can_access_pustaka(request.user):
        return _tolak(request)
    pilihan = pilihan_pemilik(request.user)
    if not pilihan:
        messages.error(request, "Akun Anda tidak punya peran Universitas, Biro/Lembaga, atau Fakultas untuk menambah dokumen.")
        return redirect("dokumen:pustaka")

    from .views import _create_gdrive_revisi, _create_link_revisi, _create_local_revisi, _get_client_ip

    if request.method == "POST":
        form = PustakaDokumenForm(request.POST, request.FILES, pilihan_pemilik=pilihan)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                with transaction.atomic():
                    dok = Dokumen.objects.create(
                        butir_dokumen=None,
                        **urai_pemilik(cd["pemilik"]),
                        judul=cd["judul"],
                        kategori=cd.get("kategori"),
                        nomor_dokumen=cd.get("nomor_dokumen", "").strip(),
                        tanggal_dokumen=cd.get("tanggal_dokumen"),
                        penerbit=cd.get("penerbit", "").strip(),
                        deskripsi=cd.get("deskripsi", "").strip(),
                        status_akses=cd["status_akses"],
                        tahun_akademik=cd.get("tahun_akademik", ""),
                        uploaded_by=request.user,
                        last_updated_by=request.user,
                    )
                    storage = cd.get("storage_type", "LOCAL")
                    buat = {"LOCAL": _create_local_revisi, "LINK": _create_link_revisi}.get(storage, _create_gdrive_revisi)
                    revisi = buat(dok, 1, form, request.user)
                    # Tautan tanpa kategori yang cocok (mis. bukan "Permendikbudristek ...") → Tautan Aplikasi
                    if storage == "LINK" and not cd.get("kategori") and (dok.kategori is None or dok.kategori.kode == "lainnya"):
                        aplikasi = KategoriDokumen.objects.filter(kode="aplikasi", aktif=True).first()
                        if aplikasi:
                            Dokumen.objects.filter(pk=dok.pk).update(kategori=aplikasi)
                    DokumenAccessLog.objects.create(
                        dokumen=dok, revisi=revisi, aksi=DokumenAccessLog.AksiType.UPLOAD, user=request.user,
                        ip_address=_get_client_ip(request),
                        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                        catatan="Ditambahkan lewat Pustaka Dokumen",
                    )
                messages.success(request, f"Dokumen '{dok.judul}' ditambahkan ke Pustaka.")
                from core.templatetags.navigasi import dengan_next
                from django.urls import reverse
                return redirect(dengan_next(reverse("dokumen:dokumen_detail", args=[dok.pk]), reverse("dokumen:pustaka")))
            except Exception as e:
                messages.error(request, f"Gagal menyimpan: {e}")
    else:
        form = PustakaDokumenForm(pilihan_pemilik=pilihan)

    return render(request, "dokumen/pustaka_tambah.html", {
        "active_menu": "pustaka",
        "form": form,
        "ukuran_maks": UKURAN_MAKS_MB,
        "ekstensi": ", ".join(e.lstrip(".").upper() for e in EKSTENSI_DITERIMA),
    })


@login_required
def kategori_kelola(request, pk=None):
    """Daftar kategori + form tambah/ubah (superadmin & LPM)."""
    if not can_kelola_kategori(request.user):
        messages.error(request, "Kelola kategori hanya untuk Super Admin dan LPM.")
        return redirect("dokumen:pustaka")
    obj = get_object_or_404(KategoriDokumen, pk=pk) if pk else None

    if request.method == "POST":
        form = KategoriDokumenForm(request.POST, instance=obj)
        if form.is_valid():
            k = form.save()
            messages.success(request, f"Kategori '{k.nama}' {'diperbarui' if obj else 'ditambahkan'}.")
            return redirect("dokumen:kategori_kelola")
    else:
        form = KategoriDokumenForm(instance=obj, initial=None if obj else {"urutan": 100, "aktif": True})

    from django.db.models import Count
    daftar = KategoriDokumen.objects.annotate(jumlah=Count("dokumen")).order_by("urutan", "nama")
    return render(request, "dokumen/pustaka_kategori.html", {
        "active_menu": "pustaka",
        "form": form,
        "obj": obj,
        "daftar": daftar,
    })


@login_required
@require_POST
def kategori_tebak_ulang(request):
    """Tebak ulang kategori dokumen yang masih 'Lainnya' (setelah kata kunci/kategori baru ditambah)."""
    if not can_kelola_kategori(request.user):
        messages.error(request, "Kelola kategori hanya untuk Super Admin dan LPM.")
        return redirect("dokumen:pustaka")
    from .pustaka import tebak_kategori_id

    pindah = 0
    for d in (Dokumen.objects.filter(kategori__kode="lainnya")
              .select_related("butir_dokumen").prefetch_related("revisi")):
        is_link = any(r.aktif and r.is_link for r in d.revisi.all())
        baru = tebak_kategori_id(d.judul, d.butir_dokumen.nama_dokumen if d.butir_dokumen_id else "", is_link)
        if baru and baru != d.kategori_id:
            Dokumen.objects.filter(pk=d.pk).update(kategori_id=baru)
            pindah += 1
    messages.success(request, f"Tebak ulang selesai: {pindah} dokumen 'Lainnya' dipindah ke kategori yang cocok.")
    return redirect("dokumen:kategori_kelola")


@login_required
@require_POST
def kategori_hapus(request, pk):
    """Hapus kategori. Bila masih dipakai, dokumennya dipindah ke kategori tujuan (wajib dipilih)."""
    if not can_kelola_kategori(request.user):
        messages.error(request, "Kelola kategori hanya untuk Super Admin dan LPM.")
        return redirect("dokumen:pustaka")
    k = get_object_or_404(KategoriDokumen, pk=pk)
    if k.is_sistem:
        messages.error(request, f"Kategori '{k.nama}' adalah kategori sistem dan tidak bisa dihapus.")
        return redirect("dokumen:kategori_kelola")
    jumlah = k.dokumen.count()
    if jumlah:
        tujuan = KategoriDokumen.objects.filter(pk=request.POST.get("pindah_ke") or 0).exclude(pk=k.pk).first()
        if not tujuan:
            messages.error(request, f"Kategori '{k.nama}' dipakai {jumlah} dokumen. Pilih kategori tujuan pemindahan.")
            return redirect("dokumen:kategori_kelola")
        with transaction.atomic():
            Dokumen.objects.filter(kategori=k).update(kategori=tujuan)
            k.delete()
        messages.success(request, f"Kategori '{k.nama}' dihapus; {jumlah} dokumen dipindah ke '{tujuan.nama}'.")
    else:
        k.delete()
        messages.success(request, f"Kategori '{k.nama}' dihapus.")
    return redirect("dokumen:kategori_kelola")
