"""Views untuk modul Sesi Akreditasi."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
import re as stdre
import zipfile
import io as stdio
import json
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.db import transaction
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from .models import SesiAkreditasi, MilestoneSesi, CatatanSesi, BundleShareToken
from .forms import SesiCreateForm, SesiEditForm
from .permissions import can_create_sesi, can_edit_sesi, can_view_sesi, is_superadmin
from master_akreditasi.models import Instrumen, ButirDokumen
from dokumen.models import Dokumen


# =========================================================
# LIST SESI
# =========================================================

@login_required(login_url="/login/")
def sesi_list(request):
    """List semua sesi akreditasi dengan filter."""

    sesi_qs = SesiAkreditasi.objects.select_related(
        "instrumen", "dibuat_oleh"
    ).order_by("-tanggal_mulai")

    # Filters
    status_filter = request.GET.get("status")
    instrumen_filter = request.GET.get("instrumen")
    tipe_filter = request.GET.get("tipe")
    search = request.GET.get("q", "").strip()

    if status_filter:
        sesi_qs = sesi_qs.filter(status=status_filter)
    if instrumen_filter:
        sesi_qs = sesi_qs.filter(instrumen_id=instrumen_filter)
    if tipe_filter:
        sesi_qs = sesi_qs.filter(tipe=tipe_filter)
    if search:
        sesi_qs = sesi_qs.filter(
            Q(judul__icontains=search)
            | Q(nama_prodi_snapshot__icontains=search)
            | Q(kode_prodi__icontains=search)
        )

    # Stats
    all_sesi = SesiAkreditasi.objects.all()
    stats = {
        "total": all_sesi.count(),
        "aktif": all_sesi.exclude(status__in=["SELESAI", "DIBATALKAN"]).count(),
        "selesai": all_sesi.filter(status="SELESAI").count(),
        "visitasi": all_sesi.filter(status="VISITASI_AKTIF").count(),
    }

    paginator = Paginator(sesi_qs, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    instrumen_list = Instrumen.objects.filter(aktif=True).order_by("urutan")

    # Permission flag
    can_create, _ = can_create_sesi(request.user)

    context = {
        "page_title": "Sesi Akreditasi",
        "active_menu": "sesi",
        "page_obj": page_obj,
        "stats": stats,
        "instrumen_list": instrumen_list,
        "status_choices": SesiAkreditasi.Status.choices,
        "tipe_choices": SesiAkreditasi.TipeAkreditasi.choices,
        "filter_status": status_filter,
        "filter_instrumen": instrumen_filter,
        "filter_tipe": tipe_filter,
        "search": search,
        "can_create": can_create,
    }
    return render(request, "sesi/sesi_list.html", context)


# =========================================================
# CREATE SESI
# =========================================================

@login_required(login_url="/login/")
def sesi_create(request):
    """Form buat sesi baru."""

    can_create, reason = can_create_sesi(request.user)
    if not can_create:
        messages.error(request, f"Tidak bisa buat sesi: {reason}")
        return redirect("sesi:sesi_list")

    if request.method == "POST":
        form = SesiCreateForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sesi = _create_sesi_with_milestones(form, request.user)
                messages.success(
                    request,
                    f"Sesi '{sesi.judul}' berhasil dibuat dengan {sesi.milestones.count()} milestone default!"
                )
                return redirect("sesi:sesi_detail", pk=sesi.pk)
            except Exception as e:
                messages.error(request, f"Gagal buat sesi: {str(e)}")
    else:
        form = SesiCreateForm()

    # Build mapping {kode_prodi: [instrumen_ids]} untuk JS filter
    from sesi.forms import get_mapping_prodi_instrumen
    mapping_data = get_mapping_prodi_instrumen()

    context = {
        "page_title": "Buat Sesi Baru",
        "active_menu": "sesi",
        "form": form,
        "mapping_prodi_instrumen": mapping_data,
    }
    return render(request, "sesi/sesi_create.html", context)


def _create_sesi_with_milestones(form, user):
    """Helper buat sesi + auto-generate milestones."""
    cleaned = form.cleaned_data
    kode_prodi = cleaned["kode_prodi"]
    instrumen = cleaned["instrumen"]
    tipe = cleaned["tipe"]
    tahun_ts = cleaned["tahun_ts"]
    tgl_mulai = cleaned["tanggal_mulai"]
    tgl_target = cleaned["tanggal_target_selesai"]
    deadline_upload = cleaned.get("deadline_upload_dokumen")
    deskripsi = cleaned.get("deskripsi", "")
    auto_milestones = cleaned.get("auto_generate_milestones", True)

    # Get prodi info
    prodi_map = form.prodi_map
    nama_prodi, kode_fakultas = prodi_map.get(kode_prodi, ("Unknown", ""))

    # Build judul otomatis
    tipe_label_map = {
        "AKREDITASI_BARU": "Akreditasi Baru",
        "REAKREDITASI": "Re-akreditasi",
        "AKREDITASI_KHUSUS": "Akreditasi Khusus",
    }
    tipe_label = tipe_label_map.get(tipe, "Akreditasi")

    # Extract tahun dari tahun_ts (misal "2025/2026" -> "2026")
    tahun_simple = tahun_ts.split("/")[-1] if "/" in tahun_ts else tahun_ts

    judul = f"{tipe_label} {nama_prodi} - {instrumen.nama_singkat} {tahun_simple}"

    # Create Sesi
    sesi = SesiAkreditasi.objects.create(
        judul=judul,
        deskripsi=deskripsi,
        instrumen=instrumen,
        kode_prodi=kode_prodi,
        nama_prodi_snapshot=nama_prodi,
        kode_fakultas=kode_fakultas,
        tipe=tipe,
        tahun_ts=tahun_ts,
        tanggal_mulai=tgl_mulai,
        tanggal_target_selesai=tgl_target,
        deadline_upload_dokumen=deadline_upload,
        status=SesiAkreditasi.Status.PERSIAPAN,
        dibuat_oleh=user,
        terakhir_diupdate_oleh=user,
    )

    # Auto-generate milestones
    if auto_milestones:
        _generate_default_milestones(sesi)

    return sesi


def _generate_default_milestones(sesi):
    """Generate 5 milestone default berdasarkan tanggal sesi."""
    tgl_mulai = sesi.tanggal_mulai
    tgl_target = sesi.tanggal_target_selesai
    deadline_upload = sesi.deadline_upload_dokumen or (tgl_mulai + (tgl_target - tgl_mulai) / 3)

    # Hitung tanggal antara
    duration = (tgl_target - tgl_mulai).days
    review_date = deadline_upload + timedelta(days=14)
    submit_date = deadline_upload + timedelta(days=30)
    visitasi_date = tgl_mulai + timedelta(days=int(duration * 0.7))

    milestones = [
        {
            "urutan": 1,
            "judul": "Persiapan Dokumen",
            "deskripsi": "Upload semua dokumen pendukung sesuai butir akreditasi",
            "tanggal_target": deadline_upload,
        },
        {
            "urutan": 2,
            "judul": "Review Internal LP3M",
            "deskripsi": "Verifikasi kelengkapan dan kualitas dokumen oleh LP3M",
            "tanggal_target": review_date,
        },
        {
            "urutan": 3,
            "judul": "Submit ke LAM/BAN-PT",
            "deskripsi": "Pengajuan resmi ke lembaga akreditasi",
            "tanggal_target": submit_date,
        },
        {
            "urutan": 4,
            "judul": "Visitasi Asesor",
            "deskripsi": "Kunjungan dan asesmen langsung oleh asesor",
            "tanggal_target": visitasi_date,
        },
        {
            "urutan": 5,
            "judul": "Sertifikat Terbit",
            "deskripsi": "Penerimaan SK akreditasi resmi",
            "tanggal_target": tgl_target,
        },
    ]

    for m in milestones:
        MilestoneSesi.objects.create(sesi=sesi, **m)


# =========================================================
# DETAIL SESI
# =========================================================

@login_required(login_url="/login/")
def sesi_detail(request, pk):
    """Detail sesi dengan progress butir per kriteria."""
    sesi = get_object_or_404(SesiAkreditasi, pk=pk)

    can_view, _ = can_view_sesi(request.user, sesi)
    if not can_view:
        messages.error(request, "Anda tidak memiliki akses untuk melihat sesi ini.")
        return redirect("sesi:sesi_list")

    can_edit, _ = can_edit_sesi(request.user, sesi)

    # Get butir dokumen untuk instrumen ini, group by standar
    butir_qs = ButirDokumen.objects.filter(
        sub_standar__standar__instrumen=sesi.instrumen,
        aktif=True,
    ).select_related(
        "sub_standar",
        "sub_standar__standar",
    ).order_by(
        "sub_standar__standar__urutan",
        "sub_standar__urutan",
        "urutan",
    )

    # Cek dokumen yang sudah upload untuk masing-masing butir (sesuai scope sesi)
    dokumen_per_butir = {}
    for d in Dokumen.objects.filter(
        butir_dokumen__in=butir_qs,
        tahun_akademik__in=sesi.tahun_periode_list,
    ).filter(
        Q(scope_kode_prodi=sesi.kode_prodi) |
        Q(scope_kode_fakultas=sesi.kode_fakultas, kategori_pemilik="FAKULTAS") |
        Q(kategori_pemilik="UNIVERSITAS")
    ).select_related("butir_dokumen"):
        dokumen_per_butir.setdefault(d.butir_dokumen_id, []).append(d)

    # Build per-standar progress
    standar_groups = {}
    for butir in butir_qs:
        std = butir.sub_standar.standar
        if std.id not in standar_groups:
            standar_groups[std.id] = {
                "standar": std,
                "butir_list": [],
                "total": 0,
                "terisi": 0,
            }
        dokumen_list = dokumen_per_butir.get(butir.id, [])
        is_terisi = len(dokumen_list) > 0
        standar_groups[std.id]["butir_list"].append({
            "butir": butir,
            "dokumen_list": dokumen_list,
            "is_terisi": is_terisi,
        })
        standar_groups[std.id]["total"] += 1
        if is_terisi:
            standar_groups[std.id]["terisi"] += 1

    # Add percentage
    for std_id, group in standar_groups.items():
        if group["total"] > 0:
            group["percentage"] = round((group["terisi"] / group["total"]) * 100, 1)
        else:
            group["percentage"] = 0

    # Sort by standar urutan
    standar_groups_list = sorted(standar_groups.values(), key=lambda g: g["standar"].urutan)

    # Milestones
    milestones = sesi.milestones.order_by("urutan", "tanggal_target")

    # Catatan
    catatan_list = sesi.catatan.select_related("dibuat_oleh").order_by("-tanggal_dibuat")[:10]

    # Overall progress
    overall_progress = sesi.progress_dokumen

    context = {
        "page_title": sesi.judul,
        "active_menu": "sesi",
        "sesi": sesi,
        "standar_groups": standar_groups_list,
        "milestones": milestones,
        "catatan_list": catatan_list,
        "overall_progress": overall_progress,
        "can_edit": can_edit,
    }
    return render(request, "sesi/sesi_detail.html", context)


# =========================================================
# EDIT SESI
# =========================================================

@login_required(login_url="/login/")
def sesi_edit(request, pk):
    """Edit metadata sesi."""
    sesi = get_object_or_404(SesiAkreditasi, pk=pk)

    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa edit: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    if request.method == "POST":
        form = SesiEditForm(request.POST, instance=sesi)
        if form.is_valid():
            form.instance.terakhir_diupdate_oleh = request.user
            form.save()
            messages.success(request, f"Sesi '{sesi.judul}' berhasil diupdate!")
            return redirect("sesi:sesi_detail", pk=sesi.pk)
    else:
        form = SesiEditForm(instance=sesi)

    context = {
        "page_title": f"Edit: {sesi.judul}",
        "active_menu": "sesi",
        "sesi": sesi,
        "form": form,
    }
    return render(request, "sesi/sesi_edit.html", context)
# =========================================================
# CANCEL & DELETE SESI
# =========================================================

@login_required(login_url="/login/")
def sesi_cancel(request, pk):
    """Set status jadi DIBATALKAN (soft delete)."""
    sesi = get_object_or_404(SesiAkreditasi, pk=pk)

    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa batalkan: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    if request.method == "POST":
        sesi.status = SesiAkreditasi.Status.DIBATALKAN
        sesi.terakhir_diupdate_oleh = request.user
        sesi.save()
        messages.success(request, f"Sesi '{sesi.judul}' telah dibatalkan.")
        return redirect("sesi:sesi_list")

    # GET: tampilkan halaman konfirmasi
    return render(request, "sesi/sesi_cancel_confirm.html", {
        "page_title": f"Batalkan: {sesi.judul}",
        "active_menu": "sesi",
        "sesi": sesi,
    })


@login_required(login_url="/login/")
def sesi_delete(request, pk):
    """Hapus permanent sesi + milestone + catatan (cascade)."""
    sesi = get_object_or_404(SesiAkreditasi, pk=pk)

    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa hapus: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    if request.method == "POST":
        # Double-confirm: user harus ketik nama sesi
        confirmation = request.POST.get("confirm_text", "").strip()
        if confirmation != sesi.judul:
            messages.error(
                request,
                "Konfirmasi tidak cocok. Sesi tidak dihapus."
            )
            return redirect("sesi:sesi_delete", pk=sesi.pk)

        judul = sesi.judul
        n_milestones = sesi.milestones.count()
        n_catatan = sesi.catatan.count()
        sesi.delete()
        messages.success(
            request,
            f"Sesi '{judul}' dihapus permanent ({n_milestones} milestone + {n_catatan} catatan ikut terhapus)."
        )
        return redirect("sesi:sesi_list")

    # GET: tampilkan form konfirmasi
    return render(request, "sesi/sesi_delete_confirm.html", {
        "page_title": f"Hapus: {sesi.judul}",
        "active_menu": "sesi",
        "sesi": sesi,
        "n_milestones": sesi.milestones.count(),
        "n_catatan": sesi.catatan.count(),
    })

# =========================================================
# TIMELINE VISUAL
# =========================================================

@login_required(login_url="/login/")
def sesi_timeline(request, pk):
    """Halaman timeline visual sesi (horizontal Gantt SVG)."""
    sesi = get_object_or_404(SesiAkreditasi, pk=pk)

    can_view, _ = can_view_sesi(request.user, sesi)
    if not can_view:
        messages.error(request, "Tidak ada akses untuk sesi ini.")
        return redirect("sesi:sesi_list")

    can_edit, _ = can_edit_sesi(request.user, sesi)

    # Build timeline items: milestones + key dates
    from datetime import date, timedelta
    today = date.today()

    # Tentukan tanggal mulai & akhir timeline
    tgl_start = sesi.tanggal_mulai
    tgl_end = sesi.tanggal_target_selesai

    # Extend kalau ada tanggal lain di luar range
    extra_dates = [
        sesi.deadline_upload_dokumen,
        sesi.tanggal_submit,
        sesi.tanggal_visitasi_mulai,
        sesi.tanggal_visitasi_selesai,
        sesi.tanggal_sertifikat,
    ]
    for d in extra_dates:
        if d and d > tgl_end:
            tgl_end = d
        if d and d < tgl_start:
            tgl_start = d

    # Add buffer 7 days
    tgl_start = tgl_start - timedelta(days=7)
    tgl_end = tgl_end + timedelta(days=7)

    total_days = (tgl_end - tgl_start).days
    if total_days < 1:
        total_days = 1

    # Helper: convert date to X position percentage
    def date_to_pct(d):
        if d is None:
            return None
        delta = (d - tgl_start).days
        return round((delta / total_days) * 100, 2)

    # Build milestone bars
    milestones_data = []
    milestones = sesi.milestones.order_by("urutan", "tanggal_target")

    # Untuk milestone, gunakan range dari tanggal milestone sebelumnya (atau tanggal_mulai sesi) sampai tanggal_target milestone ini
    prev_date = sesi.tanggal_mulai
    for ms in milestones:
        # Bar end
        end_date = ms.tanggal_aktual if ms.tanggal_aktual else ms.tanggal_target
        start_date = prev_date

        # Make sure start <= end
        if start_date > end_date:
            start_date = end_date - timedelta(days=7)

        # Color based on status
        color_map = {
            "BELUM": "#94A3B8",       # gray
            "PROGRESS": "#3B82F6",     # blue
            "SELESAI": "#10B981",      # green
            "TERLEWAT": "#EF4444",     # red
        }
        # Auto-detect terlewat
        is_overdue = (
            ms.status == "BELUM"
            and ms.tanggal_target < today
        )
        if is_overdue:
            ms_status = "TERLEWAT"
            ms_color = color_map["TERLEWAT"]
        else:
            ms_status = ms.status
            ms_color = color_map.get(ms.status, "#94A3B8")

        x_start = date_to_pct(start_date)
        x_end = date_to_pct(end_date)
        width = max(x_end - x_start, 2)  # min width 2%

        milestones_data.append({
            "milestone": ms,
            "x_start": x_start,
            "width": width,
            "color": ms_color,
            "status_display": ms_status,
            "is_overdue": is_overdue,
            "start_date": start_date,
            "end_date": end_date,
        })
        prev_date = end_date

    # Key date markers (vertical lines)
    key_markers = []
    if sesi.deadline_upload_dokumen:
        key_markers.append({
            "date": sesi.deadline_upload_dokumen,
            "x": date_to_pct(sesi.deadline_upload_dokumen),
            "label": "Deadline Upload",
            "color": "#F59E0B",
        })
    if sesi.tanggal_submit:
        key_markers.append({
            "date": sesi.tanggal_submit,
            "x": date_to_pct(sesi.tanggal_submit),
            "label": "Submit ke LAM",
            "color": "#06B6D4",
        })
    if sesi.tanggal_visitasi_mulai:
        key_markers.append({
            "date": sesi.tanggal_visitasi_mulai,
            "x": date_to_pct(sesi.tanggal_visitasi_mulai),
            "label": "Visitasi Mulai",
            "color": "#A855F7",
        })
    if sesi.tanggal_sertifikat:
        key_markers.append({
            "date": sesi.tanggal_sertifikat,
            "x": date_to_pct(sesi.tanggal_sertifikat),
            "label": "Sertifikat",
            "color": "#10B981",
        })

    # Today indicator
    today_x = None
    if tgl_start <= today <= tgl_end:
        today_x = date_to_pct(today)

    # Month grid (untuk vertical light gray lines)
    month_marks = []
    current_month_date = date(tgl_start.year, tgl_start.month, 1)
    if current_month_date < tgl_start:
        if current_month_date.month == 12:
            current_month_date = date(current_month_date.year + 1, 1, 1)
        else:
            current_month_date = date(current_month_date.year, current_month_date.month + 1, 1)

    while current_month_date <= tgl_end:
        month_marks.append({
            "x": date_to_pct(current_month_date),
            "label": current_month_date.strftime("%b %Y"),
        })
        if current_month_date.month == 12:
            current_month_date = date(current_month_date.year + 1, 1, 1)
        else:
            current_month_date = date(current_month_date.year, current_month_date.month + 1, 1)

    context = {
        "page_title": f"Timeline: {sesi.judul}",
        "active_menu": "sesi",
        "sesi": sesi,
        "milestones_data": milestones_data,
        "key_markers": key_markers,
        "today_x": today_x,
        "today_date": today,
        "tgl_start": tgl_start,
        "tgl_end": tgl_end,
        "total_days": total_days,
        "month_marks": month_marks,
        "can_edit": can_edit,
    }
    return render(request, "sesi/sesi_timeline.html", context)

# =========================================================
# DASHBOARD SESI AKREDITASI
# =========================================================

@login_required(login_url="/login/")
def dashboard_sesi(request):
    """Dashboard executive view untuk sesi akreditasi."""
    from datetime import date, timedelta
    from django.db.models import Count, Q
    from .permissions import can_access_dashboard, get_visible_sesi_for_user

    can_access, reason = can_access_dashboard(request.user)
    if not can_access:
        messages.error(request, f"Akses dashboard ditolak: {reason}")
        return redirect("sesi:sesi_list")

    today = date.today()

    # Ambil semua sesi yang visible untuk user
    visible_qs = get_visible_sesi_for_user(request.user)
    visible_qs = visible_qs.select_related("instrumen")

    # Sesi aktif (exclude SELESAI & DIBATALKAN)
    sesi_aktif = visible_qs.exclude(status__in=["SELESAI", "DIBATALKAN"])

    # ============================================
    # 4 STATS CARDS
    # ============================================
    total_aktif = sesi_aktif.count()
    sedang_visitasi = visible_qs.filter(status="VISITASI_AKTIF").count()
    selesai_tahun_ini = visible_qs.filter(
        status="SELESAI",
        tanggal_sertifikat__year=today.year,
    ).count()

    # Critical: deadline <=30 hari ATAU progress <50%
    critical_count = 0
    critical_sesi = []
    for s in sesi_aktif:
        days = s.days_to_deadline
        progress = s.progress_dokumen
        is_critical = False
        urgency = "ok"
        if days is not None and days <= 7:
            urgency = "urgent"
            is_critical = True
        elif days is not None and days <= 30:
            urgency = "warning"
            is_critical = True
        elif progress["percentage"] < 50 and progress["total"] > 0:
            urgency = "warning"
            is_critical = True

        if is_critical:
            critical_count += 1
            critical_sesi.append({
                "sesi": s,
                "days": days,
                "progress": progress,
                "urgency": urgency,
            })

    # Sort: urgent dulu, lalu by days asc
    critical_sesi.sort(key=lambda x: (
        0 if x["urgency"] == "urgent" else 1,
        x["days"] if x["days"] is not None else 9999,
    ))

    # ============================================
    # CHARTS DATA
    # ============================================

    # Donut: by status
    status_counts_dict = dict(
        visible_qs.values_list("status").annotate(count=Count("id"))
    )
    status_data = []
    status_color_map = {
        "PERSIAPAN": "#3B82F6",
        "REVIEW_INTERNAL": "#F59E0B",
        "SUBMITTED": "#06B6D4",
        "VISITASI_AKTIF": "#A855F7",
        "MENUNGGU_HASIL": "#EAB308",
        "SELESAI": "#10B981",
        "DIBATALKAN": "#94A3B8",
    }
    status_label_map = dict(SesiAkreditasi.Status.choices)
    for status_key, color in status_color_map.items():
        count = status_counts_dict.get(status_key, 0)
        if count > 0:
            status_data.append({
                "key": status_key,
                "label": status_label_map.get(status_key, status_key),
                "count": count,
                "color": color,
            })

    total_for_donut = sum(s["count"] for s in status_data)

    # Calculate donut paths (SVG arcs)
    import math
    donut_segments = []
    if total_for_donut > 0:
        cumulative_angle = -90  # start at top
        for item in status_data:
            pct = item["count"] / total_for_donut
            angle_size = pct * 360
            start_angle = cumulative_angle
            end_angle = cumulative_angle + angle_size

            # SVG arc
            cx, cy = 100, 100
            r_outer = 80
            r_inner = 50

            sa_rad = math.radians(start_angle)
            ea_rad = math.radians(end_angle)

            x1_outer = cx + r_outer * math.cos(sa_rad)
            y1_outer = cy + r_outer * math.sin(sa_rad)
            x2_outer = cx + r_outer * math.cos(ea_rad)
            y2_outer = cy + r_outer * math.sin(ea_rad)

            x1_inner = cx + r_inner * math.cos(ea_rad)
            y1_inner = cy + r_inner * math.sin(ea_rad)
            x2_inner = cx + r_inner * math.cos(sa_rad)
            y2_inner = cy + r_inner * math.sin(sa_rad)

            large_arc = "1" if angle_size > 180 else "0"

            path = (
                f"M {x1_outer:.2f} {y1_outer:.2f} "
                f"A {r_outer} {r_outer} 0 {large_arc} 1 {x2_outer:.2f} {y2_outer:.2f} "
                f"L {x1_inner:.2f} {y1_inner:.2f} "
                f"A {r_inner} {r_inner} 0 {large_arc} 0 {x2_inner:.2f} {y2_inner:.2f} "
                f"Z"
            )
            donut_segments.append({
                "path": path,
                "color": item["color"],
                "label": item["label"],
                "count": item["count"],
                "pct": round(pct * 100, 1),
            })
            cumulative_angle = end_angle

    # Bar chart: per fakultas
    fakultas_data_raw = dict(
        visible_qs.values_list("kode_fakultas").annotate(count=Count("id"))
    )
    fakultas_data = sorted(
        [(k or "TANPA FAKULTAS", v) for k, v in fakultas_data_raw.items()],
        key=lambda x: -x[1]
    )
    max_fakultas_count = max((c for _, c in fakultas_data), default=1)
    fakultas_data = [
        {
            "kode": k,
            "count": c,
            "pct": round((c / max_fakultas_count) * 100, 1),
        }
        for k, c in fakultas_data
    ]

    # Per instrumen breakdown (matrix Instrumen x Status)
    instrumen_breakdown = []
    instrumen_qs = visible_qs.values("instrumen__nama_singkat").annotate(
        total=Count("id")
    ).order_by("-total")
    for ins in instrumen_qs:
        nama_ins = ins["instrumen__nama_singkat"]
        sesi_ins = visible_qs.filter(instrumen__nama_singkat=nama_ins)
        instrumen_breakdown.append({
            "nama": nama_ins,
            "total": ins["total"],
            "persiapan": sesi_ins.filter(status="PERSIAPAN").count(),
            "review": sesi_ins.filter(status="REVIEW_INTERNAL").count(),
            "submitted": sesi_ins.filter(status="SUBMITTED").count(),
            "visitasi": sesi_ins.filter(status="VISITASI_AKTIF").count(),
            "menunggu": sesi_ins.filter(status="MENUNGGU_HASIL").count(),
            "selesai": sesi_ins.filter(status="SELESAI").count(),
            "dibatalkan": sesi_ins.filter(status="DIBATALKAN").count(),
        })

    # Recent Activity: catatan terbaru + status change recent
    from .models import CatatanSesi
    visible_sesi_ids = list(visible_qs.values_list("id", flat=True))

    recent_catatan = CatatanSesi.objects.filter(
        sesi_id__in=visible_sesi_ids,
    ).select_related("sesi", "dibuat_oleh").order_by("-tanggal_dibuat")[:10]

    # Recent sesi (urutan tanggal_diubah)
    recent_sesi = visible_qs.order_by("-tanggal_diubah")[:5]

    context = {
        "page_title": "Dashboard Sesi Akreditasi",
        "active_menu": "dashboard_sesi",
        "today": today,
        "total_aktif": total_aktif,
        "critical_count": critical_count,
        "sedang_visitasi": sedang_visitasi,
        "selesai_tahun_ini": selesai_tahun_ini,
        "critical_sesi": critical_sesi[:10],  # show top 10
        "donut_segments": donut_segments,
        "donut_total": total_for_donut,
        "fakultas_data": fakultas_data,
        "instrumen_breakdown": instrumen_breakdown,
        "recent_catatan": recent_catatan,
        "recent_sesi": recent_sesi,
        "user_scope_info": _get_user_scope_label(request.user),
    }
    return render(request, "sesi/dashboard.html", context)


def _get_user_scope_label(user):
    """Return string deskripsi scope user untuk dashboard header."""
    if user.is_superuser:
        return "Super Admin (semua sesi)"

    scopes = user.scopes.filter(aktif=True)
    if scopes.filter(level__in=["UNIVERSITAS", "BIRO"]).exists():
        return "Pimpinan Universitas / LP3M (semua sesi)"

    labels = []
    for s in scopes.filter(level="FAKULTAS"):
        if s.fakultas_id:
            labels.append(f"Fakultas {s.fakultas_id}")
    for s in scopes.filter(level="PRODI"):
        if s.prodi_id:
            labels.append(f"Prodi {s.prodi_id}")

    return " + ".join(labels) if labels else "User"

# =========================================================
# MILESTONE QUICK ACTIONS
# =========================================================

@login_required(login_url="/login/")
def milestone_mark_progress(request, sesi_pk, ms_pk):
    """Mark milestone as PROGRESS."""
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_pk)
    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa update milestone: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    if request.method != "POST":
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    ms = get_object_or_404(MilestoneSesi, pk=ms_pk, sesi=sesi)
    ms.status = MilestoneSesi.StatusMilestone.PROGRESS
    ms.save()

    sesi.terakhir_diupdate_oleh = request.user
    sesi.save(update_fields=["terakhir_diupdate_oleh", "tanggal_diubah"])

    messages.success(request, f"Milestone '{ms.judul}' ditandai sedang berjalan.")
    return redirect("sesi:sesi_detail", pk=sesi.pk)


@login_required(login_url="/login/")
def milestone_mark_selesai(request, sesi_pk, ms_pk):
    """Mark milestone as SELESAI + set tanggal_aktual=today."""
    from datetime import date

    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_pk)
    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa update milestone: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    if request.method != "POST":
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    ms = get_object_or_404(MilestoneSesi, pk=ms_pk, sesi=sesi)
    ms.status = MilestoneSesi.StatusMilestone.SELESAI
    if not ms.tanggal_aktual:
        ms.tanggal_aktual = date.today()
    ms.save()

    sesi.terakhir_diupdate_oleh = request.user
    sesi.save(update_fields=["terakhir_diupdate_oleh", "tanggal_diubah"])

    messages.success(
        request,
        f"Milestone '{ms.judul}' selesai pada {ms.tanggal_aktual.strftime('%d %b %Y')}."
    )

    # Suggest update status sesi kalau ini milestone terakhir
    last_milestone = sesi.milestones.order_by("-urutan").first()
    if last_milestone and last_milestone.pk == ms.pk:
        if sesi.status != "SELESAI":
            messages.info(
                request,
                f"?? Ini milestone terakhir. Pertimbangkan untuk update status sesi menjadi 'Selesai'. "
                f"<a href='{reverse('sesi:sesi_edit', kwargs={'pk': sesi.pk})}' style='color:#1E40AF; font-weight:700;'>Edit Sesi ?</a>"
            )

    # Suggest workflow updates based on which milestone selesai
    judul_lower = ms.judul.lower()
    if "submit" in judul_lower and sesi.status == "PERSIAPAN":
        messages.info(
            request,
            f"?? Milestone Submit sudah selesai. Pertimbangkan ubah status sesi menjadi 'Submitted'. "
            f"<a href='{reverse('sesi:sesi_edit', kwargs={'pk': sesi.pk})}' style='color:#1E40AF; font-weight:700;'>Edit Sesi ?</a>"
        )
    elif "visitasi" in judul_lower and sesi.status not in ["VISITASI_AKTIF", "MENUNGGU_HASIL", "SELESAI"]:
        messages.info(
            request,
            f"?? Milestone Visitasi selesai. Pertimbangkan ubah status sesi. "
            f"<a href='{reverse('sesi:sesi_edit', kwargs={'pk': sesi.pk})}' style='color:#1E40AF; font-weight:700;'>Edit Sesi ?</a>"
        )

    return redirect("sesi:sesi_detail", pk=sesi.pk)


@login_required(login_url="/login/")
def milestone_reset(request, sesi_pk, ms_pk):
    """Reset milestone status ke BELUM dan clear tanggal_aktual."""
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_pk)
    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa reset milestone: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    if request.method != "POST":
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    ms = get_object_or_404(MilestoneSesi, pk=ms_pk, sesi=sesi)
    ms.status = MilestoneSesi.StatusMilestone.BELUM
    ms.tanggal_aktual = None
    ms.save()

    sesi.terakhir_diupdate_oleh = request.user
    sesi.save(update_fields=["terakhir_diupdate_oleh", "tanggal_diubah"])

    messages.success(request, f"Milestone '{ms.judul}' di-reset.")
    return redirect("sesi:sesi_detail", pk=sesi.pk)


@login_required(login_url="/login/")
def milestone_edit(request, sesi_pk, ms_pk):
    """Full edit milestone: judul, tanggal_target, tanggal_aktual, status, catatan."""
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_pk)
    can_edit, reason = can_edit_sesi(request.user, sesi)
    if not can_edit:
        messages.error(request, f"Tidak bisa edit: {reason}")
        return redirect("sesi:sesi_detail", pk=sesi.pk)

    ms = get_object_or_404(MilestoneSesi, pk=ms_pk, sesi=sesi)

    if request.method == "POST":
        # Manual extract dan validasi field
        judul = request.POST.get("judul", "").strip()
        deskripsi = request.POST.get("deskripsi", "").strip()
        tanggal_target = request.POST.get("tanggal_target")
        tanggal_aktual = request.POST.get("tanggal_aktual") or None
        status = request.POST.get("status", ms.status)
        catatan = request.POST.get("catatan", "").strip()

        if not judul or not tanggal_target:
            messages.error(request, "Judul dan tanggal target wajib diisi.")
        else:
            ms.judul = judul
            ms.deskripsi = deskripsi
            ms.tanggal_target = tanggal_target
            ms.tanggal_aktual = tanggal_aktual if tanggal_aktual else None
            ms.status = status
            ms.catatan = catatan
            ms.save()

            sesi.terakhir_diupdate_oleh = request.user
            sesi.save(update_fields=["terakhir_diupdate_oleh", "tanggal_diubah"])

            messages.success(request, f"Milestone '{ms.judul}' berhasil diupdate.")
            return redirect("sesi:sesi_detail", pk=sesi.pk)

    context = {
        "page_title": f"Edit Milestone: {ms.judul}",
        "active_menu": "sesi",
        "sesi": sesi,
        "ms": ms,
        "status_choices": MilestoneSesi.StatusMilestone.choices,
    }
    return render(request, "sesi/milestone_edit.html", context)

# ============================================
# BUNDLE EXPORT (Step 8 Batch 4)
# ============================================

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404


def _build_bundle_tree(sesi, approved_only=False):
    from django.db.models import Q
    from django.db.models import Q
    from django.db.models import Q
    from django.db.models import Q
    """Bangun struktur tree Standar ? SubStandar ? Butir ? Dokumen.
    
    Return dict:
    {
        'standars': [
            {
                'obj': <Standar>,
                'substandars': [
                    {
                        'obj': <SubStandar>,
                        'butirs': [
                            {
                                'obj': <ButirDokumen>,
                                'dokumens': [<Dokumen>, ...],
                            }
                        ]
                    }
                ]
            }
        ],
        'stats': {
            'total_butir': int,
            'total_butir_terisi': int,
            'total_butir_kosong': int,
            'total_dokumen': int,
            'completion_pct': float,
        }
    }
    """
    from master_akreditasi.models import Standar, SubStandar, ButirDokumen
    from dokumen.models import Dokumen
    from master_akreditasi.models_dosen_link import ButirDataDosenMapping

    instrumen = sesi.instrumen
    periode_list = sesi.tahun_periode_list  # property dari Batch 2.5
    instrumen = sesi.instrumen
    periode_list = sesi.tahun_periode_list  # property dari Batch 2.5

    # Pre-fetch butir IDs yang punya ButirDataDosenMapping aktif
    # (untuk inject field 'has_data_dosen_mapping' ke tree butir)
    butir_with_mapping_ids = set(
        ButirDataDosenMapping.objects.filter(
            aktif=True,
            butir__sub_standar__standar__instrumen=instrumen,
        ).values_list('butir_id', flat=True)
    )
    # Build scope filter untuk dokumen
    scope_filter = Q()
    if sesi.kode_prodi:
        scope_filter |= Q(scope_kode_prodi=sesi.kode_prodi)
    if sesi.kode_fakultas:
        scope_filter |= Q(scope_kode_fakultas=sesi.kode_fakultas) | \
                        Q(scope_kode_prodi__isnull=True, scope_kode_fakultas=sesi.kode_fakultas)
    # Selalu include scope UNIVERSITAS (dokumen universal)
    scope_filter |= Q(scope_kode_prodi__isnull=True, scope_kode_fakultas__isnull=True)

    # Ambil semua standar untuk instrumen ini
    standars_qs = Standar.objects.filter(
        instrumen=instrumen
    ).order_by('urutan', 'nomor')

    tree_standars = []
    total_butir = 0
    total_butir_terisi = 0
    total_dokumen = 0

    for std in standars_qs:
        substandars_qs = SubStandar.objects.filter(
            standar=std
        ).order_by('urutan', 'nomor')

        tree_substandars = []
        for sub in substandars_qs:
            butirs_qs = ButirDokumen.objects.filter(
                sub_standar=sub
            ).order_by('urutan', 'kode')

            tree_butirs = []
            for butir in butirs_qs:
                dokumens = Dokumen.objects.filter(
                    butir_dokumen=butir,
                    tahun_akademik__in=periode_list,
                    status='FINAL',  # hanya dokumen FINAL yang masuk bundle
                ).filter(scope_filter).distinct().order_by('tahun_akademik', '-tanggal_dibuat')

                dokumens_all = list(dokumens)
                
                # Filter by approved status kalau approved_only=True
                if approved_only:
                    dokumens_list = [d for d in dokumens_all if d.is_approved()]
                else:
                    dokumens_list = dokumens_all
                total_butir += 1
                total_dokumen += len(dokumens_list)
                if dokumens_list:
                    total_butir_terisi += 1

                tree_butirs.append({
                    'obj': butir,
                    'dokumens': dokumens_list,
                    'count': len(dokumens_list),
                    'has_data_dosen_mapping': butir.id in butir_with_mapping_ids,
                })

            tree_substandars.append({
                'obj': sub,
                'butirs': tree_butirs,
                'butir_count': len(tree_butirs),
            })

        tree_standars.append({
            'obj': std,
            'substandars': tree_substandars,
        })

    total_butir_kosong = total_butir - total_butir_terisi
    completion_pct = (total_butir_terisi / total_butir * 100) if total_butir > 0 else 0

    return {
        'standars': tree_standars,
        'stats': {
            'total_butir': total_butir,
            'total_butir_terisi': total_butir_terisi,
            'total_butir_kosong': total_butir_kosong,
            'total_dokumen': total_dokumen,
            'completion_pct': round(completion_pct, 1),
        }
    }








def _get_prodi_display(sesi):
    """Return string tampilan prodi: 'Jenjang Nama (Kode)'.
    
    Contoh: 'S1 Manajemen (E21)'
    
    Jenjang di-infer dari digit pertama kode:
    - 2x -> S1, 3x -> S2, 4x -> S3, 1x -> D3
    """
    if not sesi.kode_prodi:
        return ''
    nama = getattr(sesi, 'nama_prodi_snapshot', '') or ''
    kode = sesi.kode_prodi
    
    # Cari digit pertama untuk infer jenjang
    jenjang = ''
    for ch in kode:
        if ch.isdigit():
            mapping = {'1': 'D3', '2': 'S1', '3': 'S2', '4': 'S3'}
            jenjang = mapping.get(ch, '')
            break
    
    if jenjang and nama:
        return f'{jenjang} {nama} ({kode})'
    elif nama:
        return f'{nama} ({kode})'
    return kode


def _check_sesi_permission(user, sesi):
    """Cek permission view sesi.
    
    - Superuser/staff -> allow
    - Authenticated user -> allow (scope filtering dihandle di view list, bukan di detail/bundle)
    - Anonymous -> deny
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return True  # allow semua authenticated user untuk bundle view

