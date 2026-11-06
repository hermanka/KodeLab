# Profil waktu Run dan Submit — konfigurasi 50 worker / 50 slot runner

**Setelah memperpendek transaksi admission API.** Rata-rata menunggu lock turun 5,213 → **1,518 detik pada Run** dan 4,999 → **2,507 detik pada Submit**. Rata-rata request yang diterima sampai hasil terlihat menjadi **11,556 / 23,012 detik**, dibanding 16,378 / 23,926 detik sebelumnya. Seluruh 64 pekerjaan benar. Target 5–7 detik belum tercapai, dan durasi penyelesaian seluruh burst 30 peserta hampir tidak berubah karena kapasitas eksekusi serta penolakan/retry admission masih berpengaruh.

Pengujian baru: `perf_30e1e8fad3`. Mulai UTC: 2026-11-04T04:55:55.933632+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

Perubahan yang diuji hanya pada admission: preflight tanpa lock tulis, pelepasan transaksi/koneksi sebelum health check dan persiapan provider, lalu pemeriksaan ulang izin/status/provider di dalam transaksi dengan lock. Kuota, urutan admission sebelum enrollment/kelas, idempotensi, snapshot provider, dan penyimpanan job/audit atomik tetap berlaku. Jika provider/revisi berubah selama preflight, API menolak 409. API baru memakai image `56dd4884b7d6010c72750348c85a2aaa6321cc461176db05b6c15b1bad7ca3d5`; worker, scheduler, dan runner mempertahankan image sebelumnya. Tidak ada migrasi skema atau perubahan kapasitas.

Sebelum benchmark: **100 tes unit/API lulus**, **4 tes MariaDB disposable lulus**. Tes mencakup koneksi/lock bebas saat health check ditahan, permintaan lain tetap diterima, kuota global 49 → 50 tanpa terlewati, idempotency key bersamaan menghasilkan satu pekerjaan, akses yang dicabut/kelas diarsipkan/akun nonaktif saat health check ditolak, provider yang berubah ditolak, retry ketika runner offline, dan atomisitas audit. Dua belas tes Docker tidak diulang pada suite biasa karena runner tidak berubah; hasil sebelumnya tetap tercatat di VERIFIKASI.md.

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(50, 50)] (concurrency, jumlah proses). Runner: **50 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_30e1e8fad3`. Nama kelas: `Performance 30 users perf_30e1e8fad3`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.296 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.289 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 2.177 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 4.233 dtk | 0 |
| run_30 | {'202': 23, '429': 7} | {'EXECUTED': 30} | 22.230 dtk | 0 |
| submit_30 | {'202': 23, '429': 7} | {'ACCEPTED': 30} | 44.586 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 14, 'running': 20, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9344 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 14}`.

