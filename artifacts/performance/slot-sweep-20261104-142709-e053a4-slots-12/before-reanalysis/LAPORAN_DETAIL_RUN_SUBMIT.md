# Profil waktu Run dan Submit — konfigurasi 12 worker / 12 slot runner

Pengujian baru: `perf_90d3cea9ab`. Mulai UTC: 2026-11-04T07:29:03.789391+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(12, 12)] (concurrency, jumlah proses). Runner: **12 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_90d3cea9ab`. Nama kelas: `Performance 30 users perf_90d3cea9ab`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 4.404 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 7.477 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.263 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 6.698 dtk | 0 |
| run_30 | {'202': 25, '429': 5} | {'EXECUTED': 30} | 22.978 dtk | 0 |
| submit_30 | {'202': 21, '429': 9} | {'ACCEPTED': 30} | 42.230 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 14, 'running': 12, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9547 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 14}`.

Catatan timestamp: `[]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.325 | 0.606 | 0.230 | 0.503 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 3.132 | 10.474 | 2.195 | 3.593 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.454 | 0.943 | 0.391 | 0.886 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 0.909 | 6.122 | 0.812 | 11.237 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.026 | 0.051 | 0.037 | 0.102 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 1.107 | 6.089 | 2.267 | 11.758 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.065 | 0.177 | 0.043 | 0.127 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 4.761 | 7.153 | 11.938 | 14.333 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 0.731 | 2.270 | 0.084 | 0.225 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.755 | 1.531 | 0.728 | 1.377 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 11.509 | 16.946 | 17.996 | 26.284 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 12.264 | 17.859 | 18.724 | 27.202 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 1.390 | 6.719 | 1.239 | 11.661 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 4.507 | 6.691 | 11.797 | 14.152 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.316390 | 0.279220 | `runner` → Docker Engine: membuat sandbox. |
| Start | 1.257753 | 3.951855 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.087854 | 0.082319 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 1.661997 | 4.313394 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.086134 | 0.255407 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.145829 | 0.477479 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.091943 | 0.312387 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 2.341812 | 5.880213 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.151237 | 0.459784 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.027155 | 0.093709 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 4.506801 | 11.796671 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 0.859059 | 0.902530 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.701831 | 0.746290 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 0.984168 | 5.615879 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000028 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 21, cpp17, attempt `8cfde6f8-b85b-4d61-a206-165dd7b11d7e`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 17.964 detik; sejak percobaan pertama: 17.964 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.854 | 0.854 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.854–11.328 | 10.474 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 11.328–11.328 | 0.000 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 11.328–12.595 | 1.267 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 12.595–12.623 | 0.028 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 12.623–12.657 | 0.035 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 12.657–12.816 | 0.159 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 12.816–17.161 | 4.345 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 17.161–17.172 | 0.011 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 17.172–17.964 | 0.793 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=11.657 detik. Runner internal memerlukan 4.065 detik, termasuk lifecycle 1.258 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 13.411–16.541 | 3.130 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 5be750d620e2ff4a89d56f9e94d5ca08e0e1e8fa8000f07fb14f53bdb5b63bcc. |
| 16.538–17.128 | 0.590 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 5be750d620e2ff4a89d56f9e94d5ca08e0e1e8fa8000f07fb14f53bdb5b63bcc. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 5, cpp17, attempt `86619b67-63a4-40b3-8ff1-aa01dd49fc27`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 4.980 detik; sejak percobaan pertama: 22.969 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–6.258 | 6.258 | HTTP 429 pada `api`/`db`. |
| 6.258–17.988 | 11.730 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 17.988–18.050 | 0.062 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 18.050–18.453 | 0.404 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 18.453–19.305 | 0.852 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 19.305–19.310 | 0.005 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 19.310–19.316 | 0.006 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 19.316–19.319 | 0.004 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 19.319–19.334 | 0.014 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 19.334–22.450 | 3.116 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 22.450–22.465 | 0.015 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 22.465–22.969 | 0.504 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=18.475 detik. Runner internal memerlukan 3.058 detik, termasuk lifecycle 0.798 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 19.487–21.541 | 2.054 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 68b92c22f4230f4831bd61180690cd26965187ffbccdf2b7e1e0b60c7b071c3a. |
| 21.541–22.376 | 0.835 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 68b92c22f4230f4831bd61180690cd26965187ffbccdf2b7e1e0b60c7b071c3a. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 7, cpp17, attempt `ddda7767-c31f-419c-b520-e7563694143c`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 27.359 detik; sejak percobaan pertama: 27.359 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.372 | 0.372 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.372–3.581 | 3.208 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 3.581–4.319 | 0.738 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 4.319–15.556 | 11.237 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 15.556–15.663 | 0.106 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 15.663–16.300 | 0.637 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 16.300–16.322 | 0.023 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 16.322–26.408 | 10.085 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 26.408–26.428 | 0.020 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 26.428–27.359 | 0.931 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=3.693 detik. Runner internal memerlukan 9.934 detik, termasuk lifecycle 3.266 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 16.804–20.178 | 3.374 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 6311e7cf7d14e7fc9530fbfce9c796a3db9d4c4d179911e0a768cccfb136de78. |
| 20.178–21.884 | 1.706 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 6311e7cf7d14e7fc9530fbfce9c796a3db9d4c4d179911e0a768cccfb136de78. |
| 21.883–23.537 | 1.655 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 6311e7cf7d14e7fc9530fbfce9c796a3db9d4c4d179911e0a768cccfb136de78. |
| 23.537–24.835 | 1.297 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 6311e7cf7d14e7fc9530fbfce9c796a3db9d4c4d179911e0a768cccfb136de78. |
| 24.835–25.751 | 0.917 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 6311e7cf7d14e7fc9530fbfce9c796a3db9d4c4d179911e0a768cccfb136de78. |
| 25.752–26.373 | 0.621 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 6311e7cf7d14e7fc9530fbfce9c796a3db9d4c4d179911e0a768cccfb136de78. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 15, cpp17, attempt `aee39d7a-7440-41ae-a65c-946fdb30e861`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 14.853 detik; sejak percobaan pertama: 42.205 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–7.488 | 7.488 | HTTP 429 pada `api`/`db`. |
| 7.488–27.351 | 19.863 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 27.351–27.455 | 0.103 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 27.455–28.078 | 0.623 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 28.078–28.340 | 0.262 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 28.340–28.348 | 0.008 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 28.348–28.362 | 0.014 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 28.362–28.367 | 0.004 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 28.367–28.386 | 0.019 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 28.386–41.510 | 13.124 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 41.510–41.536 | 0.026 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 41.536–42.205 | 0.669 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=28.095 detik. Runner internal memerlukan 13.042 detik, termasuk lifecycle 4.435 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 28.709–32.371 | 3.663 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 1201fa8fe091f04c6b2a702a7e90998d2ad7cd612cbd886bbbeccd67f43ec29f. |
| 32.372–34.431 | 2.060 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 1201fa8fe091f04c6b2a702a7e90998d2ad7cd612cbd886bbbeccd67f43ec29f. |
| 34.432–36.624 | 2.192 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 1201fa8fe091f04c6b2a702a7e90998d2ad7cd612cbd886bbbeccd67f43ec29f. |
| 36.624–38.654 | 2.030 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 1201fa8fe091f04c6b2a702a7e90998d2ad7cd612cbd886bbbeccd67f43ec29f. |
| 38.654–40.196 | 1.542 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 1201fa8fe091f04c6b2a702a7e90998d2ad7cd612cbd886bbbeccd67f43ec29f. |
| 40.196–41.466 | 1.270 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 1201fa8fe091f04c6b2a702a7e90998d2ad7cd612cbd886bbbeccd67f43ec29f. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 1.390 | 0.535 | 1.239 |
| Dispatcher menunggu worker | 0.037 | 0.909 | 0.039 | 0.812 |
| Pekerjaan menunggu worker | 0.021 | 1.107 | 0.026 | 2.267 |
| Lock admission API | 5.213 | 1.906 | 4.999 | 1.081 |
| Create container | 0.453 | 0.316 | 0.387 | 0.279 |
| Start proses container | 2.044 | 1.258 | 5.475 | 3.952 |
| Remove container | 0.149 | 0.088 | 0.117 | 0.082 |
| Inspeksi Docker | 0.153 | 0.092 | 0.509 | 0.312 |
| Total runner | 6.825 | 4.507 | 16.180 | 11.797 |
| Request → hasil tersimpan | 15.423 | 11.509 | 22.958 | 17.996 |
| Request → hasil terlihat | 16.377 | 12.264 | 23.926 | 18.724 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.458 | 1.715 | +17.7% |
| c17_judge | 3.603 | 4.274 | +18.6% |
| cpp17_run | 1.845 | 1.944 | +5.3% |
| cpp17_judge | 4.461 | 4.607 | +3.3% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 4 sampel; CPU rata-rata 15.0%, maksimum 23.7%; memori available minimum 12.92 GiB.

- single_c17_judge: 8 sampel; CPU rata-rata 15.2%, maksimum 25.0%; memori available minimum 12.90 GiB.

- single_cpp17_run: 3 sampel; CPU rata-rata 17.2%, maksimum 21.6%; memori available minimum 12.88 GiB.

- single_cpp17_judge: 7 sampel; CPU rata-rata 17.2%, maksimum 25.9%; memori available minimum 12.88 GiB.

- run_30: 23 sampel; CPU rata-rata 61.4%, maksimum 89.2%; memori available minimum 12.57 GiB.

- submit_30: 42 sampel; CPU rata-rata 69.4%, maksimum 87.3%; memori available minimum 12.46 GiB.

## Analisis hambatan

- run_30: antre worker rata-rata 1.107 detik; runner 4.507 detik; menunggu lock admission rata-rata 1.906 detik, maksimum 9.138 detik. Lifecycle create/start/remove 1.662 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.279 detik, P95 0.887 detik; health check total 0.183 detik per request.
- submit_30: antre worker rata-rata 2.267 detik; runner 11.797 detik; menunggu lock admission rata-rata 1.081 detik, maksimum 10.494 detik. Lifecycle create/start/remove 4.313 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.170 detik, P95 0.820 detik; health check total 0.161 detik per request.

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