@login_required(login_url='/login/')
def sesi_bundle(request, sesi_id):
    """Halaman bundle export — tree view dokumen per sesi.
    
    Format read-only untuk submit ke LAM/BAN-PT atau share ke asesor.
    """
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_id)

    # Permission check
    if not _check_sesi_permission(request.user, sesi):
        raise Http404("Sesi tidak ditemukan atau tidak ada akses.")

    tree_data = _build_bundle_tree(sesi)

    # Ambil token share yang aktif (untuk ditampilkan di halaman)
    active_tokens = sesi.bundle_tokens.filter(is_active=True).order_by('-created_at')

    context = {
        'page_title': f'Bundle - {sesi.judul}',
        'active_menu': 'sesi',
        'sesi': sesi,
        'tree': tree_data['standars'],
        'stats': tree_data['stats'],
        'active_tokens': active_tokens,
        'prodi_display': _get_prodi_display(sesi),
        'is_public_view': False,  # flag untuk template
    }
    return render(request, 'sesi/sesi_bundle.html', context)


# ============================================
# BUNDLE PUBLIC (Step 8 Batch 4D)
# ============================================

from django.http import HttpResponseForbidden
from django.views.decorators.csrf import csrf_protect


def sesi_bundle_public(request, token):
    """Halaman bundle publik via token (TANPA LOGIN).
    
    Untuk asesor LAM/BAN-PT atau eksternal yang tidak punya akun.
    """
    try:
        share = BundleShareToken.objects.select_related('sesi__instrumen').get(token=token)
    except BundleShareToken.DoesNotExist:
        return render(request, 'sesi/sesi_bundle_invalid.html', {
            'page_title': 'Link Tidak Valid',
            'reason': 'Token tidak ditemukan. Periksa kembali link yang Anda gunakan.',
        }, status=404)

    if not share.is_valid():
        reason = 'Link ini sudah dinonaktifkan oleh pengelola.'
        if share.expires_at:
            from django.utils import timezone
            if share.expires_at < timezone.now():
                reason = f'Link ini sudah kadaluarsa pada {share.expires_at.strftime("%d %B %Y, %H:%M")} WITA.'
        return render(request, 'sesi/sesi_bundle_invalid.html', {
            'page_title': 'Link Tidak Valid',
            'reason': reason,
        }, status=403)

    # Valid -> track access + render
    share.mark_accessed()
    sesi = share.sesi
    tree_data = _build_bundle_tree(sesi, approved_only=True)

    context = {
        'page_title': f'Bundle Asesor - {sesi.judul}',
        'sesi': sesi,
        'tree': tree_data['standars'],
        'stats': tree_data['stats'],
        'share_token': share,
        'prodi_display': _get_prodi_display(sesi),
        'is_public_view': True,
    }
    return render(request, 'sesi/sesi_bundle_public.html', context)


