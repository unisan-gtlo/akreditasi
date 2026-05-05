"""
Views untuk master_akreditasi — list & detail Instrumen, Standar, Mapping.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q

from .models import (
    Instrumen,
    Standar,
    SubStandar,
    ButirDokumen,
    MappingProdiInstrumen,
)



@login_required
def instrumen_list(request):
    """List semua instrumen akreditasi."""
    instrumen_qs = (
        Instrumen.objects.filter(aktif=True)
        .annotate(
            n_standar=Count("standar", distinct=True),
        )
        .order_by("urutan", "kode")
    )

    context = {
        "page_title": "Instrumen Akreditasi",
        "active_menu": "instrumen",
        "instrumen_list": instrumen_qs,
    }
    return render(request, "master_akreditasi/instrumen_list.html", context)


@login_required
def instrumen_detail(request, pk):
    """Detail instrumen — list standar-nya."""
    instrumen = get_object_or_404(Instrumen, pk=pk, aktif=True)
    standar_qs = instrumen.standar.filter(aktif=True).order_by("urutan", "nomor")

    context = {
        "page_title": f"{instrumen.nama_singkat}",
        "active_menu": "instrumen",
        "instrumen": instrumen,
        "standar_list": standar_qs,
    }
    return render(request, "master_akreditasi/instrumen_detail.html", context)


@login_required
def standar_list(request):
    """List semua standar (flat) dengan filter instrumen."""
    instrumen_id = request.GET.get("instrumen")

    standar_qs = Standar.objects.filter(aktif=True).select_related("instrumen")
    if instrumen_id:
        standar_qs = standar_qs.filter(instrumen_id=instrumen_id)
    standar_qs = standar_qs.order_by("instrumen__urutan", "urutan", "nomor")

    instrumen_all = Instrumen.objects.filter(aktif=True).order_by("urutan")

    context = {
        "page_title": "Standar / Kriteria Akreditasi",
        "active_menu": "standar",
        "standar_list": standar_qs,
        "instrumen_all": instrumen_all,
        "filter_instrumen": instrumen_id,
    }
    return render(request, "master_akreditasi/standar_list.html", context)


@login_required
def standar_detail(request, pk):
    """Detail standar — list sub-standar bertingkat + butir dokumen."""
    standar = get_object_or_404(Standar, pk=pk, aktif=True)

    # Ambil sub-standar level 1 (parent=null)
    substandar_root = standar.sub_standar.filter(
        parent__isnull=True, aktif=True
    ).order_by("urutan", "nomor")

    context = {
        "page_title": f"{standar.instrumen.label_standar} {standar.nomor}",
        "active_menu": "standar",
        "standar": standar,
        "substandar_root": substandar_root,
    }
    return render(request, "master_akreditasi/standar_detail.html", context)


@login_required
def mapping_list(request):
    """List mapping prodi ↔ instrumen, grouped by instrumen."""
    mappings = MappingProdiInstrumen.objects.filter(
        aktif=True
    ).select_related("instrumen").order_by("instrumen__urutan", "kode_prodi")

    # Group by instrumen
    grouped = {}
    for m in mappings:
        key = m.instrumen.id
        if key not in grouped:
            grouped[key] = {
                "instrumen": m.instrumen,
                "prodi_list": [],
            }
        grouped[key]["prodi_list"].append(m)

    # Untuk dropdown modal CRUD (semua instrumen, ga cuma yang aktif)
    all_instrumen = Instrumen.objects.all().order_by("urutan", "nama_singkat")
    
    context = {
        "page_title": "Mapping Prodi ↔ Instrumen",
        "active_menu": "mapping",
        "grouped_mapping": list(grouped.values()),
        "total_mapping": mappings.count(),
        "all_instrumen": all_instrumen,
    }
    return render(request, "master_akreditasi/mapping_list.html", context)

# ============================================
# IMPORT EXCEL (Batch 2-3 akan lengkap)
# ============================================

from django.contrib.auth.decorators import user_passes_test


def superadmin_required(user):
    """Hanya Super Admin Pustikom yang bisa akses Import Excel."""
    return user.is_authenticated and user.is_superuser


@user_passes_test(superadmin_required, login_url="/app/")
def import_excel_home(request):
    """Halaman utama Import Excel — daftar history + tombol upload baru."""
    from .models import ImportLog
    logs = ImportLog.objects.select_related("instrumen", "uploaded_by").all()[:50]

    context = {
        "page_title": "Import Excel Master",
        "active_menu": "import",
        "logs": logs,
    }
    return render(request, "master_akreditasi/import_home.html", context)

# ============================================
# IMPORT EXCEL — Full Flow
# ============================================

from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import ImportLog, ImportLogItem
from .forms import ExcelUploadForm
from .import_parser import ExcelImportParser


def superadmin_required(user):
    """Hanya Super Admin Pustikom yang bisa akses Import Excel."""
    return user.is_authenticated and user.is_superuser


@user_passes_test(superadmin_required, login_url="/app/")
def import_excel_home(request):
    """Halaman utama Import Excel — daftar history + tombol upload baru."""
    logs = ImportLog.objects.select_related("instrumen", "uploaded_by").all()[:50]

    context = {
        "page_title": "Import Excel Master",
        "active_menu": "import",
        "logs": logs,
    }
    return render(request, "master_akreditasi/import_home.html", context)


@user_passes_test(superadmin_required, login_url="/app/")
def import_upload(request):
    """Halaman upload + parsing + redirect ke preview."""

    if request.method == "POST":
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            instrumen = form.cleaned_data["instrumen"]
            mode = form.cleaned_data["mode"]
            excel_file = form.cleaned_data["file"]

            # Save file + create ImportLog first
            import_log = ImportLog.objects.create(
                file_name=excel_file.name,
                file_size_kb=int(excel_file.size / 1024),
                file=excel_file,
                instrumen=instrumen,
                mode=mode,
                uploaded_by=request.user,
                status=ImportLog.Status.PENDING,
            )

            # Re-open the saved file for parsing
            try:
                import_log.file.seek(0)
                parser = ExcelImportParser(import_log.file, instrumen)
                result = parser.parse_and_validate(mode=mode)
            except Exception as e:
                import_log.status = ImportLog.Status.FAILED
                import_log.error_message = f"Gagal parse file: {str(e)}"
                import_log.save()
                messages.error(request, f"Gagal memproses file: {str(e)}")
                return redirect("master_akreditasi:import_home")

            if result.has_global_errors:
                import_log.status = ImportLog.Status.FAILED
                import_log.error_message = "\n".join(result.global_errors)
                import_log.save()
                messages.error(request, "File Excel tidak valid. Lihat detail di bawah.")
                return redirect("master_akreditasi:import_preview", pk=import_log.pk)

            # Simpan tiap row sebagai ImportLogItem
            all_rows = result.substandar_rows + result.butir_rows
            for row in all_rows:
                # Hapus field internal (_wajib_bool, _ukuran_int) dari raw_data
                raw = {k: v for k, v in row.data.items() if not k.startswith("_")}

                # Map action ke ItemStatus choice
                status_map = {
                    "WILL_CREATE": ImportLogItem.ItemStatus.WILL_CREATE,
                    "WILL_UPDATE": ImportLogItem.ItemStatus.WILL_UPDATE,
                    "DUPLICATE":   ImportLogItem.ItemStatus.DUPLICATE,
                    "INVALID":     ImportLogItem.ItemStatus.INVALID,
                }
                ImportLogItem.objects.create(
                    import_log=import_log,
                    sheet=row.sheet,
                    row_number=row.row_number,
                    raw_data=raw,
                    status=status_map.get(row.action, ImportLogItem.ItemStatus.INVALID),
                    error_detail="\n".join(row.errors) if row.errors else "",
                )

            # Update counter di import_log
            import_log.total_rows = result.total_rows
            import_log.valid_rows = result.valid_rows
            import_log.error_rows = result.error_rows
            import_log.status = ImportLog.Status.PREVIEWED
            import_log.save()

            messages.info(
                request,
                f"File berhasil di-parse. {result.valid_rows}/{result.total_rows} baris valid. "
                f"Silakan review dan klik Commit untuk menyimpan."
            )
            return redirect("master_akreditasi:import_preview", pk=import_log.pk)
    else:
        form = ExcelUploadForm()

    context = {
        "page_title": "Upload Excel",
        "active_menu": "import",
        "form": form,
    }
    return render(request, "master_akreditasi/import_upload.html", context)


@user_passes_test(superadmin_required, login_url="/app/")
def import_preview(request, pk):
    """Tampilkan hasil parsing — admin review lalu klik Commit/Cancel."""
    import_log = get_object_or_404(ImportLog, pk=pk)

    # Separate items per sheet
    substandar_items = import_log.items.filter(sheet="SUBSTANDAR").order_by("row_number")
    butir_items = import_log.items.filter(sheet="BUTIR").order_by("row_number")

    context = {
        "page_title": "Preview Import",
        "active_menu": "import",
        "import_log": import_log,
        "substandar_items": substandar_items,
        "butir_items": butir_items,
        "can_commit": import_log.is_valid_for_commit,
    }
    return render(request, "master_akreditasi/import_preview.html", context)


@user_passes_test(superadmin_required, login_url="/app/")
def import_commit(request, pk):
    """Eksekusi actual import ke database."""
    import_log = get_object_or_404(ImportLog, pk=pk)

    if request.method != "POST":
        return redirect("master_akreditasi:import_preview", pk=pk)

    if not import_log.is_valid_for_commit:
        messages.error(request, "Import log ini tidak bisa di-commit.")
        return redirect("master_akreditasi:import_preview", pk=pk)

    instrumen = import_log.instrumen

    # Counters
    ss_created = 0
    ss_updated = 0
    b_created = 0
    b_updated = 0
    errors = []

    try:
        with transaction.atomic():
            # STEP 1: Proses SubStandar dulu (urutan: yang tanpa parent dulu, lalu dengan parent)
            ss_items = list(import_log.items.filter(
                sheet="SUBSTANDAR",
                status__in=[
                    ImportLogItem.ItemStatus.WILL_CREATE,
                    ImportLogItem.ItemStatus.WILL_UPDATE,
                ],
            ).order_by("row_number"))

            # 2 pass: pass 1 tanpa parent, pass 2 dengan parent
            pending = ss_items[:]
            max_passes = 5
            while pending and max_passes > 0:
                still_pending = []
                for item in pending:
                    created_or_updated = self_process_substandar_item(
                        item, instrumen,
                    )
                    if created_or_updated is None:
                        # parent belum ada, tunda
                        still_pending.append(item)
                    else:
                        if created_or_updated == "CREATED":
                            ss_created += 1
                            item.status = ImportLogItem.ItemStatus.CREATED
                        else:
                            ss_updated += 1
                            item.status = ImportLogItem.ItemStatus.UPDATED
                        item.save()

                if len(still_pending) == len(pending):
                    # tidak ada progress, parent tidak ketemu
                    for item in still_pending:
                        item.status = ImportLogItem.ItemStatus.FAILED
                        item.error_detail = "Parent tidak bisa diresolve"
                        item.save()
                    errors.append("Ada sub-standar dengan parent yang tidak bisa diresolve")
                    break
                pending = still_pending
                max_passes -= 1

            # STEP 2: Proses ButirDokumen
            butir_items = import_log.items.filter(
                sheet="BUTIR",
                status__in=[
                    ImportLogItem.ItemStatus.WILL_CREATE,
                    ImportLogItem.ItemStatus.WILL_UPDATE,
                ],
            ).order_by("row_number")

            for item in butir_items:
                result = self_process_butir_item(item, instrumen)
                if result == "CREATED":
                    b_created += 1
                    item.status = ImportLogItem.ItemStatus.CREATED
                elif result == "UPDATED":
                    b_updated += 1
                    item.status = ImportLogItem.ItemStatus.UPDATED
                else:
                    item.status = ImportLogItem.ItemStatus.FAILED
                    item.error_detail = result or "Unknown error"
                item.save()

            # Mark DUPLICATE items as SKIPPED
            import_log.items.filter(status=ImportLogItem.ItemStatus.DUPLICATE).update(
                status=ImportLogItem.ItemStatus.SKIPPED
            )

        # Finalize
        import_log.substandar_created = ss_created
        import_log.substandar_updated = ss_updated
        import_log.butir_created = b_created
        import_log.butir_updated = b_updated
        import_log.status = ImportLog.Status.COMMITTED
        import_log.waktu_commit = timezone.now()
        import_log.save()

        messages.success(
            request,
            f"Import berhasil! SubStandar: {ss_created} baru, {ss_updated} di-update. "
            f"Butir Dokumen: {b_created} baru, {b_updated} di-update."
        )
    except Exception as e:
        import_log.status = ImportLog.Status.FAILED
        import_log.error_message = f"Commit gagal: {str(e)}"
        import_log.save()
        messages.error(request, f"Commit gagal: {str(e)}")

    return redirect("master_akreditasi:import_preview", pk=pk)


@user_passes_test(superadmin_required, login_url="/app/")
def import_cancel(request, pk):
    """Batalkan import — mark sebagai CANCELLED."""
    import_log = get_object_or_404(ImportLog, pk=pk)

    if request.method == "POST":
        if import_log.is_final:
            messages.warning(request, "Import log ini sudah final, tidak bisa dibatalkan.")
        else:
            import_log.status = ImportLog.Status.CANCELLED
            import_log.save()
            messages.info(request, "Import dibatalkan.")

    return redirect("master_akreditasi:import_home")


# ============================================
# HELPERS untuk commit (bukan method class)
# ============================================

def self_process_substandar_item(item, instrumen):
    """
    Process 1 ImportLogItem (sheet=SUBSTANDAR).
    Return: 'CREATED' / 'UPDATED' / None (kalau parent belum ada).
    """
    data = item.raw_data
    nomor_std = str(data.get("nomor_standar", "")).strip()
    nomor_ss  = str(data.get("nomor_substandar", "")).strip()
    nomor_par = str(data.get("nomor_parent", "")).strip()

    try:
        standar = Standar.objects.get(instrumen=instrumen, nomor=nomor_std)
    except Standar.DoesNotExist:
        return None

    parent = None
    if nomor_par:
        parent = SubStandar.objects.filter(
            standar__instrumen=instrumen, nomor=nomor_par
        ).first()
        if not parent:
            return None  # parent belum dibuat, tunda

    ss, created = SubStandar.objects.update_or_create(
        standar=standar,
        nomor=nomor_ss,
        defaults={
            "parent": parent,
            "nama": data.get("nama", "").strip(),
            "deskripsi": data.get("deskripsi", "").strip(),
            "aktif": True,
        },
    )
    item.substandar = ss
    return "CREATED" if created else "UPDATED"


def self_process_butir_item(item, instrumen):
    """Process 1 ButirDokumen item. Return 'CREATED' / 'UPDATED' / error message string."""
    data = item.raw_data
    nomor_ss = str(data.get("nomor_substandar", "")).strip()
    kode     = str(data.get("kode_butir", "")).strip()

    try:
        sub_standar = SubStandar.objects.get(
            standar__instrumen=instrumen, nomor=nomor_ss
        )
    except SubStandar.DoesNotExist:
        return f"Sub-standar '{nomor_ss}' tidak ditemukan"

    # Parse wajib
    wajib_str = str(data.get("wajib", "")).strip().upper()
    wajib_bool = wajib_str in ["Y", "YA", "YES", "TRUE", "1", "WAJIB"]

    # Parse ukuran_max
    try:
        ukuran = int(float(data.get("ukuran_max", "50") or "50"))
    except (ValueError, TypeError):
        ukuran = 50

    fmt = str(data.get("format", "PDF")).strip().upper() or "PDF"
    kategori = str(data.get("kategori", "")).strip().upper()
    akses = str(data.get("akses", "INTERNAL")).strip().upper() or "INTERNAL"

    butir, created = ButirDokumen.objects.update_or_create(
        sub_standar=sub_standar,
        kode=kode,
        defaults={
            "nama_dokumen": data.get("nama_dokumen", "").strip(),
            "deskripsi": data.get("deskripsi", "").strip(),
            "panduan_dokumen": data.get("panduan_dokumen", "").strip(),
            "kategori_kepemilikan": kategori,
            "wajib": wajib_bool,
            "format_diterima": fmt,
            "ukuran_max_mb": ukuran,
            "status_akses_default": akses,
            "aktif": True,
        },
    )
    item.butir = butir
    return "CREATED" if created else "UPDATED"

# ============================================
# DOWNLOAD TEMPLATE EXCEL
# ============================================

from django.http import HttpResponse
from .template_generator import generate_template


@user_passes_test(superadmin_required, login_url="/app/")
def download_template(request, instrumen_id):
    """Download template Excel untuk instrumen tertentu."""
    instrumen = get_object_or_404(Instrumen, pk=instrumen_id, aktif=True)

    try:
        excel_stream = generate_template(instrumen)
    except Exception as e:
        messages.error(request, f"Gagal generate template: {str(e)}")
        return redirect("master_akreditasi:import_home")

    # Build filename
    safe_kode = instrumen.kode.lower().replace(" ", "_")
    filename = f"template_siakred_{safe_kode}.xlsx"

    response = HttpResponse(
        excel_stream.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@user_passes_test(superadmin_required, login_url="/app/")
def download_template_picker(request):
    """Halaman pemilihan instrumen sebelum download template."""
    instrumen_list = Instrumen.objects.filter(aktif=True).order_by("urutan")

    context = {
        "page_title": "Download Template Excel",
        "active_menu": "import",
        "instrumen_list": instrumen_list,
    }
    return render(request, "master_akreditasi/download_template.html", context)


# ============================================================
# CRUD MAPPING PRODI (Modal Popup)
# ============================================================

def _is_admin(user):
    """Helper cek apakah user superuser atau staff."""
    return user.is_authenticated and (user.is_superuser or user.is_staff)


@login_required(login_url='/login/')
def mapping_create(request):
    """Tambah mapping prodi baru via AJAX POST."""
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST
    from .models import MappingProdiInstrumen, Instrumen
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Akses ditolak. Hanya admin yang bisa kelola mapping.'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method tidak diizinkan'}, status=405)
    
    instrumen_id = request.POST.get('instrumen_id', '').strip()
    kode_prodi = request.POST.get('kode_prodi', '').strip().upper()
    nama_prodi = request.POST.get('nama_prodi', '').strip()
    catatan = request.POST.get('catatan', '').strip()
    aktif = request.POST.get('aktif') == 'on'
    
    # Validasi
    errors = {}
    if not instrumen_id:
        errors['instrumen_id'] = 'Pilih instrumen'
    if not kode_prodi:
        errors['kode_prodi'] = 'Kode prodi wajib diisi'
    elif len(kode_prodi) < 2:
        errors['kode_prodi'] = 'Kode prodi minimal 2 karakter'
    if not nama_prodi:
        errors['nama_prodi'] = 'Nama prodi wajib diisi'
    elif len(nama_prodi) < 3:
        errors['nama_prodi'] = 'Nama prodi minimal 3 karakter'
    
    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)
    
    # Validasi instrumen exists
    try:
        instrumen = Instrumen.objects.get(pk=int(instrumen_id))
    except (Instrumen.DoesNotExist, ValueError):
        return JsonResponse({'success': False, 'errors': {'instrumen_id': 'Instrumen tidak valid'}}, status=400)
    
    # Cek duplikat kode_prodi + instrumen
    if MappingProdiInstrumen.objects.filter(kode_prodi=kode_prodi, instrumen=instrumen).exists():
        return JsonResponse({
            'success': False,
            'errors': {'kode_prodi': f'Mapping {kode_prodi} ke instrumen ini sudah ada'},
        }, status=400)
    
    # Create
    mapping = MappingProdiInstrumen.objects.create(
        instrumen=instrumen,
        kode_prodi=kode_prodi,
        nama_prodi=nama_prodi,
        catatan=catatan,
        aktif=aktif,
    )
    
    return JsonResponse({
        'success': True,
        'message': f'Mapping {kode_prodi} - {nama_prodi} berhasil ditambahkan',
        'data': {
            'id': mapping.id,
            'kode_prodi': mapping.kode_prodi,
            'nama_prodi': mapping.nama_prodi,
            'aktif': mapping.aktif,
        },
    })


@login_required(login_url='/login/')
def mapping_edit(request, pk):
    """Edit mapping prodi via AJAX. GET return data, POST submit."""
    from django.http import JsonResponse
    from django.shortcuts import get_object_or_404
    from .models import MappingProdiInstrumen, Instrumen
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Akses ditolak'}, status=403)
    
    mapping = get_object_or_404(MappingProdiInstrumen, pk=pk)
    
    if request.method == 'GET':
        # Return data untuk prefill form
        return JsonResponse({
            'success': True,
            'data': {
                'id': mapping.id,
                'instrumen_id': mapping.instrumen_id,
                'kode_prodi': mapping.kode_prodi,
                'nama_prodi': mapping.nama_prodi,
                'catatan': mapping.catatan or '',
                'aktif': mapping.aktif,
            },
        })
    
    if request.method == 'POST':
        instrumen_id = request.POST.get('instrumen_id', '').strip()
        kode_prodi = request.POST.get('kode_prodi', '').strip().upper()
        nama_prodi = request.POST.get('nama_prodi', '').strip()
        catatan = request.POST.get('catatan', '').strip()
        aktif = request.POST.get('aktif') == 'on'
        
        errors = {}
        if not instrumen_id:
            errors['instrumen_id'] = 'Pilih instrumen'
        if not kode_prodi:
            errors['kode_prodi'] = 'Kode prodi wajib diisi'
        if not nama_prodi:
            errors['nama_prodi'] = 'Nama prodi wajib diisi'
        
        if errors:
            return JsonResponse({'success': False, 'errors': errors}, status=400)
        
        try:
            instrumen = Instrumen.objects.get(pk=int(instrumen_id))
        except (Instrumen.DoesNotExist, ValueError):
            return JsonResponse({'success': False, 'errors': {'instrumen_id': 'Instrumen tidak valid'}}, status=400)
        
        # Cek duplikat (exclude diri sendiri)
        if MappingProdiInstrumen.objects.filter(
            kode_prodi=kode_prodi,
            instrumen=instrumen,
        ).exclude(pk=pk).exists():
            return JsonResponse({
                'success': False,
                'errors': {'kode_prodi': f'Mapping {kode_prodi} ke instrumen ini sudah ada'},
            }, status=400)
        
        mapping.instrumen = instrumen
        mapping.kode_prodi = kode_prodi
        mapping.nama_prodi = nama_prodi
        mapping.catatan = catatan
        mapping.aktif = aktif
        mapping.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Mapping {kode_prodi} - {nama_prodi} berhasil diupdate',
        })
    
    return JsonResponse({'success': False, 'error': 'Method tidak diizinkan'}, status=405)


@login_required(login_url='/login/')
def mapping_delete(request, pk):
    """Hapus mapping prodi via AJAX POST."""
    from django.http import JsonResponse
    from django.shortcuts import get_object_or_404
    from django.views.decorators.http import require_POST
    from .models import MappingProdiInstrumen
    
    if not _is_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Akses ditolak'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method tidak diizinkan'}, status=405)
    
    mapping = get_object_or_404(MappingProdiInstrumen, pk=pk)
    
    # Cek apakah ada dokumen yang refer ke prodi ini (warning, but still allow delete)
    from dokumen.models import Dokumen
    dokumen_count = Dokumen.objects.filter(scope_kode_prodi=mapping.kode_prodi).count()
    
    info = f'Mapping {mapping.kode_prodi} - {mapping.nama_prodi} berhasil dihapus'
    if dokumen_count > 0:
        info += f' (Catatan: ada {dokumen_count} dokumen masih refer ke prodi ini)'
    
    mapping.delete()
    
    return JsonResponse({
        'success': True,
        'message': info,
    })

