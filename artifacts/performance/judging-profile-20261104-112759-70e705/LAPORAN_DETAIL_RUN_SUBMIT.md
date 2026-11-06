# Profil waktu Run dan Submit — konfigurasi 50 worker / 50 slot runner

**Setelah penggunaan ulang container per Run/Submit dan pengurangan inspeksi Docker.** Rata-rata waktu sampai hasil terlihat turun dari 19,344 menjadi **16,378 detik untuk Run** dan dari 28,066 menjadi **23,926 detik untuk Submit**. Seluruh 64 pekerjaan benar, tetapi target 5–7 detik belum tercapai. Maksimum Submit yang sudah diterima masih 35,427 detik; termasuk penolakan 429 dan jeda retry alat uji, maksimum menjadi 44,389 detik.

Pengujian baru: `perf_25d404856f`. Mulai UTC: 2026-11-04T04:29:46.989648+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(50, 50)] (concurrency, jumlah proses). Runner: **50 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_25d404856f`. Nama kelas: `Performance 30 users perf_25d404856f`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.343 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.257 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.189 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.309 dtk | 0 |
| run_30 | {'202': 30} | {'EXECUTED': 30} | 22.319 dtk | 0 |
| submit_30 | {'202': 25, '429': 5} | {'ACCEPTED': 30} | 44.419 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 7, 'running': 20, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 7949 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 5}`.