@login_required(login_url='/login/')
@require_POST
@csrf_protect
def bundle_token_create(request, sesi_id):
    """Generate token share baru untuk sesi."""
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_id)
    if not _check_sesi_permission(request.user, sesi):
        return HttpResponseForbidden('Tidak ada akses untuk sesi ini.')

    label = request.POST.get('label', '').strip()
    expires_raw = request.POST.get('expires_at', '').strip()

    if not label:
        messages.error(request, 'Label token wajib diisi.')
        return redirect('sesi:sesi_bundle', sesi_id=sesi.pk)

    expires_at = None
    if expires_raw:
        from django.utils.dateparse import parse_date
        parsed = parse_date(expires_raw)
        if parsed:
            from django.utils import timezone
            import datetime
            # Set ke akhir hari (23:59:59)
            expires_at = timezone.make_aware(datetime.datetime.combine(parsed, datetime.time(23, 59, 59)))

    token = BundleShareToken.objects.create(
        sesi=sesi,
        token=BundleShareToken.generate_token(),
        label=label[:200],
        expires_at=expires_at,
        created_by=request.user,
    )

    messages.success(
        request,
        f'Token "{token.label}" berhasil dibuat. Copy link dan share ke asesor.'
    )
    return redirect('sesi:sesi_bundle', sesi_id=sesi.pk)


