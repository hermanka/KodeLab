# Uji konkurensi setelah penggunaan ulang container dan pengurangan inspeksi

Pengujian 4 November 2026: 30 siswa pada learning path yang sama, worker 50 proses, runner 50 slot, scheduler 1 detik. Laporan lama dipertahankan.

**[Laporan lengkap, waktu antar-container, timeline terburuk, dan data mentah](artifacts/performance/judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md)**

| Waktu request yang diterima sampai hasil terlihat | Run sebelumnya | Run sekarang | Submit sebelumnya | Submit sekarang |
|---|---:|---:|---:|---:|
| Rata-rata | 19,344 dtk | **16,378 dtk** | 28,066 dtk | **23,926 dtk** |
| P95 | 26,352 dtk | **22,258 dtk** | 35,627 dtk | **34,181 dtk** |
| Maksimum | 26,425 dtk | **22,282 dtk** | 35,643 dtk | **35,427 dtk** |

Seluruh 64 pekerjaan benar, tanpa retry eksekusi. Burst Run menerima 30/30; burst Submit menerima 25 dan menolak 5 dengan HTTP 429. Setelah retry terkontrol, seluruh Submit selesai. Maksimum sejak percobaan pertama termasuk 429/retry adalah **44,389 detik** untuk Submit. Pending/running maksimum tetap 20 sesuai kuota kelas.

Pada 64 pekerjaan, create/remove turun dari 256 menjadi 64 operasi masing-masing; inspeksi dari 2.361 menjadi 256. Rata-rata pemrosesan runner Submit turun **24,991 → 16,180 detik**. Namun lock admission API mencapai **24,819 detik**, sehingga target 5–7 detik belum tercapai.

Tidak ditemukan peringatan cleanup pada log pengujian ini. Konfigurasi normal sudah dipulihkan setelah profiler dilepas. Fixture dibersihkan; akun/kelas pengguna sebelumnya tidak dihapus.

Skrip tetap tersedia: [test-judging-profile.ps1](scripts/test-judging-profile.ps1), dengan [panduan](scripts/profiling/README.md). Hasil berasal dari satu burst per skenario pada satu host dan dua perbaikan diuji bersama; belum membuktikan 50 eksekusi aktif atau latensi produksi.
