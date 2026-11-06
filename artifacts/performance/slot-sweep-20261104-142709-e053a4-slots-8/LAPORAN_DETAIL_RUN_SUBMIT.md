# Profil waktu Run dan Submit — konfigurasi 8 worker / 8 slot runner

Pengujian baru: `perf_79f2e38513`. Mulai UTC: 2026-11-04T07:33:22.945478+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(8, 8)] (concurrency, jumlah proses). Runner: **8 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_79f2e38513`. Nama kelas: `Performance 30 users perf_79f2e38513`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.277 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.244 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.202 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.295 dtk | 0 |
| run_30 | {'202': 25, '429': 5} | {'EXECUTED': 30} | 24.594 dtk | 0 |
| submit_30 | {'429': 10, '202': 20} | {'ACCEPTED': 30} | 46.234 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 13, 'running': 8, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9494 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 15}`.

Catatan timestamp: `[]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.331 | 0.574 | 0.204 | 0.320 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 3.258 | 9.621 | 1.643 | 2.982 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.348 | 0.878 | 0.443 | 0.954 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 2.106 | 6.119 | 2.681 | 10.108 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.026 | 0.058 | 0.032 | 0.107 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 1.616 | 5.832 | 3.148 | 10.197 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.037 | 0.075 | 0.035 | 0.054 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 4.167 | 5.944 | 9.124 | 11.135 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 0.344 | 1.406 | 0.067 | 0.130 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.681 | 1.478 | 0.659 | 1.198 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 12.233 | 19.053 | 17.376 | 28.846 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 12.914 | 19.780 | 18.036 | 29.816 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 2.480 | 7.026 | 3.156 | 11.102 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 3.999 | 5.619 | 8.996 | 11.008 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.285185 | 0.241097 | `runner` → Docker Engine: membuat sandbox. |
| Start | 1.133242 | 3.010170 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.075861 | 0.069213 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 1.494288 | 3.320481 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.074765 | 0.174632 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.123408 | 0.319916 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.092550 | 0.216001 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 2.062521 | 4.588548 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.135263 | 0.319991 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.015439 | 0.055024 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 3.998886 | 8.996028 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 0.735567 | 0.703917 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.674929 | 0.651360 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 0.855114 | 4.332171 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000081 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 27, cpp17, attempt `d9fbf86f-ad43-4e49-a224-090d838484b3`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 19.814 detik; sejak percobaan pertama: 19.814 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.435 | 0.435 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.435–7.871 | 7.437 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 7.871–7.871 | 0.000 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 7.871–9.921 | 2.050 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 9.921–9.978 | 0.057 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 9.978–14.354 | 4.375 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 14.354–14.374 | 0.020 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 14.374–18.883 | 4.510 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 18.883–18.901 | 0.018 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 18.901–19.814 | 0.913 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=8.033 detik. Runner internal memerlukan 4.361 detik, termasuk lifecycle 1.368 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 14.713–17.668 | 2.955 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 8a83da393ced69d566ed426eb71ccb82e445099f9953921ae8afc2863e6bddcb. |
| 17.668–18.820 | 1.152 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 8a83da393ced69d566ed426eb71ccb82e445099f9953921ae8afc2863e6bddcb. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 3, cpp17, attempt `585f717e-9e7b-4d96-b2f3-e3c4118f6e31`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 4.681 detik; sejak percobaan pertama: 24.551 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–5.700 | 5.700 | HTTP 429 pada `api`/`db`. |
| 5.700–19.871 | 14.171 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 19.871–19.908 | 0.037 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 19.908–20.236 | 0.328 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 20.236–20.895 | 0.659 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 20.895–20.901 | 0.006 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 20.901–20.906 | 0.005 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 20.906–20.908 | 0.002 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 20.908–20.929 | 0.021 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 20.929–24.021 | 3.091 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 24.021–24.067 | 0.047 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 24.067–24.551 | 0.484 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=20.271 detik. Runner internal memerlukan 3.033 detik, termasuk lifecycle 0.893 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 21.189–23.070 | 1.881 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: d6a1657e07fb7c12d3ce911e7befdbd28c21e9e232a1b9a2a412d664e396177d. |
| 23.070–23.921 | 0.852 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: d6a1657e07fb7c12d3ce911e7befdbd28c21e9e232a1b9a2a412d664e396177d. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 21, cpp17, attempt `dbd73e5b-860c-4b31-a071-0fe6365a1096`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 29.837 detik; sejak percobaan pertama: 29.837 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.261 | 0.261 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.261–2.472 | 2.211 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 2.472–3.265 | 0.793 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 3.265–13.373 | 10.108 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 13.373–13.478 | 0.105 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 13.478–21.473 | 7.995 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 21.473–21.504 | 0.031 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 21.504–28.814 | 7.310 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 28.814–28.846 | 0.032 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 28.846–29.837 | 0.991 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=2.510 detik. Runner internal memerlukan 7.205 detik, termasuk lifecycle 2.478 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 21.897–24.479 | 2.582 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 64982040a77df06d8be5a3aef67c4ce482f229084379eab9964e5ad01c124fa8. |
| 24.479–25.262 | 0.784 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 64982040a77df06d8be5a3aef67c4ce482f229084379eab9964e5ad01c124fa8. |
| 25.263–26.119 | 0.857 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 64982040a77df06d8be5a3aef67c4ce482f229084379eab9964e5ad01c124fa8. |
| 26.120–27.027 | 0.907 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 64982040a77df06d8be5a3aef67c4ce482f229084379eab9964e5ad01c124fa8. |
| 27.027–27.884 | 0.857 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 64982040a77df06d8be5a3aef67c4ce482f229084379eab9964e5ad01c124fa8. |
| 27.884–28.751 | 0.867 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 64982040a77df06d8be5a3aef67c4ce482f229084379eab9964e5ad01c124fa8. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 16, c17, attempt `b6cd5d56-ac54-4c1d-8c8e-a33521465486`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 16.341 detik; sejak percobaan pertama: 46.195 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–9.248 | 9.248 | HTTP 429 pada `api`/`db`. |
| 9.248–29.854 | 20.606 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 29.854–29.965 | 0.112 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 29.965–30.419 | 0.454 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 30.419–31.317 | 0.898 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 31.317–31.322 | 0.006 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 31.322–31.341 | 0.019 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 31.341–40.097 | 8.756 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 40.097–40.139 | 0.042 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 40.139–45.145 | 5.006 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 45.145–45.172 | 0.026 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 45.172–46.195 | 1.023 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=30.558 detik. Runner internal memerlukan 4.863 detik, termasuk lifecycle 1.907 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 40.453–41.800 | 1.347 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: be57f97493bf4ef3c7e701b847afcd7c1646e580bec6a71d268346e8407103e0. |
| 41.800–42.605 | 0.805 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: be57f97493bf4ef3c7e701b847afcd7c1646e580bec6a71d268346e8407103e0. |
| 42.605–43.196 | 0.591 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: be57f97493bf4ef3c7e701b847afcd7c1646e580bec6a71d268346e8407103e0. |
| 43.196–43.822 | 0.626 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: be57f97493bf4ef3c7e701b847afcd7c1646e580bec6a71d268346e8407103e0. |
| 43.820–44.492 | 0.672 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: be57f97493bf4ef3c7e701b847afcd7c1646e580bec6a71d268346e8407103e0. |
| 44.492–45.105 | 0.613 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: be57f97493bf4ef3c7e701b847afcd7c1646e580bec6a71d268346e8407103e0. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 2.480 | 0.535 | 3.156 |
| Dispatcher menunggu worker | 0.037 | 2.106 | 0.039 | 2.681 |
| Pekerjaan menunggu worker | 0.021 | 1.616 | 0.026 | 3.148 |
| Lock admission API | 5.213 | 2.071 | 4.999 | 0.696 |
| Create container | 0.453 | 0.285 | 0.387 | 0.241 |
| Start proses container | 2.044 | 1.133 | 5.475 | 3.010 |
| Remove container | 0.149 | 0.076 | 0.117 | 0.069 |
| Inspeksi Docker | 0.153 | 0.093 | 0.509 | 0.216 |
| Total runner | 6.825 | 3.999 | 16.180 | 8.996 |
| Request → hasil tersimpan | 15.423 | 12.233 | 22.958 | 17.376 |
| Request → hasil terlihat | 16.377 | 12.914 | 23.926 | 18.035 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.359 | 1.207 | -11.2% |
| c17_judge | 3.361 | 3.474 | +3.4% |
| cpp17_run | 1.770 | 1.862 | +5.2% |
| cpp17_judge | 3.715 | 3.910 | +5.2% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 4 sampel; CPU rata-rata 14.4%, maksimum 17.9%; memori available minimum 13.09 GiB.

- single_c17_judge: 5 sampel; CPU rata-rata 13.3%, maksimum 21.4%; memori available minimum 13.08 GiB.

- single_cpp17_run: 3 sampel; CPU rata-rata 16.6%, maksimum 21.3%; memori available minimum 13.08 GiB.

- single_cpp17_judge: 5 sampel; CPU rata-rata 14.3%, maksimum 18.4%; memori available minimum 13.08 GiB.

- run_30: 25 sampel; CPU rata-rata 56.9%, maksimum 79.2%; memori available minimum 12.80 GiB.

- submit_30: 46 sampel; CPU rata-rata 60.1%, maksimum 81.4%; memori available minimum 12.76 GiB.

## Analisis hambatan

- run_30: antre worker rata-rata 1.616 detik; runner 3.999 detik; menunggu lock admission rata-rata 2.071 detik, maksimum 7.938 detik. Lifecycle create/start/remove 1.494 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.233 detik, P95 0.849 detik; health check total 0.177 detik per request.
- submit_30: antre worker rata-rata 3.148 detik; runner 8.996 detik; menunggu lock admission rata-rata 0.696 detik, maksimum 1.557 detik. Lifecycle create/start/remove 3.320 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.114 detik, P95 0.463 detik; health check total 0.155 detik per request.

Angka tersebut perlu dibaca bersama kontrol tanpa profiler, sumber daya VM, dan batas admission. Concurrency lebih besar dapat mengurangi antrean sekaligus memperlambat setiap pekerjaan. Tidak ada optimasi lanjutan yang otomatis diterapkan oleh alat uji.

## Anomali, validasi, dan batas kesimpulan

- Anomali harness: `[]`.
- Pemulihan fixture: `{'class_deleted': True, 'test_accounts_disabled': 30}`. Akun dinonaktifkan, bukan dihapus; akun/kelas lama tidak dihapus.
- Jumlah delivery worker teramati 64 untuk 64 pekerjaan API; cek retry dan trace sebelum menafsirkan delivery tambahan sebagai eksekusi ganda.
- Self-check profiler dijalankan sebelum burst; regresi kapasitas runner tercatat pada VERIFIKASI.md. Trace memakai metadata eksplisit dan tidak mencatat source, input, password, atau token.
- Pengujian hanya satu host, satu soal sederhana, burst 30 pengguna dan kuota pending 20; belum membuktikan kapasitas 50 program aktif, beban berkelanjutan, fault injection, atau target 5–7 detik pada soal lain.
- Selesainya seluruh pekerjaan setelah retry admission tidak berarti seluruh burst awal diterima. Waktu sejak percobaan pertama mencakup jeda retry alat uji.

## Berkas dan pengulangan

[Hasil HTTP/jobs](results.json), [analisis tahap](stage-analysis.json), [CSV pekerjaan](job-stages.csv), [CSV container](container-stages.csv), [requests](requests.csv), [antrean](queue.csv), [trace](traces/), [konfigurasi aktual worker](runtime-config.json), [slot runner](runner-runtime.json), [lingkungan/image](environment.json).

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Wrapper membaca command worker dari Compose, sehingga tidak memaksa concurrency lama. Build dan aktifkan konfigurasi yang hendak diuji terlebih dahulu. Wrapper memverifikasi kapasitas aktual, memasang profiling sementara, lalu mengembalikan command/image tanpa profiling di `finally`. Proses PowerShell yang dihentikan paksa tetap perlu pemulihan manual. Setiap pengulangan menghasilkan direktori baru.
