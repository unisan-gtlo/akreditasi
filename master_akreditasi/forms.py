"""Forms untuk Import Excel master."""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Instrumen, ImportLog


class ExcelUploadForm(forms.Form):
    """Form upload file Excel untuk import master."""

    instrumen = forms.ModelChoiceField(
        label=_("Instrumen Target"),
        queryset=Instrumen.objects.filter(aktif=True).order_by("urutan"),
        empty_label="-- Pilih Instrumen --",
        widget=forms.Select(attrs={"class": "form-input"}),
        error_messages={"required": _("Instrumen wajib dipilih.")},
    )

    mode = forms.ChoiceField(
        label=_("Mode Import"),
        choices=ImportLog.Mode.choices,
        initial=ImportLog.Mode.UPDATE,
        widget=forms.RadioSelect,
    )

    file = forms.FileField(
        label=_("File Excel (.xlsx)"),
        widget=forms.FileInput(attrs={
            "class": "form-input",
            "accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }),
        error_messages={"required": _("Silakan pilih file Excel.")},
    )

    MAX_FILE_SIZE_MB = 10

    def clean_file(self):
        f = self.cleaned_data["file"]

        # Size check
        size_mb = f.size / (1024 * 1024)
        if size_mb > self.MAX_FILE_SIZE_MB:
            raise forms.ValidationError(
                _(f"Ukuran file maksimal {self.MAX_FILE_SIZE_MB} MB. File Anda: {size_mb:.1f} MB")
            )

        # Extension check
        name_lower = f.name.lower()
        if not name_lower.endswith(".xlsx"):
            raise forms.ValidationError(
                _("Hanya file Excel .xlsx yang diterima.")
            )

        return f