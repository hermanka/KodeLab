# Perbandingan 4, 8, 12, dan 16 slot

**Pembaruan:** [pengujian konfirmasi dengan urutan 12 lalu 8](artifacts/performance/slot-sweep-20261104-142709-e053a4/LAPORAN_KONFIRMASI_8_12.md) sudah selesai. Pemenang berbalik menjadi 12 pada putaran tersebut; 8 masih unggul pada statistik gabungan, tetapi belum terbukti selalu optimal. Angka di bawah adalah putaran pertama.

**[Laporan lengkap dan tautan setiap konfigurasi](artifacts/performance/slot-sweep-20261104-122722-9e1850/LAPORAN_PERBANDINGAN_SLOT.md)**

Jumlah proses worker dan slot runner disamakan pada tiap konfigurasi. Seluruhnya memakai 30 pengguna, kode/API yang sama, scheduler 1 detik, dan batas pending kelas 20.

| Slot / worker | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 |
|---:|---:|---:|---:|---:|
| 4 | 18,872 dtk | 30,147 dtk | 35,545 dtk | 61,496 dtk |
| **8** | **13,093 dtk** | **20,818 dtk** | **26,360 dtk** | **43,858 dtk** |
| 12 | 17,261 dtk | 25,574 dtk | 35,981 dtk | 54,257 dtk |
| 16 | 16,714 dtk | 23,287 dtk | 31,120 dtk | 45,182 dtk |

Waktu dihitung sejak percobaan pertama sampai hasil terlihat, termasuk antrean serta penolakan 429/retry alat uji. **8 slot / 8 proses worker adalah kandidat terbaik pada cohort lengkap**, bukan jaminan optimum produksi. Target 5–7 detik belum tercapai.

Empat cohort lengkap menghasilkan 256/256 pekerjaan benar. Percobaan 8 slot pertama tidak lengkap karena satu `ReadError` saat pengiriman HTTP; 63 pekerjaan lainnya selesai benar. Percobaan gagal dipertahankan dan 8 slot diulang dengan fixture baru. Total lima percobaan: 319 pekerjaan selesai benar dari 320 yang direncanakan, tanpa retry eksekusi.

Konfigurasi normal **50 worker / 50 slot** dipulihkan; kandidat belum diterapkan. Skrip tersimpan di [test-slot-sweep.ps1](scripts/test-slot-sweep.ps1) dan mendukung melanjutkan sweep yang terputus. Setiap laporan kapasitas tetap memuat waktu antar-container dan timeline terburuk.

Satu cohort lengkap per kapasitas, urutan pengujian, variasi host, dan pengaruh profiler membatasi kesimpulan; lakukan konfirmasi dengan urutan berbeda sebelum menetapkan kapasitas produksi.
