# Pengujian performa 30 pengguna

Pengujian ulang dengan rincian waktu setiap tahap sudah tersedia: **[Laporan detail Run dan Submit](artifacts/performance/judging-profile-20261104-093052-80dbc2/LAPORAN_DETAIL_RUN_SUBMIT.md)**. Seluruh 64 pekerjaan benar. Pada burst Submit, rata-rata antrean sebelum worker bekerja 23,634 detik, runner 6,012 detik, dan request sampai hasil tersimpan 31,040 detik. Dispatcher sempat menunggu 34,588 detik. Laporan berikut merupakan pengujian awal yang tetap dipertahankan sebagai riwayat.

Pengujian dilakukan 4 November 2026 pada deployment Docker lokal, dengan 30 akun siswa dan satu learning path yang sama. Kode aplikasi dan kuota tidak diubah.

Laporan lengkap, metode, persentil, analisis anomali, batas kesimpulan, dan data mentah tersedia di:

**[Laporan performa 30 pengguna](artifacts/performance/concurrent-30-20261104-084606-a2c74c/LAPORAN_PERFORMA_30_USER.md)**

| Skenario | Diterima pada burst awal | Ditolak HTTP 429 | Selesai setelah retry terkontrol | Durasi seluruh fase |
|---|---:|---:|---:|---:|
| 30 run serentak | 20 | 10 | 30 | 36,333 detik |
| 30 submit benar serentak | 20 | 10 | 30 | 85,402 detik |
| 60 run/submit campuran dari 30 pengguna | 22 | 38 | 60 | 129,328 detik |

Seluruh 120 pekerjaan selesai dengan hasil yang diharapkan: 60 Executed, 50 Accepted, dan 10 Wrong Answer yang sengaja dipakai sebagai kontrol. Tidak ditemukan salah nilai/output, system_error, atau retry eksekusi. Terdapat satu RemoteProtocolError saat polling hasil dan dua peringatan cleanup NotFound pada runner.

Hambatan utama adalah batas 20 pending per kelas dan dua proses worker kiriman. Waktu antre maksimum 53 detik. Keberhasilan seluruh pekerjaan melibatkan retry oleh alat uji; UI saat ini tidak otomatis mengantre ulang permintaan yang ditolak 429.

Kelas uji sudah dihapus. Sebanyak 30 akun uji dinonaktifkan dan dipertahankan bersama audit untuk keterlacakan. Akun/kelas yang sudah ada tidak dihapus.

Pengulangan menggunakan PowerShell 7, Docker aktif, dan kredensial bootstrap yang sudah ada di `.env`:

```powershell
./scripts/test-concurrent-users.ps1 -SelfCheck
./scripts/test-concurrent-users.ps1
```

Setiap pengulangan membuat akun/kelas uji baru dan menghasilkan direktori hasil baru. Benchmark memakai HTTP nyata dan compiler C/C++ nyata, bukan 30 browser yang merender UI; hasil ini belum merupakan jaminan kapasitas produksi atau beban berkelanjutan.
