# Perbandingan slot eksekusi — 30 pengguna

Jumlah proses worker eksekusi dan slot runner diubah bersama, dengan nilai yang sama. Ini pengujian kapasitas paralel keseluruhan, bukan isolasi pengaruh semaphore runner saja. Source Compose dan kode aplikasi tidak diubah oleh sweep; konfigurasi normal dipulihkan setelah setiap skenario.

Setiap konfigurasi: 30 akun/kelas baru, satu learning path dan soal penjumlahan, 15 C17/15 C++17, 5 test case, 4 baseline API, 30 Run dan 30 Submit. Ada 8 kontrol RPC tanpa profiler dan 8 dengan profiler. Scheduler tetap 1 detik; dispatcher tetap berbagi worker dengan eksekusi. Batas pending kelas tetap 20.

Pengiriman burst HTTP serentak mewakili klik; waktu render browser tidak diukur. Poll hasil setiap 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; ini bukan retry otomatis UI. Waktu sejak percobaan pertama memasukkan penolakan dan jeda retry tersebut.

## Waktu sejak percobaan pertama sampai hasil terlihat

Semua angka detik. Ini ukuran utama pengalaman 30 peserta, termasuk antrean dan retry admission.

| Slot / proses worker | Run rata-rata | Run P95 | Run maksimum | Submit rata-rata | Submit P95 | Submit maksimum |
|---:|---:|---:|---:|---:|---:|---:|
| 12 | 15.259 | 22.937 | 22.969 | 26.929 | 42.178 | 42.205 |
| 8 | 16.219 | 24.534 | 24.551 | 27.989 | 46.195 | 46.195 |

## Waktu setelah request yang diterima dan di dalam runner

Kolom request dimulai dari pengiriman HTTP yang akhirnya diterima, mencakup waktu penerimaan API. Kolom runner hanya bagian eksekusi sehingga tidak boleh dipakai sendiri untuk menilai waktu pengguna.

| Slot | Run request rata-rata / P95 | Run runner rata-rata | Submit request rata-rata / P95 | Submit runner rata-rata |
|---:|---:|---:|---:|---:|
| 12 | 12.264 / 17.859 | 4.507 | 18.724 / 27.202 | 11.797 |
| 8 | 12.914 / 19.780 | 3.999 | 18.036 / 29.816 | 8.996 |

## Antrean, admission, dan kapasitas yang teramati

| Slot | Run outbox / antre worker | Submit outbox / antre worker | Run / Submit lock admission rata-rata | Puncak running |
|---:|---:|---:|---:|---:|
| 12 | 1.390 / 1.107 | 1.239 / 2.267 | 1.906 / 1.081 | 12 |
| 8 | 2.480 / 1.616 | 3.156 / 3.148 | 2.071 / 0.696 | 8 |

| Slot | Run awal diterima / 429 | Submit awal diterima / 429 | Durasi fase Run / Submit | Retry eksekusi |
|---:|---:|---:|---:|---:|
| 12 | 25 / 5 | 21 / 9 | 22.978 / 42.230 | 0 |
| 8 | 25 / 5 | 20 / 10 | 24.594 / 46.234 | 0 |

## Sumber daya dan variasi kontrol

CPU adalah penggunaan VM Docker keseluruhan, bukan satu sandbox. Kontrol Submit C++17 tanpa profiler adalah RPC tunggal pada konfigurasi normal, sebelum kapasitas kandidat diaktifkan; perubahan kontrol tersebut menunjukkan variasi host yang tidak boleh seluruhnya dikaitkan dengan jumlah slot.

| Slot | CPU Run rata-rata / maksimum | CPU Submit rata-rata / maksimum | RAM available minimum Submit | Kontrol Submit C++17 tanpa profiler |
|---:|---:|---:|---:|---:|
| 12 | 61.4% / 89.2% | 69.4% / 87.3% | 12.46 GiB | 4.461 dtk |
| 8 | 56.9% / 79.2% | 60.1% / 81.4% | 12.76 GiB | 3.715 dtk |

## Kandidat konfigurasi

Di antara konfigurasi baru yang diuji, **12 slot / 12 proses worker** memiliki jumlah P95 Run dan Submit sejak percobaan pertama paling rendah (65.115 detik). Kriteria ini memberi bobot sama pada kedua aksi. Ini kandidat untuk pengujian lanjutan, bukan bukti optimum produksi.

Jumlah slot lebih sedikit dapat mempercepat pekerjaan yang sedang berjalan sambil menambah antrean. Baca kedua tabel waktu bersama; jumlah worker rendah juga dapat menunda dispatcher yang berbagi antrean. Kandidat belum diterapkan sebagai konfigurasi normal.

## Kebenaran hasil dan keterbatasan

Seluruh 128 pekerjaan API pada konfigurasi baru tervalidasi dengan verdict yang diharapkan; setiap konfigurasi lengkap 64/64 trace dan seluruh peserta mencapai progres/nilai 100. Kelas fixture dihapus, masing-masing 30 akun dinonaktifkan. Delivery Celery bisa lebih banyak daripada eksekusi jika pesan duplikat dijadwalkan; lihat data setiap konfigurasi.

Setiap kapasitas memakai satu cohort lengkap untuk peringkat. Percobaan ulang, bila ada, dicatat pada manifest dan bagian percobaan yang tidak masuk peringkat. Belum mengendalikan efek urutan, variasi host, cache, atau beban berkelanjutan. Rekomendasi yang berdekatan perlu diuji ulang dalam urutan berbeda. Data memakai profiler; kontrol pengaruh profiler dan sumber daya VM tersedia pada laporan setiap konfigurasi.

## Laporan per konfigurasi dan pengulangan

- [12 slot / worker](../slot-sweep-20261104-142709-e053a4-slots-12/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `perf_90d3cea9ab`, delivery worker 64, cleanup `{'class_deleted': True, 'test_accounts_disabled': 30}`.
- [8 slot / worker](../slot-sweep-20261104-142709-e053a4-slots-8/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `perf_79f2e38513`, delivery worker 64, cleanup `{'class_deleted': True, 'test_accounts_disabled': 30}`.

Pembanding 50 slot terdahulu dengan API admission yang sama: [laporan](../judging-profile-20261104-115413-6490f7/LAPORAN_DETAIL_RUN_SUBMIT.md). Run pertama → hasil rata-rata 15,354 detik/P95 21,887 detik; Submit 30,541 detik/P95 44,194 detik. Pengukuran 50 slot itu dilakukan pada waktu berbeda dan bukan bagian urutan sweep ini.

```powershell
./scripts/test-slot-sweep.ps1
# Satu konfigurasi saja:
./scripts/test-judging-profile.ps1 -Slots 8
```

[Data perbandingan](comparison.json) dan [manifest urutan/status](manifest.json). Laporan per konfigurasi berisi timeline terburuk dan waktu antar-container; laporan lama tidak ditimpa.