Catatan timestamp: `[]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.273 | 0.355 | 0.321 | 0.482 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 5.800 | 16.218 | 5.519 | 24.874 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.386 | 0.858 | 0.475 | 0.914 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 0.037 | 0.096 | 0.039 | 0.090 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.018 | 0.037 | 0.022 | 0.075 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 0.021 | 0.074 | 0.026 | 0.066 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.107 | 0.553 | 0.063 | 0.217 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 7.207 | 10.709 | 16.396 | 23.091 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 1.573 | 3.855 | 0.099 | 0.241 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.955 | 1.986 | 0.968 | 2.354 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 15.423 | 21.350 | 22.958 | 33.762 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 16.378 | 22.258 | 23.926 | 34.181 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 0.441 | 0.893 | 0.535 | 0.954 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 6.825 | 10.392 | 16.180 | 22.892 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Jumlah operasi Docker pada 64 pekerjaan API (tidak termasuk kontrol runner dan validasi solusi acuan saat setup):

| Operasi | Sebelumnya: per fase + polling | Sekarang: satu container + wait |
|---|---:|---:|
| Create container fisik | 256 | **64** |
| Remove container fisik | 256 | **64** |
| Start proses container | 256 | **256** |
| Inspeksi status | 2.361 | **256** |
| Wait selesai | 256 | **256** |

Pada seluruh pekerjaan baru, ID container konsisten dari kompilasi hingga input terakhir. Run mempunyai 2 fase dan Submit 6 fase, tetapi keduanya hanya membuat/menghapus satu container. Inspeksi tepat satu per fase normal. Jumlah start masih sama karena proses dimulai ulang antar-input untuk menjaga isolasi file/proses.

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.452660 | 0.386910 | `runner` → Docker Engine: membuat sandbox. |
| Start | 2.044310 | 5.475396 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.148615 | 0.117298 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 2.645584 | 5.979604 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.124620 | 0.391756 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.241261 | 0.818862 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.153131 | 0.509310 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 3.337136 | 7.321297 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.251203 | 0.722341 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.070235 | 0.429095 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 6.824920 | 16.180499 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 1.183304 | 1.134677 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.818122 | 0.767778 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 1.506821 | 7.297231 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000050 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 27, cpp17, attempt `cef44ae7-2d7e-44e0-bc4a-a1b1a848e321`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 22.282 detik; sejak percobaan pertama: 22.282 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.353 | 0.353 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.353–16.572 | 16.218 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 16.572–16.838 | 0.267 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 16.838–16.902 | 0.064 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 16.902–16.911 | 0.008 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 16.911–16.939 | 0.028 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 16.939–17.019 | 0.081 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 17.019–21.295 | 4.275 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 21.295–21.878 | 0.583 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 21.878–22.282 | 0.404 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=16.598 detik. Runner internal memerlukan 3.992 detik, termasuk lifecycle 1.352 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 17.606–20.417 | 2.811 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: c046333c5f2e9d10610a5f00ad4e9509a1e8fd50fe5e28fade92612e18ffdad0. |
| 20.418–21.231 | 0.814 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: c046333c5f2e9d10610a5f00ad4e9509a1e8fd50fe5e28fade92612e18ffdad0. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 7, cpp17, attempt `8e5d8c9c-11e1-4740-95cf-93ec563e41b4`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 35.427 detik; sejak percobaan pertama: 35.427 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–2.318 | 2.318 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 2.318–26.897 | 24.579 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 26.897–27.608 | 0.712 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 27.608–27.624 | 0.016 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 27.624–27.637 | 0.012 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 27.637–27.643 | 0.006 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 27.643–27.665 | 0.023 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 27.665–34.414 | 6.748 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 34.414–34.439 | 0.026 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 34.439–35.427 | 0.988 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=26.942 detik. Runner internal memerlukan 6.635 detik, termasuk lifecycle 2.014 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 27.872–30.103 | 2.231 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: a3c6035a7bc110c26d4d5d65402f95d758309a6c9806a248d4ae934e609dad59. |
| 30.103–31.089 | 0.986 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: a3c6035a7bc110c26d4d5d65402f95d758309a6c9806a248d4ae934e609dad59. |
| 31.089–31.923 | 0.834 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: a3c6035a7bc110c26d4d5d65402f95d758309a6c9806a248d4ae934e609dad59. |
| 31.923–33.006 | 1.082 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: a3c6035a7bc110c26d4d5d65402f95d758309a6c9806a248d4ae934e609dad59. |
| 33.006–33.790 | 0.784 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: a3c6035a7bc110c26d4d5d65402f95d758309a6c9806a248d4ae934e609dad59. |
| 33.790–34.374 | 0.584 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: a3c6035a7bc110c26d4d5d65402f95d758309a6c9806a248d4ae934e609dad59. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 18, c17, attempt `ed539030-7fc3-4198-9fb8-5c45ced4bd32`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 8.975 detik; sejak percobaan pertama: 44.389 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–22.541 | 22.541 | HTTP 429 pada `api`/`db`. |
| 22.541–35.414 | 12.873 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 35.414–35.464 | 0.050 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 35.464–35.867 | 0.403 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 35.867–36.591 | 0.724 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 36.591–36.616 | 0.025 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 36.616–36.624 | 0.009 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 36.624–36.630 | 0.005 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 36.630–36.647 | 0.018 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 36.647–43.365 | 6.718 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 43.365–43.404 | 0.039 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 43.404–44.389 | 0.984 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=35.900 detik. Runner internal memerlukan 6.646 detik, termasuk lifecycle 2.262 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 36.931–38.206 | 1.274 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 546182c572d415f92ce967df2c5497917bcc6e1b589dfb7074e0c6c7c9b0c746. |
| 38.206–39.167 | 0.961 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 546182c572d415f92ce967df2c5497917bcc6e1b589dfb7074e0c6c7c9b0c746. |
| 39.167–40.172 | 1.006 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 546182c572d415f92ce967df2c5497917bcc6e1b589dfb7074e0c6c7c9b0c746. |
| 40.172–41.330 | 1.158 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 546182c572d415f92ce967df2c5497917bcc6e1b589dfb7074e0c6c7c9b0c746. |
| 41.330–42.336 | 1.006 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 546182c572d415f92ce967df2c5497917bcc6e1b589dfb7074e0c6c7c9b0c746. |
| 42.336–43.299 | 0.963 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 546182c572d415f92ce967df2c5497917bcc6e1b589dfb7074e0c6c7c9b0c746. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-103741-bdae8f](../judging-profile-20261104-103741-bdae8f/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.442 | 0.441 | 0.490 | 0.535 |
| Dispatcher menunggu worker | 0.038 | 0.037 | 0.020 | 0.039 |
| Pekerjaan menunggu worker | 0.028 | 0.021 | 0.014 | 0.026 |
| Lock admission API | 6.856 | 5.213 | 0.832 | 4.999 |
| Create container | 1.233 | 0.453 | 4.177 | 0.387 |
| Start proses container | 2.246 | 2.044 | 7.979 | 5.475 |
| Remove container | 0.355 | 0.149 | 1.301 | 0.117 |
| Inspeksi Docker | 2.722 | 0.153 | 7.203 | 0.509 |
| Total runner | 8.024 | 6.825 | 24.991 | 16.180 |
| Request → hasil tersimpan | 18.457 | 15.423 | 27.277 | 22.958 |
| Request → hasil terlihat | 19.344 | 16.377 | 28.066 | 23.926 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.444 | 1.416 | -2.0% |
| c17_judge | 3.751 | 3.818 | +1.8% |
| cpp17_run | 1.730 | 1.753 | +1.3% |
| cpp17_judge | 4.030 | 3.865 | -4.1% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 4 sampel; CPU rata-rata 18.9%, maksimum 34.1%; memori available minimum 11.50 GiB.

- single_c17_judge: 5 sampel; CPU rata-rata 14.0%, maksimum 19.2%; memori available minimum 11.48 GiB.

- single_cpp17_run: 3 sampel; CPU rata-rata 12.4%, maksimum 18.3%; memori available minimum 11.50 GiB.

- single_cpp17_judge: 5 sampel; CPU rata-rata 18.6%, maksimum 22.0%; memori available minimum 11.48 GiB.

- run_30: 22 sampel; CPU rata-rata 76.7%, maksimum 96.2%; memori available minimum 11.06 GiB.

- submit_30: 44 sampel; CPU rata-rata 66.2%, maksimum 93.1%; memori available minimum 10.91 GiB.

## Analisis hambatan

1. **Dua perbaikan bekerja sesuai rancangan.** Create/remove turun 75% secara agregat pada 64 pekerjaan, dan jumlah inspeksi turun sekitar 89,2%. Pada Submit, rata-rata biaya create+start+remove turun 13,458 → 5,980 detik; inspeksi turun 7,203 → 0,509 detik. Total runner turun 24,991 → 16,180 detik, sekitar 35,3%. Ini pengukuran gabungan kedua perubahan, bukan eksperimen yang memisahkan pengaruh masing-masing secara tersendiri.
2. **Perbaikan waktu yang terlihat pengguna lebih kecil daripada perbaikan runner.** Rata-rata Run membaik sekitar 15,3% dan Submit 14,7%. P95 Run 26,352 → 22,258 detik dan Submit 35,627 → 34,181 detik. Maksimum Submit yang diterima hampir tetap: 35,643 → 35,427 detik. Jadi, percepatan runner belum menyelesaikan penantian terburuk pengguna.
3. **Lock admission menjadi hambatan penting.** Pada Submit, rata-rata lock justru naik 0,832 → 4,999 detik dan maksimum mencapai 24,819 detik. API sampai commit maksimum 26,055 detik. Pada pekerjaan Submit terlama yang diterima, 24,579 detik berada pada handler API sebelum commit, sedangkan HTTP runner hanya 6,748 detik. Lock ini global pada `QuotaLock(id="admission")`; health check provider dan pemeriksaan lain masih dijalankan selama transaksi tersebut. Health check Submit rata-rata 0,234 detik, maksimum 1,062 detik. Data ini belum memisahkan seluruh kontribusi kontensi database, penjadwalan host, dan SQL tiap pemeriksaan.
4. **Penolakan kuota juga bisa terasa lambat.** Lima respons 429 masing-masing membutuhkan sekitar 11,336; 13,747; 15,666; 19,813; dan 22,541 detik. Artinya sebagian pengguna sudah menunggu lama sebelum mengetahui permintaan ditolak. Jeda retry berikutnya berasal dari kebijakan alat uji, bukan antrean sandbox untuk pekerjaan yang telah diterima. Burst awal Submit kini menerima 25, dibanding 20 pada uji sebelumnya; pekerjaan yang selesai saat admission berlangsung membebaskan kuota. Batas pending tetap 20.
5. **Start proses dan waktu menunggu proses masih berarti.** Start untuk enam fase Submit memakan rata-rata 5,475 detik. Wait 7,321 detik mencakup compiler/program, bootstrap, serta pengiriman input; ini bukan 7,321 detik overhead murni. Kompilasi nyata rata-rata 1,135 detik dan CPU compiler 0,768 detik. Lifetime PID1 program juga tidak sama dengan CPU algoritma siswa.
6. **Respons polling/progres masih ikut terpengaruh.** Poll hasil median 1,093 detik, P95 3,233 detik, maksimum 4,446 detik; seluruhnya HTTP 200. Probe `/my/learning` median 0,060 detik, P95 3,603 detik, maksimum 4,281 detik. Tambahan dari hasil tersimpan sampai terlihat rata-rata 0,955 detik pada Run dan 0,968 detik pada Submit, termasuk jeda polling dan pemrosesan API.

Prioritas berikut yang didukung hasil ini adalah memperpendek transaksi admission dengan tetap menjaga ketepatan kuota/idempotensi, kemudian mengkalibrasi concurrency dan biaya start proses. Antrean dispatcher/worker saat ini puluhan milidetik sehingga bukan penyebab utama penantian puluhan detik. Tidak ada perubahan optimasi aplikasi tambahan diterapkan selama benchmark ini.

Perbandingan tetap terbatas: satu pengulangan pada satu host, dua perubahan diterapkan bersamaan, dan jumlah penerimaan/retry awal berbeda. Selisih waktu bukan jaminan kapasitas produksi atau bukti bahwa seluruh penghematan disebabkan satu perubahan tertentu.

- run_30: antre worker rata-rata 0.021 detik; runner 6.825 detik; lock admission rata-rata 5.213 detik, maksimum 16.066 detik. Lifecycle create/start/remove 2.646 detik berada di dalam runner.
- submit_30: antre worker rata-rata 0.026 detik; runner 16.180 detik; lock admission rata-rata 4.999 detik, maksimum 24.819 detik. Lifecycle create/start/remove 5.980 detik berada di dalam runner.

Angka tersebut perlu dibaca bersama kontrol tanpa profiler, sumber daya VM, dan batas admission. Concurrency lebih besar dapat mengurangi antrean sekaligus memperlambat setiap pekerjaan. Tidak ada optimasi lanjutan yang otomatis diterapkan oleh alat uji.

## Anomali, validasi, dan batas kesimpulan

- Seluruh 32 Run menghasilkan Executed dan 32 Submit menghasilkan Accepted, tanpa salah output/nilai, retry eksekusi, atau system_error yang ditemukan harness. Seluruh 30 peserta mencapai progres dan nilai 100. Hasil test privat tetap disembunyikan.
- Lima error span HTTPException adalah penolakan admission 429 yang sesuai kuota. Tidak ada error span eksekusi, interval negatif, atau catatan koreksi batas commit pada analisis ini; 64/64 jalur lengkap dan penjumlahan waktu konsisten.
- Log profiling lengkap tidak memuat `Sandbox cleanup error`, `Judging failed`, atau `PROFILE_WRITE_FAILED`. Ini temuan pada pengujian ini, bukan jaminan semua skenario cleanup bebas gangguan.
- Setelah profiling, command dan image normal dipulihkan dengan konfigurasi tetap 50 worker / 50 slot runner / scheduler 1 detik, memakai sandbox `gcc12-v2`. Kelas sementara dihapus, 30 akun uji dinonaktifkan, dan pemeriksaan independen tidak menemukan sandbox tersisa. Pemeriksaan secret terkonfigurasi serta konfigurasi aktif dicatat pada berkas verifikasi.

- Anomali harness: `[]`.
- Pemulihan fixture: `{'class_deleted': True, 'test_accounts_disabled': 30}`. Akun dinonaktifkan, bukan dihapus; akun/kelas lama tidak dihapus.
- Jumlah delivery worker teramati 64 untuk 64 pekerjaan API; cek retry dan trace sebelum menafsirkan delivery tambahan sebagai eksekusi ganda.
- Self-check profiler dijalankan sebelum burst; regresi kapasitas runner tercatat pada VERIFIKASI.md. Trace memakai metadata eksplisit dan tidak mencatat source, input, password, atau token.
- Pengujian hanya satu host, satu soal sederhana, burst 30 pengguna dan kuota pending 20; belum membuktikan kapasitas 50 program aktif, beban berkelanjutan, fault injection, atau target 5–7 detik pada soal lain.
- Selesainya seluruh pekerjaan setelah retry admission tidak berarti seluruh burst awal diterima. Waktu sejak percobaan pertama mencakup jeda retry alat uji.

## Berkas dan pengulangan

[Hasil HTTP/jobs](results.json), [analisis tahap](stage-analysis.json), [CSV pekerjaan](job-stages.csv), [CSV container](container-stages.csv), [requests](requests.csv), [antrean](queue.csv), [trace](traces/), [konfigurasi aktual worker](runtime-config.json), [slot runner](runner-runtime.json), [lingkungan/image](environment.json).

[Verifikasi independen dan jumlah operasi Docker](verification.json), [hash source pengujian](source-hashes.json), [log layanan selama profiling](service-profile.log), dan [sampling sumber daya VM](resources.jsonl). Verifikasi mencocokkan image/command layanan dengan kondisi sebelum instrumentasi, memeriksa cleanup fixture serta sandbox, dan memindai artefak terhadap nilai secret yang terkonfigurasi tanpa mencetak nilainya.

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Wrapper membaca command worker dari Compose, sehingga tidak memaksa concurrency lama. Build dan aktifkan konfigurasi yang hendak diuji terlebih dahulu. Wrapper memverifikasi kapasitas aktual, memasang profiling sementara, lalu mengembalikan command/image tanpa profiling di `finally`. Proses PowerShell yang dihentikan paksa tetap perlu pemulihan manual. Setiap pengulangan menghasilkan direktori baru.