@login_required(login_url='/login/')
@require_POST
@csrf_protect
def bundle_token_revoke(request, sesi_id, token_id):
    """Revoke (nonaktifkan) token share."""
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_id)
    if not _check_sesi_permission(request.user, sesi):
        return HttpResponseForbidden('Tidak ada akses untuk sesi ini.')

    token = get_object_or_404(BundleShareToken, pk=token_id, sesi=sesi)
    token.is_active = False
    token.save(update_fields=['is_active'])

    messages.success(request, f'Token "{token.label}" telah dinonaktifkan.')
    return redirect('sesi:sesi_bundle', sesi_id=sesi.pk)


# ============================================
# BUNDLE ZIP EXPORT (Step 8 Batch 4E)
# ============================================

def _sanitize_filename(s, max_len=80):
    """Bersihkan string jadi safe filename (no special chars, no spaces)."""
    s = stdre.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(s))
    s = stdre.sub(r'\s+', '_', s.strip())
    s = stdre.sub(r'_+', '_', s)
    return s[:max_len].strip('_.')


def _build_bundle_zip(sesi, include_local_files=True, approved_only=False):
    """Build ZIP file bundle dalam memory. Return (bytes, filename)."""
    from dokumen.models import DokumenRevisi
    from django.utils import timezone
    import datetime

    tree_data = _build_bundle_tree(sesi, approved_only=approved_only)
    stats = tree_data['stats']

    # Manifest root
    manifest = {
        'sesi': {
            'id': sesi.pk,
            'judul': sesi.judul,
            'instrumen': str(sesi.instrumen),
            'kode_prodi': sesi.kode_prodi or '',
            'nama_prodi': getattr(sesi, 'nama_prodi_snapshot', '') or '',
            'prodi_display': _get_prodi_display(sesi),
            'kode_fakultas': sesi.kode_fakultas or '',
            'tahun_ts': sesi.tahun_ts,
            'status': sesi.get_status_display(),
            'jumlah_tahun_evaluasi': getattr(sesi, 'jumlah_tahun_evaluasi', None),
            'periode_list': getattr(sesi, 'tahun_periode_list', []),
        },
        'exported_at': timezone.now().isoformat(),
        'exported_by': 'SIAKRED UNISAN',
        'stats': stats,
        'dokumen': [],
    }

    # Bikin ZIP di memory
    buf = stdio.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # README.txt
        readme = (
            f"BUNDLE DOKUMEN AKREDITASI\n"
            f"==========================\n\n"
            f"Sesi: {sesi.judul}\n"
            f"Instrumen: {sesi.instrumen}\n"
            f"Tahun TS: {sesi.tahun_ts}\n"
            f"Periode Evaluasi: {', '.join(str(p) for p in getattr(sesi, 'tahun_periode_list', []))}\n\n"
            f"Diekspor: {timezone.now().strftime('%d %B %Y, %H:%M')} WITA\n\n"
            f"STATISTIK:\n"
            f"- Total Butir: {stats['total_butir']}\n"
            f"- Terisi: {stats['total_butir_terisi']}\n"
            f"- Kosong: {stats['total_butir_kosong']}\n"
            f"- Total Dokumen: {stats['total_dokumen']}\n"
            f"- Completion: {stats['completion_pct']}%\n\n"
            f"STRUKTUR FOLDER:\n"
            f"Dokumen dikelompokkan per Standar/Sub-Standar/Butir.\n"
            f"File dokumen yang disimpan di Google Drive tidak disertakan\n"
            f"langsung dalam ZIP ini, tetapi tautan aksesnya tercatat di\n"
            f"'manifest.json'.\n\n"
            f"Lihat 'manifest.json' untuk metadata lengkap.\n\n"
            f"--\n"
            f"SIAKRED UNISAN - Sistem Informasi Akreditasi\n"
            f"Universitas Ichsan Gorontalo\n"
        )
        zf.writestr('README.txt', readme)

        # Iterate tree
        for std_item in tree_data['standars']:
            std = std_item['obj']
            std_folder = f"{_sanitize_filename(str(std.nomor))}-{_sanitize_filename(std.nama, 60)}"

            for sub_item in std_item['substandars']:
                sub = sub_item['obj']
                sub_folder = f"{_sanitize_filename(str(sub.nomor))}-{_sanitize_filename(sub.nama, 50)}"

                for butir_item in sub_item['butirs']:
                    butir = butir_item['obj']
                    butir_folder = f"{_sanitize_filename(butir.kode)}-{_sanitize_filename(butir.nama_dokumen, 40)}"

                    for dok in butir_item['dokumens']:
                        # Ambil revisi terakhir yang aktif
                        rev = dok.revisi.filter(aktif=True).order_by('-nomor_revisi').first()
                        if not rev:
                            continue

                        entry = {
                            'standar': f"{std.nomor} - {std.nama}",
                            'sub_standar': f"{sub.nomor} - {sub.nama}",
                            'butir': f"{butir.kode} - {butir.nama_dokumen}",
                            'dokumen_id': dok.pk,
                            'judul': dok.judul,
                            'tahun_akademik': dok.tahun_akademik,
                            'status': dok.get_status_display() if hasattr(dok, 'get_status_display') else dok.status,
                            'nomor_revisi': rev.nomor_revisi,
                            'file_size_kb': rev.file_size_kb,
                            'mime_type': rev.mime_type,
                            'storage_type': rev.storage_type,
                            'uploaded_at': rev.tanggal_upload.isoformat() if rev.tanggal_upload else None,
                        }

                        # Safe filename: kode_butir + judul + ext
                        ext = rev.extension or ''
                        if ext and not ext.startswith('.'):
                            ext = '.' + ext
                        base_name = f"{_sanitize_filename(butir.kode)}_{_sanitize_filename(dok.judul, 60)}"
                        rev_suffix = f"_r{rev.nomor_revisi}" if rev.nomor_revisi and rev.nomor_revisi > 1 else ''
                        safe_name = f"{base_name}{rev_suffix}{ext}"

                        zip_path = f"{std_folder}/{sub_folder}/{butir_folder}/{safe_name}"

                        if rev.storage_type == 'LOCAL' and include_local_files and rev.file:
                            try:
                                with rev.file.open('rb') as f:
                                    zf.writestr(zip_path, f.read())
                                entry['zip_path'] = zip_path
                                entry['included'] = True
                            except Exception as e:
                                entry['included'] = False
                                entry['error'] = f'Gagal baca file: {str(e)[:100]}'
                        elif rev.storage_type == 'GDRIVE':
                            entry['included'] = False
                            entry['gdrive_url'] = rev.gdrive_url
                            entry['gdrive_file_id'] = rev.gdrive_file_id
                            entry['note'] = 'File disimpan di Google Drive, lihat gdrive_url untuk akses.'
                        else:
                            entry['included'] = False
                            entry['note'] = 'File tidak tersedia (tidak ada file lokal dan bukan GDrive).'

                        manifest['dokumen'].append(entry)

        # Tulis manifest.json terakhir
        zf.writestr(
            'manifest.json',
            json.dumps(manifest, indent=2, ensure_ascii=False, default=str)
        )

    buf.seek(0)

    # Filename: LAMEMBA-E21-2025-2026-20260423.zip
    today = timezone.now().strftime('%Y%m%d')
    instrumen_tag = _sanitize_filename(
        getattr(sesi.instrumen, 'nama_singkat', None) or str(sesi.instrumen),
        20
    )
    prodi_tag = _sanitize_filename(sesi.kode_prodi or 'UNIV', 10)
    tahun_tag = sesi.tahun_ts.replace('/', '-') if sesi.tahun_ts else 'TS'
    filename = f"bundle_{instrumen_tag}_{prodi_tag}_{tahun_tag}_{today}.zip"

    return buf.getvalue(), filename


@login_required(login_url='/login/')
def sesi_bundle_zip(request, sesi_id):
    """Download bundle sebagai ZIP (internal, butuh login)."""
    sesi = get_object_or_404(SesiAkreditasi, pk=sesi_id)
    if not _check_sesi_permission(request.user, sesi):
        return HttpResponseForbidden('Tidak ada akses untuk sesi ini.')

    zip_bytes, filename = _build_bundle_zip(sesi)

    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(zip_bytes)
    return response


def sesi_bundle_zip_public(request, token):
    """Download bundle ZIP via token publik (tanpa login)."""
    try:
        share = BundleShareToken.objects.select_related('sesi').get(token=token)
    except BundleShareToken.DoesNotExist:
        return HttpResponse('Token tidak ditemukan', status=404)

    if not share.is_valid():
        return HttpResponse('Token tidak valid atau kadaluarsa', status=403)

    share.mark_accessed()
    zip_bytes, filename = _build_bundle_zip(share.sesi, approved_only=True)

    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(zip_bytes)
    return response

