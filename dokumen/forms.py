"""Forms untuk modul Dokumen."""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Dokumen, DokumenRevisi
from .gdrive_helper import validate_gdrive_url


class DokumenUploadForm(forms.Form):
    """Form upload dokumen baru atau revisi — hybrid (local upload OR gdrive link)."""

    STORAGE_CHOICES = [
        ("LOCAL", _("Upload File Lokal")),
        ("GDRIVE", _("Google Drive Link")),
    ]

    # Pilih tipe storage
    storage_type = forms.ChoiceField(
        label=_("Metode Upload"),
        choices=STORAGE_CHOICES,
        initial="LOCAL",
        widget=forms.RadioSelect,
    )

    # Local upload
    file = forms.FileField(
        label=_("File Dokumen"),
        required=False,
        widget=forms.FileInput(attrs={"class": "form-input"}),
    )

    # GDrive link
    gdrive_url = forms.URLField(
        label=_("Google Drive URL"),
        required=False,
        max_length=500,
        widget=forms.URLInput(attrs={
            "class": "form-input",
            "placeholder": "https://drive.google.com/file/d/XXXXXXXXX/view",
        }),
    )

    # Common metadata
    judul = forms.CharField(
        label=_("Judul Dokumen"),
        max_length=300,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Contoh: SK Rektor tentang VMTS 2024",
        }),
        error_messages={"required": _("Judul wajib diisi.")},
    )

    tahun_akademik = forms.CharField(
        label=_("Tahun Akademik"),
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Contoh: 2024/2025",
        }),
    )

    status_akses = forms.ChoiceField(
        label=_("Status Akses"),
        choices=Dokumen.StatusAkses.choices,
        widget=forms.RadioSelect,
    )

    deskripsi = forms.CharField(
        label=_("Deskripsi / Catatan"),
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-input",
            "rows": 3,
            "placeholder": "Catatan tambahan tentang dokumen ini (opsional)",
        }),
    )

    catatan_revisi = forms.CharField(
        label=_("Catatan Revisi"),
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-input",
            "rows": 2,
            "placeholder": "Kalau ini revisi, tulis apa yang diperbarui (opsional)",
        }),
    )

    def __init__(self, *args, butir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.butir = butir

        # Pre-fill dari butir
        if butir and not self.is_bound:
            self.fields["judul"].initial = butir.nama_dokumen
            self.fields["status_akses"].initial = butir.status_akses_default

    def clean_file(self):
        """Validasi file upload (kalau dipilih)."""
        f = self.cleaned_data.get("file")
        storage = self.data.get("storage_type", "LOCAL")

        if storage != "LOCAL":
            return None  # skip, kita pakai gdrive

        if not f:
            raise forms.ValidationError(_("File wajib dipilih untuk upload lokal."))

        if not self.butir:
            return f

        # Size check
        max_mb = self.butir.ukuran_max_mb
        size_mb = f.size / (1024 * 1024)
        if size_mb > max_mb:
            raise forms.ValidationError(
                _(f"Ukuran file melebihi batas ({max_mb} MB). File Anda: {size_mb:.1f} MB. "
                  f"Pertimbangkan pakai Google Drive link untuk file besar.")
            )

        # Extension check
        filename_lower = f.name.lower()
        format_ext_map = {
            "PDF": [".pdf"],
            "DOCX": [".docx", ".doc"],
            "XLSX": [".xlsx", ".xls"],
            "PPTX": [".pptx", ".ppt"],
            "GAMBAR": [".jpg", ".jpeg", ".png", ".webp", ".gif"],
            "APAPUN": None,
        }
        expected_formats = format_ext_map.get(self.butir.format_diterima)
        if expected_formats is not None:
            if not any(filename_lower.endswith(ext) for ext in expected_formats):
                raise forms.ValidationError(
                    _(f"Format file tidak sesuai. Butir ini hanya menerima: "
                      f"{', '.join(expected_formats)}")
                )

        return f

    def clean_gdrive_url(self):
        """Validasi URL Google Drive (kalau dipilih)."""
        url = self.cleaned_data.get("gdrive_url", "").strip()
        storage = self.data.get("storage_type", "LOCAL")

        if storage != "GDRIVE":
            return ""  # skip

        if not url:
            raise forms.ValidationError(_("URL Google Drive wajib diisi."))

        # Validasi format & extract file_id
        result = validate_gdrive_url(url)
        if not result["is_valid"]:
            raise forms.ValidationError(result["error"])

        # Store file_id di cleaned_data
        self.cleaned_data["_gdrive_file_id"] = result["file_id"]
        self.cleaned_data["_gdrive_accessible"] = result.get("accessible", False)
        self.cleaned_data["_gdrive_warning"] = result.get("warning", "")

        return url

    def clean(self):
        """Validasi cross-field."""
        cleaned = super().clean()
        storage = cleaned.get("storage_type", "LOCAL")

        if storage == "LOCAL" and not cleaned.get("file"):
            if "file" not in self._errors:
                self.add_error("file", _("File wajib dipilih untuk upload lokal."))

        if storage == "GDRIVE" and not cleaned.get("gdrive_url"):
            if "gdrive_url" not in self._errors:
                self.add_error("gdrive_url", _("URL Google Drive wajib diisi."))

        return cleaned

class RevisiUploadForm(forms.Form):
    """
    Form upload revisi baru untuk dokumen existing.
    Mirip DokumenUploadForm tapi TIDAK include field metadata utama
    (judul/tahun/akses tetap dari dokumen existing).
    """

    STORAGE_CHOICES = [
        ("LOCAL", _("Upload File Lokal")),
        ("GDRIVE", _("Google Drive Link")),
    ]

    storage_type = forms.ChoiceField(
        label=_("Metode Upload"),
        choices=STORAGE_CHOICES,
        initial="LOCAL",
        widget=forms.RadioSelect,
    )

    file = forms.FileField(
        label=_("File Dokumen Baru"),
        required=False,
        widget=forms.FileInput(attrs={"class": "form-input"}),
    )

    gdrive_url = forms.URLField(
        label=_("Google Drive URL Baru"),
        required=False,
        max_length=500,
        widget=forms.URLInput(attrs={
            "class": "form-input",
            "placeholder": "https://drive.google.com/file/d/XXXXXXXXX/view",
        }),
    )

    catatan_revisi = forms.CharField(
        label=_("Catatan Revisi"),
        required=True,
        widget=forms.Textarea(attrs={
            "class": "form-input",
            "rows": 3,
            "placeholder": "Wajib: jelaskan perubahan apa yang dilakukan di revisi ini",
        }),
        error_messages={"required": _("Catatan revisi wajib diisi untuk audit trail.")},
    )

    def __init__(self, *args, butir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.butir = butir

    def clean_file(self):
        f = self.cleaned_data.get("file")
        storage = self.data.get("storage_type", "LOCAL")

        if storage != "LOCAL":
            return None

        if not f:
            raise forms.ValidationError(_("File wajib dipilih untuk upload lokal."))

        if not self.butir:
            return f

        # Size check
        max_mb = self.butir.ukuran_max_mb
        size_mb = f.size / (1024 * 1024)
        if size_mb > max_mb:
            raise forms.ValidationError(
                _(f"Ukuran file melebihi batas ({max_mb} MB). File Anda: {size_mb:.1f} MB. "
                  f"Pertimbangkan pakai Google Drive link untuk file besar.")
            )

        # Extension check
        filename_lower = f.name.lower()
        format_ext_map = {
            "PDF": [".pdf"],
            "DOCX": [".docx", ".doc"],
            "XLSX": [".xlsx", ".xls"],
            "PPTX": [".pptx", ".ppt"],
            "GAMBAR": [".jpg", ".jpeg", ".png", ".webp", ".gif"],
            "APAPUN": None,
        }
        expected_formats = format_ext_map.get(self.butir.format_diterima)
        if expected_formats is not None:
            if not any(filename_lower.endswith(ext) for ext in expected_formats):
                raise forms.ValidationError(
                    _(f"Format file tidak sesuai. Butir ini hanya menerima: "
                      f"{', '.join(expected_formats)}")
                )
        return f

    def clean_gdrive_url(self):
        url = self.cleaned_data.get("gdrive_url", "").strip()
        storage = self.data.get("storage_type", "LOCAL")

        if storage != "GDRIVE":
            return ""

        if not url:
            raise forms.ValidationError(_("URL Google Drive wajib diisi."))

        result = validate_gdrive_url(url)
        if not result["is_valid"]:
            raise forms.ValidationError(result["error"])

        self.cleaned_data["_gdrive_file_id"] = result["file_id"]
        self.cleaned_data["_gdrive_accessible"] = result.get("accessible", False)
        return url

    def clean(self):
        cleaned = super().clean()
        storage = cleaned.get("storage_type", "LOCAL")

        if storage == "LOCAL" and not cleaned.get("file"):
            if "file" not in self._errors:
                self.add_error("file", _("File wajib dipilih untuk upload lokal."))

        if storage == "GDRIVE" and not cleaned.get("gdrive_url"):
            if "gdrive_url" not in self._errors:
                self.add_error("gdrive_url", _("URL Google Drive wajib diisi."))

        return cleaned


class DokumenEditForm(forms.ModelForm):
    """Form edit metadata dokumen (TANPA file/storage/scope)."""

    class Meta:
        model = Dokumen
        fields = ["judul", "deskripsi", "tahun_akademik", "status_akses", "status"]
        widgets = {
            "judul": forms.TextInput(attrs={"class": "form-input"}),
            "deskripsi": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 4,
                "placeholder": "Deskripsi atau catatan tentang dokumen ini",
            }),
            "tahun_akademik": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Contoh: 2024/2025",
            }),
            "status_akses": forms.RadioSelect,
            "status": forms.RadioSelect,
        }
        labels = {
            "judul": _("Judul Dokumen"),
            "deskripsi": _("Deskripsi / Catatan"),
            "tahun_akademik": _("Tahun Akademik"),
            "status_akses": _("Status Akses"),
            "status": _("Status Dokumen"),
        }