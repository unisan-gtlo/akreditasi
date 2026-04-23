"""Forms untuk Sesi Akreditasi."""
from django import forms
from django.utils.translation import gettext_lazy as _
from django.db import connection

from .models import SesiAkreditasi
from master_akreditasi.models import Instrumen


def get_prodi_choices():
    """Get list prodi dari master.program_studi cross-schema."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT kode_prodi, nama_prodi, kode_fakultas
                FROM master.program_studi
                ORDER BY kode_prodi
            """)
            rows = cursor.fetchall()
            return [(row[0], f"{row[0]} -- {row[1]}") for row in rows], {row[0]: (row[1], row[2]) for row in rows}
    except Exception:
        return [], {}


def get_mapping_prodi_instrumen():
    """
    Get mapping prodi -> list instrumen IDs.
    Return dict: {'T21': [3], 'E21': [4], ...}
    """
    from master_akreditasi.models import MappingProdiInstrumen
    mapping = {}
    try:
        for m in MappingProdiInstrumen.objects.filter(aktif=True).select_related("instrumen"):
            mapping.setdefault(m.kode_prodi, []).append(m.instrumen_id)
    except Exception:
        pass
    return mapping


class SesiCreateForm(forms.ModelForm):
    """Form untuk buat sesi baru."""

    kode_prodi = forms.ChoiceField(
        label=_("Program Studi"),
        choices=[],
        widget=forms.Select(attrs={"class": "form-input"}),
        help_text=_("Pilih prodi yang akan diakreditasi"),
    )

    auto_generate_milestones = forms.BooleanField(
        label=_("Auto-generate Default Milestones"),
        required=False,
        initial=True,
        help_text=_("Otomatis buat 5 milestone default"),
    )

    class Meta:
        model = SesiAkreditasi
        fields = [
            "instrumen",
            "tipe",
            "tahun_ts",
            "jumlah_tahun_evaluasi",
            "tanggal_mulai",
            "tanggal_target_selesai",
            "deadline_upload_dokumen",
            "deskripsi",
        ]
        widgets = {
            "instrumen": forms.Select(attrs={"class": "form-input", "id": "id_instrumen"}),
            "tipe": forms.Select(attrs={"class": "form-input"}),
            "tahun_ts": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Contoh: 2025/2026",
            }),
            "jumlah_tahun_evaluasi": forms.Select(
                choices=[(3, "3 Tahun (TS-2 s/d TS)"), (4, "4 Tahun (TS-3 s/d TS)"), (5, "5 Tahun (TS-4 s/d TS)")],
                attrs={"class": "form-input", "id": "id_jumlah_tahun_evaluasi"},
            ),
            "tanggal_mulai": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "tanggal_target_selesai": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "deadline_upload_dokumen": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "deskripsi": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Deskripsi atau tujuan sesi (opsional)",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate prodi choices
        choices, prodi_map = get_prodi_choices()
        self.fields["kode_prodi"].choices = [("", "-- Pilih Prodi --")] + choices
        self.prodi_map = prodi_map

        # Get mapping prodi -> instrumen (untuk dynamic filter di template)
        self.mapping_prodi_instrumen = get_mapping_prodi_instrumen()

        # Filter instrumen aktif
        self.fields["instrumen"].queryset = Instrumen.objects.filter(aktif=True).order_by("urutan")

    def clean(self):
        cleaned = super().clean()
        kode_prodi = cleaned.get("kode_prodi")
        instrumen = cleaned.get("instrumen")
        tahun_ts = cleaned.get("tahun_ts")
        tgl_mulai = cleaned.get("tanggal_mulai")
        tgl_target = cleaned.get("tanggal_target_selesai")

        if tahun_ts and "/" in tahun_ts:
            try:
                start, end = tahun_ts.split("/")
                if int(end) - int(start) != 1:
                    self.add_error("tahun_ts", "Format tahun harus berurutan, contoh: 2025/2026")
            except (ValueError, IndexError):
                self.add_error("tahun_ts", "Format tahun salah. Contoh yang benar: 2025/2026")
        elif tahun_ts:
            self.add_error("tahun_ts", "Format harus YYYY/YYYY, contoh: 2025/2026")

        if kode_prodi and instrumen and tahun_ts:
            existing = SesiAkreditasi.objects.filter(
                kode_prodi=kode_prodi,
                instrumen=instrumen,
                tahun_ts=tahun_ts,
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    f"Sudah ada sesi untuk Prodi {kode_prodi} - Instrumen {instrumen.nama_singkat} - "
                    f"TS {tahun_ts}. Tidak bisa duplikasi."
                )

        if tgl_mulai and tgl_target and tgl_target <= tgl_mulai:
            self.add_error("tanggal_target_selesai", "Tanggal target harus setelah tanggal mulai")

        return cleaned


class SesiEditForm(forms.ModelForm):
    """Form edit metadata sesi."""

    class Meta:
        model = SesiAkreditasi
        fields = [
            "judul", "deskripsi", "jumlah_tahun_evaluasi",
            "tanggal_mulai", "tanggal_target_selesai", "deadline_upload_dokumen",
            "tanggal_submit", "tanggal_visitasi_mulai", "tanggal_visitasi_selesai",
            "tanggal_sertifikat", "status",
            "nilai_akhir", "nomor_sk_akreditasi", "berlaku_sampai",
        ]
        widgets = {
            "judul": forms.TextInput(attrs={"class": "form-input"}),
            "deskripsi": forms.Textarea(attrs={"class": "form-input", "rows": 3}),
            "jumlah_tahun_evaluasi": forms.Select(
                choices=[(3, "3 Tahun"), (4, "4 Tahun"), (5, "5 Tahun")],
                attrs={"class": "form-input"},
            ),
            "tanggal_mulai": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "tanggal_target_selesai": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "deadline_upload_dokumen": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "tanggal_submit": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "tanggal_visitasi_mulai": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "tanggal_visitasi_selesai": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "tanggal_sertifikat": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "berlaku_sampai": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-input"}),
            "nilai_akhir": forms.TextInput(attrs={"class": "form-input"}),
            "nomor_sk_akreditasi": forms.TextInput(attrs={"class": "form-input"}),
        }