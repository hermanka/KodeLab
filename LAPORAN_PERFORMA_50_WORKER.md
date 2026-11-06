# Pengujian konkurensi — 50 proses worker / 50 slot runner

Pengujian 4 November 2026 memakai scheduler 1 detik, 30 siswa, satu learning path, serta compiler C17/C++17 nyata. Laporan lama dipertahankan.

**[Laporan lengkap, tahap antar-container, timeline terburuk, dan data mentah](artifacts/performance/judging-profile-20261104-103741-bdae8f/LAPORAN_DETAIL_RUN_SUBMIT.md)**

| Ukuran | Run | Submit |
|---|---:|---:|
| Diterima / 429 pada burst awal | 30 / 0 | 20 / 10 |
| Rata-rata menunggu worker eksekusi | 0,028 dtk | 0,014 dtk |
| Rata-rata pemrosesan runner | 8,024 dtk | 24,991 dtk |
| Rata-rata request yang diterima → hasil terlihat | 19,344 dtk | 28,066 dtk |
| P95 request yang diterima → hasil terlihat | 26,352 dtk | 35,627 dtk |
| Maksimum sejak percobaan pertama, termasuk retry alat uji | 26,425 dtk | 53,900 dtk |

Seluruh 64 pekerjaan benar: 32 Executed dan 32 Accepted, tanpa retry eksekusi. Batas pending kelas tetap 20; concurrency aktual pekerjaan pada sampling mencapai 20, sehingga uji ini belum menguji 50 eksekusi aktif.

Antrean worker berkurang tajam, tetapi hambatan berpindah: lifecycle/inspeksi Docker membengkak dan lock admission API pada burst Run mencapai 19,918 detik. CPU VM Docker mencapai 95,3%. Target hasil terlihat dalam 5–7 detik belum tercapai. Snapshot log mencatat 10 peringatan cleanup NotFound; tidak ada sandbox tersisa setelah pengujian.

Skrip tersimpan dan dapat digunakan kembali:

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Build/aktifkan konfigurasi yang hendak diuji terlebih dahulu. Wrapper membaca command Compose, memverifikasi konfigurasi aktual, mencatat resource VM, dan menghasilkan laporan baru per pengulangan. Lihat [panduan](scripts/profiling/README.md). Konfigurasi normal 50/50/1 tetap aktif setelah instrumentasi dilepas.
