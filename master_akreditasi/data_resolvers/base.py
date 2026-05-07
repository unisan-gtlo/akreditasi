"""Abstract base class untuk Data Resolver pattern.

Resolver = strategy untuk mengambil & merender data dosen dari SIMDA
sesuai dengan ButirDataDosenMapping.jenis_data.

Kontrak:
- Setiap resolver punya identitas (jenis_data) yang match dengan
  ButirDataDosenMapping.JENIS_DATA_CHOICES.
- Setiap resolver tahu cara:
  1. Compute summary per dosen (count, total/agregat) untuk tabel modal utama
  2. Fetch detail records per dosen untuk drill-down expand
  3. Tahu nama template partial yang harus dirender (modal body & detail row)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DosenSummary:
    """Hasil ringkasan data per dosen DTPS untuk tabel utama modal.

    Attributes:
        count: Jumlah records (mis. jumlah BKD periode, jumlah jenjang ijazah).
        agg_label: Label agregat untuk header kolom (mis. "Total SKS", "Jenjang Tertinggi").
        agg_value: Nilai agregat untuk ditampilkan (mis. 28.00, "S2").
        agg_value_formatted: Versi terformat untuk display (mis. "28.00", "S2 - Magister").
        extra: Data tambahan optional (untuk template-specific rendering).
    """
    count: int = 0
    agg_label: str = ""
    agg_value: Any = None
    agg_value_formatted: str = ""
    extra: dict = field(default_factory=dict)


class BaseDataResolver(ABC):
    """Abstract base untuk resolver per jenis_data SIMDA.

    Subclass HARUS:
    - Set class attribute `jenis_data` (string yang match JENIS_DATA_CHOICES)
    - Implementasi `get_dosen_summary()` dan `get_detail_records()`
    - Set class attribute `modal_template` dan `detail_template`

    Subclass BISA override:
    - `column_headers` untuk customize header tabel modal utama
    - `agg_column_label` untuk label kolom agregat
    """

    # Identitas resolver — match dengan ButirDataDosenMapping.JENIS_DATA_CHOICES
    jenis_data: str = ""

    # Templates yang akan dirender
    modal_template: str = ""        # untuk modal utama (tabel DTPS)
    detail_template: str = ""       # untuk drill-down expand row

    # Label-label tampilan
    title_prefix: str = "Data Dosen DTPS"
    agg_column_label: str = "Total"

    # ===== ABSTRACT METHODS =====

    @abstractmethod
    def get_dosen_summary(self, sesi, dtps, mapping):
        """Compute ringkasan data per 1 dosen DTPS.

        Args:
            sesi: SesiAkreditasi instance
            dtps: DTPSDosenSesi instance
            mapping: ButirDataDosenMapping instance (untuk filter_periode dll)

        Returns:
            DosenSummary instance.
        """
        raise NotImplementedError

    @abstractmethod
    def get_detail_records(self, sesi, dtps, mapping):
        """Fetch records lengkap untuk drill-down per dosen.

        Args:
            sesi, dtps, mapping: sama dengan get_dosen_summary

        Returns:
            QuerySet atau list of records yang akan dirender di template detail.
            Format spesifik untuk template (template tahu cara baca).
        """
        raise NotImplementedError

    # ===== HOOKS (optional override) =====

    def get_extra_context(self, sesi, butir, mapping):
        """Hook untuk inject extra context ke template modal.

        Default: empty dict. Subclass bisa override kalau butuh data tambahan.
        """
        return {}

    def __repr__(self):
        return f"<{self.__class__.__name__} jenis_data={self.jenis_data!r}>"