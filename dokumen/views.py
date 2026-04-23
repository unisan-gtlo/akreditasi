"""
Views untuk modul Dokumen.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Q, F
from django.db import models, transaction


from master_akreditasi.models import (
    Instrumen,
    Standar,
    SubStandar,
    ButirDokumen,
    MappingProdiInstrumen,
)
from .models import Dokumen, DokumenRevisi, DokumenAccessLog
from .permissions import (
    get_user_scopes,
    is_superadmin,
    can_upload_to_butir,
    can_view_dokumen,
    can_edit_dokumen,
    get_uploadable_butir_for_user,
)


# =========================================================
# HELPER: GET RELEVANT INSTRUMEN FOR USER
# =========================================================

def _get_relevant_instrumen_for_user(user):
    """
    Return instrumen yang relevan untuk scope user.
    - PRODI: instrumen yang ter-mapping ke prodi user
    - FAKULTAS: semua instrumen prodi di bawah fakultas
    - BIRO/UNIVERSITAS: semua instrumen
    """
    if is_superadmin(user):
        return Instrumen.objects.filter(aktif=True)

    scopes = get_user_scopes(user)

    # Kumpulkan kode_prodi user (kalau ada scope prodi)
    kode_prodi_list = []
    has_universitas = False
    has_biro = False
    has_fakultas_kode = []

    for scope in scopes:
        if scope.level == "UNIVERSITAS":
            has_universitas = True
        elif scope.level == "BIRO":
            has_biro = True
        elif scope.level == "FAKULTAS" and scope.fakultas_id:
            has_fakultas_kode.append(scope.fakultas_id)
        elif scope.level == "PRODI" and scope.prodi_id:
            kode_prodi_list.append(scope.prodi_id)

    # Universitas / Biro → semua instrumen
    if has_universitas or has_biro:
        return Instrumen.objects.filter(aktif=True)

    # Fakultas → instrumen yang dipakai prodi di bawahnya
    if has_fakultas_kode:
        # Query prodi under this fakultas via raw cross-schema
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT kode_prodi FROM master.program_studi WHERE kode_fakultas = ANY(%s)",
                [has_fakultas_kode],
            )
            prodi_under_fak = [row[0] for row in cursor.fetchall()]
        if prodi_under_fak:
            instrumen_ids = MappingProdiInstrumen.objects.filter(
                kode_prodi__in=prodi_under_fak,
                aktif=True,
            ).values_list("instrumen_id", flat=True).distinct()
            return Instrumen.objects.filter(id__in=instrumen_ids, aktif=True)

    # Prodi → instrumen specific
    if kode_prodi_list:
        instrumen_ids = MappingProdiInstrumen.objects.filter(
            kode_prodi__in=kode_prodi_list,
            aktif=True,
        ).values_list("instrumen_id", flat=True).distinct()
        return Instrumen.objects.filter(id__in=instrumen_ids, aktif=True)

    return Instrumen.objects.none()


# =========================================================
# LIST BUTIR (yang relevan untuk user)
# =========================================================

@login_required(login_url="/login/")
def butir_saya(request):
    """
    List butir dokumen yang user relevan upload.
    Grouped by instrumen.
    """
    # Filter instrumen relevan
    relevant_instrumen = _get_relevant_instrumen_for_user(request.user)

    # Filter param
    instrumen_filter = request.GET.get("instrumen")
    kategori_filter = request.GET.get("kategori")
    wajib_filter = request.GET.get("wajib")
    search = request.GET.get("q", "").strip()

    # Get uploadable butir
    butir_qs = get_uploadable_butir_for_user(request.user)
    butir_qs = butir_qs.filter(
        sub_standar__standar__instrumen__in=relevant_instrumen
    ).select_related(
        "sub_standar",
        "sub_standar__standar",
        "sub_standar__standar__instrumen",
    )

    # Apply filters
    if instrumen_filter:
        butir_qs = butir_qs.filter(sub_standar__standar__instrumen_id=instrumen_filter)
    if kategori_filter:
        butir_qs = butir_qs.filter(kategori_kepemilikan=kategori_filter)
    if wajib_filter == "Y":
        butir_qs = butir_qs.filter(wajib=True)
    elif wajib_filter == "N":
        butir_qs = butir_qs.filter(wajib=False)
    if search:
        butir_qs = butir_qs.filter(
            Q(kode__icontains=search)
            | Q(nama_dokumen__icontains=search)
            | Q(deskripsi__icontains=search)
        )

    butir_qs = butir_qs.order_by(
        "sub_standar__standar__instrumen__urutan",
        "sub_standar__standar__urutan",
        "sub_standar__urutan",
        "urutan",
    )

    # Annotate: apakah sudah ada dokumen untuk butir ini (by scope user)
    # Ini bantu user lihat progress upload
    scopes = get_user_scopes(request.user)
    user_kode_prodi = [s.prodi_id for s in scopes if s.level == "PRODI" and s.prodi_id]
    user_kode_fakultas = [s.fakultas_id for s in scopes if s.level == "FAKULTAS" and s.fakultas_id]

    # Precompute doc count per butir (relevan dengan scope user)
    butir_list = []
    for butir in butir_qs:
        # Hitung dokumen yang sudah diupload untuk butir ini
        # Untuk admin/universitas: count semua
        # Untuk scope lain: count dokumen di scope mereka
        dokumen_qs = butir.dokumen_terunggah.all()
        if butir.kategori_kepemilikan == "PRODI" and user_kode_prodi:
            dokumen_qs = dokumen_qs.filter(scope_kode_prodi__in=user_kode_prodi)
        elif butir.kategori_kepemilikan == "FAKULTAS" and user_kode_fakultas:
            dokumen_qs = dokumen_qs.filter(scope_kode_fakultas__in=user_kode_fakultas)

        butir_list.append({
            "butir": butir,
            "dokumen_count": dokumen_qs.count(),
        })

    # Grouping by instrumen
    instrumen_all = list(relevant_instrumen.order_by("urutan"))

    context = {
        "page_title": "Dokumen Saya",
        "active_menu": "dokumen",
        "butir_list": butir_list,
        "instrumen_all": instrumen_all,
        "filter_instrumen": instrumen_filter,
        "filter_kategori": kategori_filter,
        "filter_wajib": wajib_filter,
        "search": search,
        "total_butir": len(butir_list),
        "total_wajib": sum(1 for b in butir_list if b["butir"].wajib),
        "total_terunggah": sum(1 for b in butir_list if b["dokumen_count"] > 0),
    }
    return render(request, "dokumen/butir_saya.html", context)


# =========================================================
# DETAIL BUTIR (+ list dokumen terunggah)
# =========================================================

@login_required(login_url="/login/")
def butir_detail(request, butir_id):
    """
    Detail 1 butir dokumen: info butir + list dokumen terunggah + tombol Upload.
    """
    butir = get_object_or_404(ButirDokumen, pk=butir_id, aktif=True)

    # Cek apakah user boleh upload ke butir ini
    can_upload, upload_reason = can_upload_to_butir(request.user, butir)

    # Ambil dokumen terunggah untuk butir ini
    # Untuk semua user login: tampilkan semua dokumen (view-only)
    # Kalau mau filter by scope user, bisa ditambah
    dokumen_qs = butir.dokumen_terunggah.select_related(
        "uploaded_by", "last_updated_by"
    ).order_by("-tanggal_diubah")

    # Filter by scope user kalau bukan superadmin
    if not is_superadmin(request.user):
        scopes = get_user_scopes(request.user)
        user_kode_prodi = [s.prodi_id for s in scopes if s.level == "PRODI" and s.prodi_id]
        user_kode_fakultas = [s.fakultas_id for s in scopes if s.level == "FAKULTAS" and s.fakultas_id]

        # Untuk Prodi / Fakultas: tampil dokumen lintas scope masih bisa (view-only)
        # Tapi untuk "Dokumen Saya" kita fokus ke milik user
        # Kita tampilkan semua dulu, user bisa lihat milik orang lain juga

    context = {
        "page_title": f"Butir: {butir.kode}",
        "active_menu": "dokumen",
        "butir": butir,
        "dokumen_list": dokumen_qs,
        "can_upload": can_upload,
        "upload_reason": upload_reason,
    }
    return render(request, "dokumen/butir_detail.html", context)


# =========================================================
# DOKUMEN DETAIL (placeholder — full di K4+K5)
# =========================================================

@login_required(login_url="/login/")
def dokumen_detail(request, pk):
    """Detail 1 dokumen dengan preview inline, action buttons, dan riwayat revisi."""
    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission check
    can_view, view_reason = can_view_dokumen(request.user, dokumen)
    if not can_view:
        messages.error(request, "Anda tidak memiliki akses untuk melihat dokumen ini.")
        return redirect("dokumen:butir_saya")

    can_edit, _ = can_edit_dokumen(request.user, dokumen)

    # Track view (increment counter + log access)
    # Hanya track 1x per user per session per hari (avoid spam)
    _track_view(dokumen, request)

    # Get revisi aktif untuk preview
    revisi_aktif = dokumen.revisi_aktif
    revisi_list = dokumen.revisi.order_by("-nomor_revisi")

    # Determine preview capability
    can_preview = False
    preview_type = None  # 'pdf', 'image', 'gdrive', None
    preview_url = None

    if revisi_aktif:
        if revisi_aktif.is_gdrive and not revisi_aktif.is_link_broken:
            can_preview = True
            preview_type = "gdrive"
            preview_url = revisi_aktif.get_preview_url()
        elif revisi_aktif.is_local and revisi_aktif.file:
            ext = revisi_aktif.extension.lower()
            if ext == "pdf":
                can_preview = True
                preview_type = "pdf"
                preview_url = revisi_aktif.file.url
            elif ext in ("jpg", "jpeg", "png", "webp", "gif"):
                can_preview = True
                preview_type = "image"
                preview_url = revisi_aktif.file.url

    context = {
        "page_title": dokumen.judul,
        "active_menu": "dokumen",
        "dokumen": dokumen,
        "revisi_aktif": revisi_aktif,
        "revisi_list": revisi_list,
        "can_edit": can_edit,
        "can_preview": can_preview,
        "preview_type": preview_type,
        "preview_url": preview_url,
    }
    return render(request, "dokumen/dokumen_detail.html", context)


# =========================================================
# UPLOAD DOKUMEN (FULL IMPLEMENTATION)
# =========================================================

import hashlib
from pathlib import Path
from django.db import transaction
from django.utils import timezone

from .forms import DokumenUploadForm


@login_required(login_url="/login/")
def dokumen_upload(request, butir_id):
    """Form upload dokumen untuk butir tertentu."""
    butir = get_object_or_404(ButirDokumen, pk=butir_id, aktif=True)

    # Permission check
    can_upload, reason = can_upload_to_butir(request.user, butir)
    if not can_upload:
        messages.error(request, f"Tidak bisa upload: {reason}")
        return redirect("dokumen:butir_detail", butir_id=butir.pk)

    # Determine user scope info — untuk populate Dokumen.scope_xxx fields
    user_scope = _resolve_user_scope(request.user, butir.kategori_kepemilikan)

    if request.method == "POST":
        form = DokumenUploadForm(request.POST, request.FILES, butir=butir)
        if form.is_valid():
            try:
                with transaction.atomic():
                    dokumen = _create_dokumen(
                        butir=butir,
                        form=form,
                        user=request.user,
                        user_scope=user_scope,
                        request=request,
                    )
                messages.success(
                    request,
                    f"Dokumen '{dokumen.judul}' berhasil di-upload!"
                )
                return redirect("dokumen:dokumen_detail", pk=dokumen.pk)
            except Exception as e:
                messages.error(request, f"Gagal upload: {str(e)}")
    else:
        form = DokumenUploadForm(butir=butir)

    context = {
        "page_title": f"Upload: {butir.kode}",
        "active_menu": "dokumen",
        "butir": butir,
        "form": form,
        "user_scope": user_scope,
    }
    return render(request, "dokumen/dokumen_upload.html", context)


# =========================================================
# HELPERS
# =========================================================

def _resolve_user_scope(user, kategori):
    """
    Resolve scope user untuk populate Dokumen fields.
    Return dict: {scope_kode_prodi, scope_kode_fakultas, scope_kode_unit_kerja, label}
    """
    if is_superadmin(user):
        # Superadmin = default ke universitas
        return {
            "scope_kode_prodi": "",
            "scope_kode_fakultas": "",
            "scope_kode_unit_kerja": "",
            "label": "Super Admin (Universitas)",
        }

    scopes = get_user_scopes(user)

    # Cari scope yang cocok dengan kategori butir
    for scope in scopes:
        if kategori == "UNIVERSITAS" and scope.level == "UNIVERSITAS":
            return {
                "scope_kode_prodi": "",
                "scope_kode_fakultas": "",
                "scope_kode_unit_kerja": "",
                "label": scope.get_role_display(),
            }
        elif kategori == "BIRO" and scope.level == "BIRO":
            return {
                "scope_kode_prodi": "",
                "scope_kode_fakultas": "",
                "scope_kode_unit_kerja": str(scope.unit_kerja_id) if scope.unit_kerja_id else "",
                "label": f"{scope.get_role_display()} (Unit {scope.unit_kerja_id})",
            }
        elif kategori == "FAKULTAS" and scope.level in ["FAKULTAS", "PRODI"]:
            # Prodi boleh upload ke kategori fakultas (pakai fakultas dari scope prodi)
            return {
                "scope_kode_prodi": "",
                "scope_kode_fakultas": scope.fakultas_id or "",
                "scope_kode_unit_kerja": "",
                "label": f"{scope.get_role_display()} ({scope.fakultas_id})",
            }
        elif kategori == "PRODI" and scope.level == "PRODI":
            return {
                "scope_kode_prodi": scope.prodi_id or "",
                "scope_kode_fakultas": scope.fakultas_id or "",
                "scope_kode_unit_kerja": "",
                "label": f"{scope.get_role_display()} (Prodi {scope.prodi_id})",
            }

    # Fallback kalau tidak ada scope cocok (shouldn't happen karena permission sudah di-check)
    return {
        "scope_kode_prodi": "",
        "scope_kode_fakultas": "",
        "scope_kode_unit_kerja": "",
        "label": "Tidak diketahui",
    }


def _create_dokumen(butir, form, user, user_scope, request):
    """
    Create Dokumen + DokumenRevisi + DokumenAccessLog.
    Support hybrid storage: LOCAL upload ATAU GDrive link.
    """
    judul = form.cleaned_data["judul"]
    tahun = form.cleaned_data.get("tahun_akademik", "").strip()
    status_akses = form.cleaned_data["status_akses"]
    deskripsi = form.cleaned_data.get("deskripsi", "").strip()
    catatan_revisi = form.cleaned_data.get("catatan_revisi", "").strip()
    storage_type = form.cleaned_data.get("storage_type", "LOCAL")

    # Cari dokumen existing (butir + kategori + scope + tahun)
    existing = Dokumen.objects.filter(
        butir_dokumen=butir,
        kategori_pemilik=butir.kategori_kepemilikan,
        scope_kode_prodi=user_scope["scope_kode_prodi"],
        scope_kode_fakultas=user_scope["scope_kode_fakultas"],
        scope_kode_unit_kerja=user_scope["scope_kode_unit_kerja"],
        tahun_akademik=tahun,
    ).first()

    if existing:
        dokumen = existing
        dokumen.judul = judul
        dokumen.deskripsi = deskripsi
        dokumen.status_akses = status_akses
        dokumen.last_updated_by = user
        dokumen.save()

        dokumen.revisi.update(aktif=False)
        last_rev = dokumen.revisi.order_by("-nomor_revisi").first()
        nomor_rev = (last_rev.nomor_revisi + 1) if last_rev else 1
        aksi = DokumenAccessLog.AksiType.REVISI
    else:
        dokumen = Dokumen.objects.create(
            butir_dokumen=butir,
            kategori_pemilik=butir.kategori_kepemilikan,
            scope_kode_prodi=user_scope["scope_kode_prodi"],
            scope_kode_fakultas=user_scope["scope_kode_fakultas"],
            scope_kode_unit_kerja=user_scope["scope_kode_unit_kerja"],
            judul=judul,
            deskripsi=deskripsi,
            status_akses=status_akses,
            tahun_akademik=tahun,
            uploaded_by=user,
            last_updated_by=user,
        )
        nomor_rev = 1
        aksi = DokumenAccessLog.AksiType.UPLOAD

    # Build revisi sesuai storage type
    if storage_type == "LOCAL":
        revisi = _create_local_revisi(dokumen, nomor_rev, form, user)
    else:  # GDRIVE
        revisi = _create_gdrive_revisi(dokumen, nomor_rev, form, user)

    # Log akses
    DokumenAccessLog.objects.create(
        dokumen=dokumen,
        revisi=revisi,
        aksi=aksi,
        user=user,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        catatan=catatan_revisi[:200] if catatan_revisi else "",
    )

    return dokumen


def _create_local_revisi(dokumen, nomor_rev, form, user):
    """Create DokumenRevisi untuk LOCAL upload."""
    uploaded_file = form.cleaned_data["file"]
    catatan_revisi = form.cleaned_data.get("catatan_revisi", "").strip()

    # Hash file
    uploaded_file.seek(0)
    sha256 = hashlib.sha256(uploaded_file.read()).hexdigest()
    uploaded_file.seek(0)

    ext = Path(uploaded_file.name).suffix.lower().lstrip(".")

    revisi = DokumenRevisi.objects.create(
        dokumen=dokumen,
        nomor_revisi=nomor_rev,
        storage_type=DokumenRevisi.StorageType.LOCAL,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        file_size_kb=int(uploaded_file.size / 1024),
        file_hash=sha256,
        mime_type=getattr(uploaded_file, "content_type", "") or "",
        extension=ext,
        catatan_revisi=catatan_revisi,
        aktif=True,
        uploaded_by=user,
    )
    return revisi


def _create_gdrive_revisi(dokumen, nomor_rev, form, user):
    """Create DokumenRevisi untuk GDRIVE link."""
    from django.utils import timezone

    gdrive_url = form.cleaned_data["gdrive_url"]
    gdrive_file_id = form.cleaned_data.get("_gdrive_file_id", "")
    gdrive_accessible = form.cleaned_data.get("_gdrive_accessible", False)
    catatan_revisi = form.cleaned_data.get("catatan_revisi", "").strip()

    revisi = DokumenRevisi.objects.create(
        dokumen=dokumen,
        nomor_revisi=nomor_rev,
        storage_type=DokumenRevisi.StorageType.GDRIVE,
        gdrive_url=gdrive_url,
        gdrive_file_id=gdrive_file_id,
        original_filename=f"[Google Drive] {dokumen.judul}",
        extension="gdrive",
        catatan_revisi=catatan_revisi,
        aktif=True,
        uploaded_by=user,
        last_verified_at=timezone.now(),
        is_link_broken=not gdrive_accessible,
    )
    return revisi


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

# =========================================================
# VIEW TRACKING
# =========================================================

def _track_view(dokumen, request):
    """
    Track view dokumen: increment counter + log akses.
    Throttle: 1x per user per session untuk avoid spam.
    """
    # Throttle: cek session apakah user sudah view dokumen ini
    session_key = f"viewed_dokumen_{dokumen.pk}"
    if request.session.get(session_key):
        return  # already counted in this session

    # Increment counter
    Dokumen.objects.filter(pk=dokumen.pk).update(
        view_count=models.F("view_count") + 1
    )

    # Log access
    DokumenAccessLog.objects.create(
        dokumen=dokumen,
        revisi=dokumen.revisi_aktif,
        aksi=DokumenAccessLog.AksiType.VIEW,
        user=request.user if request.user.is_authenticated else None,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )

    # Mark in session
    request.session[session_key] = True

# =========================================================
# DOWNLOAD (K6 — Batch 2 stub for now, full di batch berikutnya)
# =========================================================

from django.http import HttpResponse, FileResponse, Http404


@login_required(login_url="/login/")
def dokumen_download(request, pk):
    """Download dokumen — LOCAL serve file, GDRIVE redirect."""
    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission: semua user login bisa download (sesuai konfig Q3=A)
    can_view, _ = can_view_dokumen(request.user, dokumen)
    if not can_view:
        messages.error(request, "Anda tidak memiliki akses untuk download dokumen ini.")
        return redirect("dokumen:butir_saya")

    revisi = dokumen.revisi_aktif
    if not revisi:
        messages.error(request, "Dokumen tidak memiliki revisi aktif.")
        return redirect("dokumen:dokumen_detail", pk=dokumen.pk)

    # Increment counter
    Dokumen.objects.filter(pk=dokumen.pk).update(
        download_count=F("download_count") + 1
    )

    # Log access
    DokumenAccessLog.objects.create(
        dokumen=dokumen,
        revisi=revisi,
        aksi=DokumenAccessLog.AksiType.DOWNLOAD,
        user=request.user if request.user.is_authenticated else None,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )

    # Serve berdasarkan storage type
    if revisi.is_gdrive:
        # Redirect ke GDrive direct download URL
        return redirect(revisi.get_download_url())
    else:
        # Serve LOCAL file dengan Content-Disposition: attachment
        if not revisi.file:
            raise Http404("File tidak ditemukan di server.")

        try:
            response = FileResponse(
                revisi.file.open("rb"),
                as_attachment=True,
                filename=revisi.original_filename,
            )
            return response
        except FileNotFoundError:
            messages.error(request, "File fisik tidak ditemukan di server. Hubungi admin.")
            return redirect("dokumen:dokumen_detail", pk=dokumen.pk)


# =========================================================
# UPLOAD REVISI (K6 — Batch 2 stub)
# =========================================================

@login_required(login_url="/login/")
def dokumen_upload_revisi(request, pk):
    """Upload revisi baru untuk dokumen existing."""
    from .forms import RevisiUploadForm

    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission: hanya yang punya edit access
    can_edit, reason = can_edit_dokumen(request.user, dokumen)
    if not can_edit:
        messages.error(request, f"Tidak bisa upload revisi: {reason}")
        return redirect("dokumen:dokumen_detail", pk=dokumen.pk)

    butir = dokumen.butir_dokumen

    if request.method == "POST":
        form = RevisiUploadForm(request.POST, request.FILES, butir=butir)
        if form.is_valid():
            try:
                with transaction.atomic():
                    revisi = _create_revisi_for_dokumen(
                        dokumen=dokumen,
                        form=form,
                        user=request.user,
                        request=request,
                    )
                messages.success(
                    request,
                    f"Revisi #{revisi.nomor_revisi} berhasil diupload!"
                )
                return redirect("dokumen:dokumen_detail", pk=dokumen.pk)
            except Exception as e:
                messages.error(request, f"Gagal upload revisi: {str(e)}")
    else:
        form = RevisiUploadForm(butir=butir)

    context = {
        "page_title": f"Upload Revisi: {dokumen.judul}",
        "active_menu": "dokumen",
        "dokumen": dokumen,
        "butir": butir,
        "form": form,
    }
    return render(request, "dokumen/dokumen_upload_revisi.html", context)


def _create_revisi_for_dokumen(dokumen, form, user, request):
    """Helper buat revisi baru untuk dokumen existing."""
    storage_type = form.cleaned_data.get("storage_type", "LOCAL")
    catatan_revisi = form.cleaned_data["catatan_revisi"].strip()

    # Update dokumen meta
    dokumen.last_updated_by = user
    dokumen.save(update_fields=["last_updated_by", "tanggal_diubah"])

    # Nonaktifkan revisi lama
    dokumen.revisi.update(aktif=False)

    # Nomor revisi baru
    last_rev = dokumen.revisi.order_by("-nomor_revisi").first()
    nomor_rev = (last_rev.nomor_revisi + 1) if last_rev else 1

    # Build revisi sesuai storage
    if storage_type == "LOCAL":
        revisi = _create_local_revisi(dokumen, nomor_rev, form, user)
    else:
        revisi = _create_gdrive_revisi(dokumen, nomor_rev, form, user)

    # Log access
    DokumenAccessLog.objects.create(
        dokumen=dokumen,
        revisi=revisi,
        aksi=DokumenAccessLog.AksiType.REVISI,
        user=user,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        catatan=catatan_revisi[:200],
    )

    return revisi

# =========================================================
# PREVIEW SERVE (untuk iframe inline — bypass X-Frame-Options)
# =========================================================

from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.http import FileResponse, Http404
import mimetypes


@xframe_options_sameorigin
@login_required(login_url="/login/")
def dokumen_preview_serve(request, pk):
    """
    Serve file untuk preview inline (PDF/Image).
    Allow embedding di iframe dari domain yang sama.
    Hanya untuk LOCAL files. GDrive pakai URL embed langsung.
    """
    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission check
    can_view, _ = can_view_dokumen(request.user, dokumen)
    if not can_view:
        raise Http404("Dokumen tidak ditemukan atau tidak ada akses.")

    revisi = dokumen.revisi_aktif
    if not revisi or not revisi.is_local or not revisi.file:
        raise Http404("File tidak tersedia untuk preview.")

    try:
        # Detect content type berdasarkan ekstensi
        content_type, _ = mimetypes.guess_type(revisi.original_filename)
        if not content_type:
            ext = revisi.extension.lower()
            if ext == "pdf":
                content_type = "application/pdf"
            elif ext in ("jpg", "jpeg"):
                content_type = "image/jpeg"
            elif ext == "png":
                content_type = "image/png"
            elif ext == "webp":
                content_type = "image/webp"
            elif ext == "gif":
                content_type = "image/gif"
            else:
                content_type = "application/octet-stream"

        response = FileResponse(
            revisi.file.open("rb"),
            content_type=content_type,
            as_attachment=False,  # inline (bukan download)
        )
        # Filename hint (untuk save-as kalau user ctrl+s)
        response["Content-Disposition"] = f'inline; filename="{revisi.original_filename}"'
        return response
    except FileNotFoundError:
        raise Http404("File fisik tidak ditemukan di server.")

# =========================================================
# EDIT METADATA DOKUMEN
# =========================================================

@login_required(login_url="/login/")
def dokumen_edit(request, pk):
    """Edit metadata dokumen (judul/deskripsi/akses/tahun/status)."""
    from .forms import DokumenEditForm

    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission check
    can_edit, reason = can_edit_dokumen(request.user, dokumen)
    if not can_edit:
        messages.error(request, f"Tidak bisa edit: {reason}")
        return redirect("dokumen:dokumen_detail", pk=dokumen.pk)

    if request.method == "POST":
        form = DokumenEditForm(request.POST, instance=dokumen)
        if form.is_valid():
            form.instance.last_updated_by = request.user
            form.save()

            # Log access
            DokumenAccessLog.objects.create(
                dokumen=dokumen,
                aksi=DokumenAccessLog.AksiType.EDIT_META,
                user=request.user,
                ip_address=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                catatan="Update metadata",
            )

            messages.success(request, f"Metadata dokumen '{dokumen.judul}' berhasil diupdate!")
            return redirect("dokumen:dokumen_detail", pk=dokumen.pk)
    else:
        form = DokumenEditForm(instance=dokumen)

    context = {
        "page_title": f"Edit: {dokumen.judul}",
        "active_menu": "dokumen",
        "dokumen": dokumen,
        "form": form,
    }
    return render(request, "dokumen/dokumen_edit.html", context)

# =========================================================
# ACCESS LOG VIEWER (K7)
# =========================================================

from django.db.models import Count
from django.core.paginator import Paginator


@login_required(login_url="/login/")
def dokumen_access_log(request, pk):
    """Lihat audit trail (riwayat akses) untuk 1 dokumen."""
    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission: hanya pemilik (can_edit) + admin bisa lihat log
    can_edit, _ = can_edit_dokumen(request.user, dokumen)
    if not can_edit and not is_superadmin(request.user):
        messages.error(
            request,
            "Anda tidak memiliki akses untuk melihat riwayat akses dokumen ini."
        )
        return redirect("dokumen:dokumen_detail", pk=dokumen.pk)

    # Query logs
    logs_qs = dokumen.access_logs.select_related("user", "revisi").order_by("-waktu")

    # Filter by aksi
    aksi_filter = request.GET.get("aksi")
    if aksi_filter:
        logs_qs = logs_qs.filter(aksi=aksi_filter)

    # Filter by user
    user_filter = request.GET.get("user", "").strip()
    if user_filter:
        logs_qs = logs_qs.filter(user__username__icontains=user_filter)

    # Pagination
    paginator = Paginator(logs_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Stats
    all_logs = dokumen.access_logs.all()
    stats = {
        "total": all_logs.count(),
        "view": all_logs.filter(aksi="VIEW").count(),
        "download": all_logs.filter(aksi="DOWNLOAD").count(),
        "upload": all_logs.filter(aksi="UPLOAD").count(),
        "revisi": all_logs.filter(aksi="REVISI").count(),
        "edit": all_logs.filter(aksi="EDIT_META").count(),
    }

    # Top viewers (top 5 user yang paling sering view/download)
    top_users = (
        all_logs.filter(user__isnull=False)
        .filter(aksi__in=["VIEW", "DOWNLOAD"])
        .values("user__username", "user__first_name", "user__last_name")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # Anonim count (user_id null)
    anon_count = all_logs.filter(user__isnull=True).count()

    # Aksi choices for filter dropdown
    aksi_choices = DokumenAccessLog.AksiType.choices

    context = {
        "page_title": f"Riwayat Akses: {dokumen.judul}",
        "active_menu": "dokumen",
        "dokumen": dokumen,
        "page_obj": page_obj,
        "stats": stats,
        "top_users": top_users,
        "anon_count": anon_count,
        "aksi_choices": aksi_choices,
        "filter_aksi": aksi_filter,
        "filter_user": user_filter,
    }
    return render(request, "dokumen/dokumen_access_log.html", context)

# =========================================================
# ACCESS LOG VIEWER (K7)
# =========================================================

from django.db.models import Count
from django.core.paginator import Paginator


@login_required(login_url="/login/")
def dokumen_access_log(request, pk):
    """Lihat audit trail (riwayat akses) untuk 1 dokumen."""
    dokumen = get_object_or_404(Dokumen, pk=pk)

    # Permission: hanya pemilik (can_edit) + admin bisa lihat log
    can_edit, _ = can_edit_dokumen(request.user, dokumen)
    if not can_edit and not is_superadmin(request.user):
        messages.error(
            request,
            "Anda tidak memiliki akses untuk melihat riwayat akses dokumen ini."
        )
        return redirect("dokumen:dokumen_detail", pk=dokumen.pk)

    # Query logs
    logs_qs = dokumen.access_logs.select_related("user", "revisi").order_by("-waktu")

    # Filter by aksi
    aksi_filter = request.GET.get("aksi")
    if aksi_filter:
        logs_qs = logs_qs.filter(aksi=aksi_filter)

    # Filter by user
    user_filter = request.GET.get("user", "").strip()
    if user_filter:
        logs_qs = logs_qs.filter(user__username__icontains=user_filter)

    # Pagination
    paginator = Paginator(logs_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Stats
    all_logs = dokumen.access_logs.all()
    stats = {
        "total": all_logs.count(),
        "view": all_logs.filter(aksi="VIEW").count(),
        "download": all_logs.filter(aksi="DOWNLOAD").count(),
        "upload": all_logs.filter(aksi="UPLOAD").count(),
        "revisi": all_logs.filter(aksi="REVISI").count(),
        "edit": all_logs.filter(aksi="EDIT_META").count(),
    }

    # Top viewers (top 5 user yang paling sering view/download)
    top_users = (
        all_logs.filter(user__isnull=False)
        .filter(aksi__in=["VIEW", "DOWNLOAD"])
        .values("user__username", "user__first_name", "user__last_name")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # Anonim count (user_id null)
    anon_count = all_logs.filter(user__isnull=True).count()

    # Aksi choices for filter dropdown
    aksi_choices = DokumenAccessLog.AksiType.choices

    context = {
        "page_title": f"Riwayat Akses: {dokumen.judul}",
        "active_menu": "dokumen",
        "dokumen": dokumen,
        "page_obj": page_obj,
        "stats": stats,
        "top_users": top_users,
        "anon_count": anon_count,
        "aksi_choices": aksi_choices,
        "filter_aksi": aksi_filter,
        "filter_user": user_filter,
    }
    return render(request, "dokumen/dokumen_access_log.html", context)

# =========================================================
# LANDING PUBLIK (K8)
# =========================================================

def dokumen_publik_list(request):
    """
    List dokumen publik (TERBUKA) — TANPA perlu login.
    Drive-style grid view.
    """
    # Query dokumen TERBUKA + status FINAL (publish-ready)
    dokumen_qs = Dokumen.objects.filter(
        status_akses="TERBUKA",
        status="FINAL",
    ).select_related(
        "butir_dokumen",
        "butir_dokumen__sub_standar",
        "butir_dokumen__sub_standar__standar",
        "butir_dokumen__sub_standar__standar__instrumen",
    ).order_by("-tanggal_diubah")

    # Filter: instrumen
    instrumen_filter = request.GET.get("instrumen")
    if instrumen_filter:
        dokumen_qs = dokumen_qs.filter(
            butir_dokumen__sub_standar__standar__instrumen_id=instrumen_filter
        )

    # Filter: kategori
    kategori_filter = request.GET.get("kategori")
    if kategori_filter:
        dokumen_qs = dokumen_qs.filter(kategori_pemilik=kategori_filter)

    # Filter: tahun
    tahun_filter = request.GET.get("tahun", "").strip()
    if tahun_filter:
        dokumen_qs = dokumen_qs.filter(tahun_akademik__icontains=tahun_filter)

    # Search
    search = request.GET.get("q", "").strip()
    if search:
        dokumen_qs = dokumen_qs.filter(
            Q(judul__icontains=search)
            | Q(deskripsi__icontains=search)
            | Q(butir_dokumen__nama_dokumen__icontains=search)
        )

    # Pagination
    paginator = Paginator(dokumen_qs, 24)  # 24 cards per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Stats untuk header
    total_publik = Dokumen.objects.filter(status_akses="TERBUKA", status="FINAL").count()
    instrumen_list = Instrumen.objects.filter(aktif=True).order_by("urutan")

    # Tahun akademik unik (untuk filter dropdown)
    tahun_list = (
        Dokumen.objects.filter(status_akses="TERBUKA", status="FINAL")
        .exclude(tahun_akademik="")
        .values_list("tahun_akademik", flat=True)
        .distinct()
        .order_by("-tahun_akademik")
    )

    context = {
        "active_publik": "dokumen",
        "page_obj": page_obj,
        "total_publik": total_publik,
        "instrumen_list": instrumen_list,
        "tahun_list": tahun_list,
        "filter_instrumen": instrumen_filter,
        "filter_kategori": kategori_filter,
        "filter_tahun": tahun_filter,
        "search": search,
    }
    return render(request, "dokumen/dokumen_publik_list.html", context)

def dokumen_publik_detail(request, pk):
    """Detail dokumen publik — bisa diakses TANPA login (untuk dokumen TERBUKA + FINAL)."""
    dokumen = get_object_or_404(
        Dokumen,
        pk=pk,
        status_akses="TERBUKA",
        status="FINAL",
    )

    # Track view (anonim atau user login, throttle session)
    _track_view_publik(dokumen, request)

    revisi_aktif = dokumen.revisi_aktif

    # Determine preview capability
    can_preview = False
    preview_type = None
    preview_url = None

    if revisi_aktif:
        if revisi_aktif.is_gdrive and not revisi_aktif.is_link_broken:
            can_preview = True
            preview_type = "gdrive"
            preview_url = revisi_aktif.get_preview_url()
        elif revisi_aktif.is_local and revisi_aktif.file:
            ext = revisi_aktif.extension.lower()
            if ext == "pdf":
                can_preview = True
                preview_type = "pdf"
                preview_url = revisi_aktif.file.url
            elif ext in ("jpg", "jpeg", "png", "webp", "gif"):
                can_preview = True
                preview_type = "image"
                preview_url = revisi_aktif.file.url

    context = {
        "active_publik": "dokumen",
        "dokumen": dokumen,
        "revisi_aktif": revisi_aktif,
        "can_preview": can_preview,
        "preview_type": preview_type,
        "preview_url": preview_url,
    }
    return render(request, "dokumen/dokumen_publik_detail.html", context)


def _track_view_publik(dokumen, request):
    """Track view publik — sama seperti _track_view tapi untuk anonim."""
    session_key = f"viewed_publik_{dokumen.pk}"
    if request.session.get(session_key):
        return

    Dokumen.objects.filter(pk=dokumen.pk).update(
        view_count=F("view_count") + 1
    )

    DokumenAccessLog.objects.create(
        dokumen=dokumen,
        revisi=dokumen.revisi_aktif,
        aksi=DokumenAccessLog.AksiType.VIEW,
        user=request.user if request.user.is_authenticated else None,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        catatan="via halaman publik",
    )

    request.session[session_key] = True

@xframe_options_sameorigin
def dokumen_publik_preview_serve(request, pk):
    """Serve file preview untuk dokumen publik (tanpa login required)."""
    dokumen = get_object_or_404(
        Dokumen,
        pk=pk,
        status_akses="TERBUKA",
        status="FINAL",
    )
    revisi = dokumen.revisi_aktif
    if not revisi or not revisi.is_local or not revisi.file:
        raise Http404("File tidak tersedia.")

    try:
        content_type, _ = mimetypes.guess_type(revisi.original_filename)
        if not content_type:
            ext = revisi.extension.lower()
            type_map = {
                "pdf": "application/pdf",
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp", "gif": "image/gif",
            }
            content_type = type_map.get(ext, "application/octet-stream")

        response = FileResponse(
            revisi.file.open("rb"),
            content_type=content_type,
            as_attachment=False,
        )
        response["Content-Disposition"] = f'inline; filename="{revisi.original_filename}"'
        return response
    except FileNotFoundError:
        raise Http404("File fisik tidak ditemukan.")


def dokumen_publik_download(request, pk):
    """Download dokumen publik (tanpa login)."""
    dokumen = get_object_or_404(
        Dokumen,
        pk=pk,
        status_akses="TERBUKA",
        status="FINAL",
    )

    revisi = dokumen.revisi_aktif
    if not revisi:
        messages.error(request, "Dokumen tidak memiliki revisi aktif.")
        return redirect("dokumen_publik_detail", pk=dokumen.pk)

    # Increment counter
    Dokumen.objects.filter(pk=dokumen.pk).update(
        download_count=F("download_count") + 1
    )

    # Log access (anonim ok)
    DokumenAccessLog.objects.create(
        dokumen=dokumen,
        revisi=revisi,
        aksi=DokumenAccessLog.AksiType.DOWNLOAD,
        user=request.user if request.user.is_authenticated else None,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        catatan="via halaman publik",
    )

    if revisi.is_gdrive:
        return redirect(revisi.get_download_url())
    else:
        if not revisi.file:
            raise Http404("File tidak ditemukan.")
        try:
            return FileResponse(
                revisi.file.open("rb"),
                as_attachment=True,
                filename=revisi.original_filename,
            )
        except FileNotFoundError:
            messages.error(request, "File fisik tidak ditemukan di server.")
            return redirect("dokumen_publik_detail", pk=dokumen.pk)