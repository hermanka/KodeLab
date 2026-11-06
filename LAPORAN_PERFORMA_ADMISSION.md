# Uji konkurensi setelah perbaikan admission API

Pengujian 4 November 2026 memakai 30 siswa pada learning path yang sama, konfigurasi 50 proses worker, 50 slot runner, scheduler 1 detik, dan kuota pending kelas 20. Laporan lama dipertahankan.

**[Laporan lengkap, waktu antar-container, timeline terburuk, dan data mentah](artifacts/performance/judging-profile-20261104-115413-6490f7/LAPORAN_DETAIL_RUN_SUBMIT.md)**

Perubahan: pemeriksaan awal tanpa lock tulis, melepas transaksi/koneksi sebelum health check/persiapan provider, lalu memeriksa ulang izin/status/provider dan kuota saat menyimpan pekerjaan secara atomik. Urutan lock, kuota, dan idempotensi tetap dijaga.

| Ukuran | Run sebelum | Run sesudah | Submit sebelum | Submit sesudah |
|---|---:|---:|---:|---:|
| Rata-rata menunggu lock | 5,213 dtk | **1,518 dtk** | 4,999 dtk | **2,507 dtk** |
| Rata-rata request yang diterima → hasil terlihat | 16,378 dtk | **11,556 dtk** | 23,926 dtk | **23,012 dtk** |
| P95 request yang diterima → hasil terlihat | 22,258 dtk | **16,160 dtk** | 34,181 dtk | **31,424 dtk** |
| Maksimum request yang diterima → hasil terlihat | 22,282 dtk | **16,270 dtk** | 35,427 dtk | **32,247 dtk** |

Seluruh 64 pekerjaan benar, tanpa retry eksekusi. Masing-masing burst awal menerima 23 dan menolak 7 dengan HTTP 429; setelah retry alat uji, seluruh pekerjaan selesai. Pengujian fungsi: **100 unit/API dan 4 MariaDB disposable lulus**.

Target 5–7 detik belum tercapai. Waktu menunggu lock Submit masih mencapai 19,151 detik dan runner rata-rata 17,319 detik. Durasi seluruh fase 30 peserta hampir tetap: Run 22,230 detik dan Submit 44,586 detik; rata-rata sejak percobaan pertama termasuk retry adalah 15,354/30,541 detik. Jadi, perbaikan admission tidak membuat seluruh burst selesai jauh lebih cepat.

Script [test-judging-profile.ps1](scripts/test-judging-profile.ps1) tetap tersimpan dan menghasilkan direktori/laporan baru. Konfigurasi normal tanpa profiler dipulihkan setelah pengujian; fixture dibersihkan. Uji satu soal/satu host dengan maksimum 20 pekerjaan aktif belum membuktikan kapasitas 50 eksekusi aktif.