Catatan timestamp: `[]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.293 | 0.487 | 0.288 | 0.685 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 2.382 | 10.764 | 3.625 | 20.538 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.409 | 0.933 | 0.485 | 0.962 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 0.018 | 0.052 | 0.013 | 0.035 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.015 | 0.023 | 0.016 | 0.030 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 0.016 | 0.033 | 0.015 | 0.031 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.100 | 0.351 | 0.050 | 0.107 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 6.245 | 8.978 | 17.561 | 23.806 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 1.491 | 3.038 | 0.114 | 0.250 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.586 | 1.269 | 0.847 | 2.045 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 10.969 | 15.702 | 22.166 | 30.811 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 11.556 | 16.160 | 23.012 | 31.424 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 0.442 | 0.969 | 0.513 | 0.982 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 5.908 | 8.605 | 17.319 | 23.565 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.401011 | 0.386982 | `runner` → Docker Engine: membuat sandbox. |
| Start | 1.733443 | 5.974905 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.123168 | 0.120417 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 2.257622 | 6.482303 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.120630 | 0.444816 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.228834 | 0.853124 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.125531 | 0.478469 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 2.899024 | 8.005612 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.202065 | 0.702139 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.073334 | 0.343627 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 5.908058 | 17.319457 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 1.003476 | 1.331895 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.658166 | 0.731139 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 1.351241 | 7.909584 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000210 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 23, cpp17, attempt `802da295-9277-4d2a-99e9-f796168c6fa5`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 16.270 detik; sejak percobaan pertama: 16.270 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.982 | 0.982 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.982–11.745 | 10.764 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 11.745–12.049 | 0.304 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 12.049–12.061 | 0.011 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 12.061–12.084 | 0.023 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 12.084–12.116 | 0.033 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 12.116–12.236 | 0.120 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 12.236–15.676 | 3.439 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 15.676–15.702 | 0.026 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 15.702–16.270 | 0.569 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=11.791 detik. Runner internal memerlukan 3.094 detik, termasuk lifecycle 1.138 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 12.997–15.026 | 2.029 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 6759e86b731fea3848f7cdcd8f851efde02e7cb341a795994770eeaa9e9a9747. |
| 15.026–15.629 | 0.603 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 6759e86b731fea3848f7cdcd8f851efde02e7cb341a795994770eeaa9e9a9747. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 29, cpp17, attempt `b8396ca2-3022-46c8-9d8f-ab02e7ff3041`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 5.913 detik; sejak percobaan pertama: 22.186 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–7.080 | 7.080 | HTTP 429 pada `api`/`db`. |
| 7.080–16.272 | 9.192 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 16.272–16.342 | 0.070 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 16.342–16.776 | 0.434 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 16.776–17.043 | 0.267 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 17.043–17.053 | 0.010 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 17.053–17.073 | 0.020 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 17.073–17.094 | 0.022 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 17.094–17.127 | 0.032 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 17.127–21.295 | 4.168 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 21.295–21.309 | 0.014 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 21.309–22.186 | 0.877 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=16.791 detik. Runner internal memerlukan 4.077 detik, termasuk lifecycle 1.110 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 17.376–20.096 | 2.720 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: daf3c9e26d7a37242176a9c6fa17be63376e34cabf3aa6c263ea3246b2f1d893. |
| 20.096–21.247 | 1.151 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: daf3c9e26d7a37242176a9c6fa17be63376e34cabf3aa6c263ea3246b2f1d893. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 19, cpp17, attempt `7989e992-1789-409e-8806-96b733a72c05`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 32.247 detik; sejak percobaan pertama: 32.247 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–1.022 | 1.022 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 1.022–24.192 | 23.170 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 24.192–24.913 | 0.721 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 24.913–24.960 | 0.047 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 24.960–24.966 | 0.006 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 24.966–24.972 | 0.006 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 24.972–25.025 | 0.052 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 25.025–32.183 | 7.159 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 32.183–32.228 | 0.045 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 32.228–32.247 | 0.019 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=24.481 detik. Runner internal memerlukan 6.961 detik, termasuk lifecycle 2.599 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 25.681–28.596 | 2.915 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: a087346d037c2de7dd934806717b2cbd338c4a7234b16338141bc3e9a14131a9. |
| 28.597–29.333 | 0.737 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: a087346d037c2de7dd934806717b2cbd338c4a7234b16338141bc3e9a14131a9. |
| 29.333–30.201 | 0.867 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: a087346d037c2de7dd934806717b2cbd338c4a7234b16338141bc3e9a14131a9. |
| 30.201–30.961 | 0.760 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: a087346d037c2de7dd934806717b2cbd338c4a7234b16338141bc3e9a14131a9. |
| 30.961–31.522 | 0.561 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: a087346d037c2de7dd934806717b2cbd338c4a7234b16338141bc3e9a14131a9. |
| 31.522–32.145 | 0.623 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: a087346d037c2de7dd934806717b2cbd338c4a7234b16338141bc3e9a14131a9. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 9, cpp17, attempt `fb006e99-efc4-4a2a-bd31-0cdb1cb7658b`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 12.305 detik; sejak percobaan pertama: 44.571 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–4.783 | 4.783 | HTTP 429 pada `api`/`db`. |
| 4.783–32.266 | 27.483 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 32.266–32.406 | 0.140 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 32.406–33.106 | 0.700 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 33.106–33.936 | 0.830 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 33.936–33.943 | 0.007 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 33.943–33.956 | 0.013 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 33.956–33.971 | 0.016 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 33.971–33.991 | 0.020 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 33.991–43.772 | 9.780 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 43.772–43.798 | 0.027 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 43.798–44.571 | 0.773 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=33.153 detik. Runner internal memerlukan 9.638 detik, termasuk lifecycle 2.972 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 34.399–37.324 | 2.925 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 885314844c804ccbeaf09521007977f6c18bbfbe96af12c748f8be15d4ef4fd3. |
| 37.324–38.846 | 1.522 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 885314844c804ccbeaf09521007977f6c18bbfbe96af12c748f8be15d4ef4fd3. |
| 38.846–40.412 | 1.565 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 885314844c804ccbeaf09521007977f6c18bbfbe96af12c748f8be15d4ef4fd3. |
| 40.412–41.766 | 1.354 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 885314844c804ccbeaf09521007977f6c18bbfbe96af12c748f8be15d4ef4fd3. |
| 41.766–42.954 | 1.188 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 885314844c804ccbeaf09521007977f6c18bbfbe96af12c748f8be15d4ef4fd3. |
| 42.954–43.696 | 0.742 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 885314844c804ccbeaf09521007977f6c18bbfbe96af12c748f8be15d4ef4fd3. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 0.442 | 0.535 | 0.513 |
| Dispatcher menunggu worker | 0.037 | 0.018 | 0.039 | 0.013 |
| Pekerjaan menunggu worker | 0.021 | 0.016 | 0.026 | 0.015 |
| Lock admission API | 5.213 | 1.518 | 4.999 | 2.507 |
| Create container | 0.453 | 0.401 | 0.387 | 0.387 |
| Start proses container | 2.044 | 1.733 | 5.475 | 5.975 |
| Remove container | 0.149 | 0.123 | 0.117 | 0.120 |
| Inspeksi Docker | 0.153 | 0.126 | 0.509 | 0.478 |
| Total runner | 6.825 | 5.908 | 16.180 | 17.319 |
| Request → hasil tersimpan | 15.423 | 10.969 | 22.958 | 22.166 |
| Request → hasil terlihat | 16.377 | 11.556 | 23.926 | 23.012 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.285 | 1.183 | -7.9% |
| c17_judge | 3.222 | 3.472 | +7.7% |
| cpp17_run | 1.561 | 1.669 | +6.9% |
| cpp17_judge | 3.888 | 3.660 | -5.9% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 3 sampel; CPU rata-rata 12.9%, maksimum 19.6%; memori available minimum 11.51 GiB.

- single_c17_judge: 6 sampel; CPU rata-rata 14.1%, maksimum 20.7%; memori available minimum 11.49 GiB.

- single_cpp17_run: 2 sampel; CPU rata-rata 12.3%, maksimum 14.6%; memori available minimum 11.49 GiB.

- single_cpp17_judge: 4 sampel; CPU rata-rata 18.6%, maksimum 21.7%; memori available minimum 11.50 GiB.

- run_30: 22 sampel; CPU rata-rata 66.0%, maksimum 96.4%; memori available minimum 11.00 GiB.

- submit_30: 44 sampel; CPU rata-rata 69.5%, maksimum 97.6%; memori available minimum 10.73 GiB.

## Analisis hambatan

### Efek pada admission

Waktu menunggu lock berbeda dari waktu lock dipegang. Waktu dipegang dihitung dari akhir span pengambilan admission lock sampai observasi commit; angka merupakan batas pengamatan profiler, bukan pengukuran internal server MariaDB. Angka pembanding di bawah dihitung kembali dari trace lama secara baca-saja, tanpa mengubah artefak lama.

| Ukuran admission (detik) | Run sebelum | Run sesudah | Submit sebelum | Submit sesudah |
|---|---:|---:|---:|---:|
| Menunggu lock, rata-rata | 5,213 | **1,518** | 4,999 | **2,507** |
| Menunggu lock, maksimum | 16,066 | **9,617** | 24,819 | **19,151** |
| Lock dipegang sampai commit, rata-rata | 0,587 | **0,188** | 0,520 | **0,364** |
| Lock dipegang sampai commit, P95 | 1,679 | **0,770** | 1,820 | **3,272** |
| Lock dipegang sampai commit, maksimum | 2,307 | **1,236** | 1,989 | **3,273** |
| Awal handler API sampai commit, rata-rata | 5,800 | **2,382** | 5,519 | **3,625** |

1. **Perbaikan bekerja pada rata-rata, tetapi belum menghilangkan penantian panjang.** Menunggu lock turun sekitar 70,9% pada Run dan 49,9% pada Submit. Waktu lock dipegang rata-rata juga turun. Namun P95 dan maksimum waktu memegang lock Submit justru meningkat pada burst ini. Pemeriksaan ulang izin/metadata, penghitungan kuota, dan penyimpanan tetap serial di dalam lock; health check sudah berada di luar dan tidak menahan koneksi/lock, sebagaimana diuji terpisah.
2. **Masih ada operasi DB yang lambat ketika host sibuk.** Pada request Submit dengan waktu memegang lock terlama, beberapa span operasi DB individual berada sekitar 0,4–0,84 detik dan total waktu memegang lock 3,273 detik. Metadata ini tidak menyimpan isi SQL atau memisahkan penjadwalan thread, latency koneksi, serta lock internal MariaDB; belum cukup untuk menyebut satu query tertentu sebagai penyebab. Tetap ada alasan untuk memprofilkan SQL di dalam admission sebelum memperluas perubahan ke penghitung kuota atomik atau pembagian lock.
3. **Waktu eksekusi Submit tetap dominan.** Runner Submit rata-rata 16,180 → 17,319 detik, sementara request sampai hasil terlihat 23,926 → 23,012 detik, hanya sekitar 3,8% lebih cepat. Start proses sekitar 5,975 detik dan wait 8,006 detik berada di dalam total runner; wait mencakup waktu compiler/program, bukan overhead murni. CPU VM mencapai 97,6% pada Submit, memori available minimum 10,73 GiB. Data mendukung adanya beban pada jalur eksekusi/host, tetapi tidak memisahkan penyebab tunggalnya.
4. **Penolakan kuota dan retry mengubah pengalaman seluruh peserta.** Burst awal Run dan Submit masing-masing menerima 23 dan menolak 7. Running/pending maksimum tetap 20: pekerjaan yang selesai selagi admission berlangsung membebaskan kuota untuk beberapa request berikutnya. Retry dilakukan alat uji setelah gelombang sebelumnya selesai, bukan otomatis oleh UI. Respons 429 Run membutuhkan sekitar 4,511–11,603 detik; Submit 4,783–17,138 detik. Penolakan masih bisa datang terlambat.

### Waktu sejak percobaan pertama dan batas kesimpulan

| Ukuran termasuk penolakan/retry alat uji | Run sebelum | Run sesudah | Submit sebelum | Submit sesudah |
|---|---:|---:|---:|---:|
| Rata-rata sampai hasil terlihat | 16,378 | **15,354** | 29,829 | **30,541** |
| Maksimum sampai hasil terlihat | 22,282 | **22,186** | 44,389 | **44,571** |
| Durasi seluruh fase 30 peserta | 22,319 | **22,230** | 44,419 | **44,586** |

Jadi, penurunan waktu request yang diterima tidak berarti seluruh 30 peserta selesai jauh lebih cepat. Secara keseluruhan durasi fase hampir sama, dan rata-rata Submit sejak percobaan pertama sedikit memburuk karena pola penolakan/retry berbeda. Perbandingan satu pengulangan pada satu host juga dipengaruhi variasi host; kontrol RPC langsung menunjukkan perbedaan antar-pengukuran meskipun kode runner tidak diubah. Hasil bukan jaminan target 5–7 detik atau kapasitas 50 program aktif.

Prioritas lanjutan: ukur lebih rinci operasi DB yang masih berada dalam admission, serta kalibrasi concurrency terhadap CPU/start proses. Kuota jangan dihapus untuk menyamarkan penantian; penggantian mekanisme kuota harus tetap menjaga batas bersama dan idempotensi. Tidak ada optimasi lanjutan diterapkan setelah benchmark ini.

- run_30: antre worker rata-rata 0.016 detik; runner 5.908 detik; menunggu lock admission rata-rata 1.518 detik, maksimum 9.617 detik. Lifecycle create/start/remove 2.258 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.188 detik, P95 0.770 detik; health check total 0.099 detik per request.
- submit_30: antre worker rata-rata 0.015 detik; runner 17.319 detik; menunggu lock admission rata-rata 2.507 detik, maksimum 19.151 detik. Lifecycle create/start/remove 6.482 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.364 detik, P95 3.272 detik; health check total 0.126 detik per request.

Angka tersebut perlu dibaca bersama kontrol tanpa profiler, sumber daya VM, dan batas admission. Concurrency lebih besar dapat mengurangi antrean sekaligus memperlambat setiap pekerjaan. Tidak ada optimasi lanjutan yang otomatis diterapkan oleh alat uji.

## Anomali, validasi, dan batas kesimpulan

- Seluruh 32 Run menghasilkan Executed dan 32 Submit menghasilkan Accepted, tanpa salah output/nilai, system_error atau retry eksekusi yang ditemukan harness; seluruh 30 peserta mencapai progres/nilai 100 dan test privat tetap disembunyikan.
- Empat belas error span HTTPException merupakan penolakan admission 429, bukan kegagalan penilaian. Analisis 9.344 rekaman lengkap 64/64, tanpa interval negatif atau koreksi batas commit pada pengujian ini. Tidak ditemukan peringatan cleanup, kegagalan judge, atau kegagalan penulisan profiler dalam log layanan.
- Setelah pengujian, command/image normal dipulihkan tanpa profiler, tetap memakai API yang diperbaiki dan konfigurasi 50/50/1 dengan sandbox gcc12-v2. Kelas sementara dihapus, 30 akun dinonaktifkan, dan verifikasi independen memeriksa tidak ada sandbox/pekerjaan tertinggal. Artefak dipindai terhadap nilai secret terkonfigurasi tanpa mencetak nilainya.

- Anomali harness: `[]`.
- Pemulihan fixture: `{'class_deleted': True, 'test_accounts_disabled': 30}`. Akun dinonaktifkan, bukan dihapus; akun/kelas lama tidak dihapus.
- Jumlah delivery worker teramati 64 untuk 64 pekerjaan API; cek retry dan trace sebelum menafsirkan delivery tambahan sebagai eksekusi ganda.
- Self-check profiler dijalankan sebelum burst; regresi kapasitas runner tercatat pada VERIFIKASI.md. Trace memakai metadata eksplisit dan tidak mencatat source, input, password, atau token.
- Pengujian hanya satu host, satu soal sederhana, burst 30 pengguna dan kuota pending 20; belum membuktikan kapasitas 50 program aktif, beban berkelanjutan, fault injection, atau target 5–7 detik pada soal lain.
- Selesainya seluruh pekerjaan setelah retry admission tidak berarti seluruh burst awal diterima. Waktu sejak percobaan pertama mencakup jeda retry alat uji.

## Berkas dan pengulangan

[Hasil HTTP/jobs](results.json), [analisis tahap](stage-analysis.json), [CSV pekerjaan](job-stages.csv), [CSV container](container-stages.csv), [requests](requests.csv), [antrean](queue.csv), [trace](traces/), [konfigurasi aktual worker](runtime-config.json), [slot runner](runner-runtime.json), [lingkungan/image](environment.json).

[Verifikasi independen](verification.json), [hash source](source-hashes.json), [log layanan](service-profile.log), dan [sampling sumber daya VM](resources.jsonl).

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Wrapper membaca command worker dari Compose, sehingga tidak memaksa concurrency lama. Build dan aktifkan konfigurasi yang hendak diuji terlebih dahulu. Wrapper memverifikasi kapasitas aktual, memasang profiling sementara, lalu mengembalikan command/image tanpa profiling di `finally`. Proses PowerShell yang dihentikan paksa tetap perlu pemulihan manual. Setiap pengulangan menghasilkan direktori baru.
