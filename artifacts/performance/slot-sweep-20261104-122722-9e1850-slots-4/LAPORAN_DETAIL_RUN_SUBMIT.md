# Profil waktu Run dan Submit — konfigurasi 4 worker / 4 slot runner

Pengujian baru: `perf_f38cf8679d`. Mulai UTC: 2026-11-04T05:29:12.840328+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(4, 4)] (concurrency, jumlah proses). Runner: **4 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_f38cf8679d`. Nama kelas: `Performance 30 users perf_f38cf8679d`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.351 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.247 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.261 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 4.248 dtk | 0 |
| run_30 | {'202': 24, '429': 6} | {'EXECUTED': 30} | 30.229 dtk | 0 |
| submit_30 | {'202': 20, '429': 10} | {'ACCEPTED': 30} | 61.761 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 17, 'running': 4, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9721 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 16}`.

Catatan timestamp: `[]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.306 | 0.553 | 0.202 | 0.362 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 2.360 | 7.233 | 1.625 | 2.440 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.425 | 0.946 | 0.510 | 0.869 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 2.678 | 12.836 | 1.984 | 29.589 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.024 | 0.051 | 0.016 | 0.026 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 4.197 | 13.047 | 9.989 | 28.950 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.021 | 0.040 | 0.027 | 0.054 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 3.098 | 4.519 | 7.073 | 8.663 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 0.155 | 1.341 | 0.047 | 0.070 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.575 | 1.545 | 0.684 | 1.028 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 13.264 | 23.553 | 21.474 | 39.549 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 13.838 | 23.878 | 22.158 | 40.105 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 3.126 | 13.459 | 2.511 | 30.121 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 2.981 | 4.363 | 6.963 | 8.474 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.182871 | 0.179867 | `runner` → Docker Engine: membuat sandbox. |
| Start | 0.750428 | 2.151437 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.049636 | 0.049166 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 0.982935 | 2.380470 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.044498 | 0.126235 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.072475 | 0.235564 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.056189 | 0.168934 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 1.741586 | 3.804178 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.076329 | 0.222110 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.006040 | 0.024019 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 2.980783 | 6.962996 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 0.638518 | 0.597060 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.623936 | 0.586015 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 0.714607 | 3.511404 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000026 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 29, cpp17, attempt `e9fbfe6b-9187-42bf-9e36-4a07633e36f6`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 25.151 detik; sejak percobaan pertama: 25.151 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.424 | 0.424 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.424–3.223 | 2.800 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 3.223–3.812 | 0.589 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 3.812–16.649 | 12.836 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 16.649–16.682 | 0.033 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 16.682–21.948 | 5.266 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 21.948–21.963 | 0.015 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 21.963–24.573 | 2.610 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 24.573–24.596 | 0.023 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 24.596–25.151 | 0.554 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=3.335 detik. Runner internal memerlukan 2.517 detik, termasuk lifecycle 0.715 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 22.192–24.020 | 1.828 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: ba3ec4c4b409c7bdf75d01a60f35897de157eed29136506443c943cf88390cc0. |
| 24.020–24.519 | 0.499 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: ba3ec4c4b409c7bdf75d01a60f35897de157eed29136506443c943cf88390cc0. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 22, c17, attempt `8ea855a3-221d-4d73-ad82-f3459345dc23`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 5.008 detik; sejak percobaan pertama: 30.178 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–5.596 | 5.596 | HTTP 429 pada `api`/`db`. |
| 5.596–25.170 | 19.574 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 25.170–25.232 | 0.062 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 25.232–25.927 | 0.695 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 25.927–26.851 | 0.924 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 26.851–27.857 | 1.006 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 27.857–27.910 | 0.054 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 27.910–27.989 | 0.078 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 27.989–28.001 | 0.012 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 28.001–30.041 | 2.040 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 30.041–30.053 | 0.012 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 30.053–30.178 | 0.125 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=25.944 detik. Runner internal memerlukan 1.968 detik, termasuk lifecycle 0.815 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 28.278–29.308 | 1.030 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 08b784bcb3d97e87f98f27d3e1b381fc94af87782b02c71895bd90a04481794a. |
| 29.308–29.986 | 0.678 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 08b784bcb3d97e87f98f27d3e1b381fc94af87782b02c71895bd90a04481794a. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 28, c17, attempt `f49c5618-ea15-420b-8921-484e06b99b88`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 40.137 detik; sejak percobaan pertama: 40.137 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.180 | 0.180 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.180–2.078 | 1.898 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 2.078–2.631 | 0.553 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 2.631–2.637 | 0.006 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 2.637–2.665 | 0.028 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 2.665–33.095 | 30.430 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 33.095–33.114 | 0.019 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 33.114–39.082 | 5.968 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 39.082–39.109 | 0.027 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 39.109–40.137 | 1.028 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=2.097 detik. Runner internal memerlukan 5.808 detik, termasuk lifecycle 1.869 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 33.417–34.477 | 1.060 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: a9f11721e8d1c893297719ae994de1cf16cdedd6e65864d605852d93573f9c34. |
| 34.477–35.330 | 0.853 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: a9f11721e8d1c893297719ae994de1cf16cdedd6e65864d605852d93573f9c34. |
| 35.330–36.191 | 0.861 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: a9f11721e8d1c893297719ae994de1cf16cdedd6e65864d605852d93573f9c34. |
| 36.191–37.080 | 0.889 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: a9f11721e8d1c893297719ae994de1cf16cdedd6e65864d605852d93573f9c34. |
| 37.081–37.955 | 0.875 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: a9f11721e8d1c893297719ae994de1cf16cdedd6e65864d605852d93573f9c34. |
| 37.956–39.008 | 1.052 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: a9f11721e8d1c893297719ae994de1cf16cdedd6e65864d605852d93573f9c34. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 21, cpp17, attempt `f00071c0-9910-4981-b757-9d5a8f0edc09`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 21.570 detik; sejak percobaan pertama: 61.727 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–3.695 | 3.695 | HTTP 429 pada `api`/`db`. |
| 3.695–40.157 | 36.462 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 40.157–40.276 | 0.119 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 40.276–41.426 | 1.150 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 41.426–41.661 | 0.235 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 41.661–41.685 | 0.024 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 41.685–41.711 | 0.026 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 41.711–56.245 | 14.534 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 56.245–56.262 | 0.017 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 56.262–61.489 | 5.228 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 61.489–61.516 | 0.026 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 61.516–61.727 | 0.212 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=41.446 detik. Runner internal memerlukan 5.109 detik, termasuk lifecycle 1.766 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 56.485–58.129 | 1.645 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 2b4ae093d92ccd00e3b0d369bdc24d804c90923898f9a8961f4e033237346c74. |
| 58.129–58.823 | 0.694 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 2b4ae093d92ccd00e3b0d369bdc24d804c90923898f9a8961f4e033237346c74. |
| 58.823–59.557 | 0.733 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 2b4ae093d92ccd00e3b0d369bdc24d804c90923898f9a8961f4e033237346c74. |
| 59.557–60.220 | 0.663 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 2b4ae093d92ccd00e3b0d369bdc24d804c90923898f9a8961f4e033237346c74. |
| 60.220–60.886 | 0.666 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 2b4ae093d92ccd00e3b0d369bdc24d804c90923898f9a8961f4e033237346c74. |
| 60.886–61.451 | 0.565 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 2b4ae093d92ccd00e3b0d369bdc24d804c90923898f9a8961f4e033237346c74. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 3.126 | 0.535 | 2.511 |
| Dispatcher menunggu worker | 0.037 | 2.678 | 0.039 | 1.984 |
| Pekerjaan menunggu worker | 0.021 | 4.197 | 0.026 | 9.989 |
| Lock admission API | 5.213 | 1.338 | 4.999 | 0.722 |
| Create container | 0.453 | 0.183 | 0.387 | 0.180 |
| Start proses container | 2.044 | 0.750 | 5.475 | 2.151 |
| Remove container | 0.149 | 0.050 | 0.117 | 0.049 |
| Inspeksi Docker | 0.153 | 0.056 | 0.509 | 0.169 |
| Total runner | 6.825 | 2.981 | 16.180 | 6.963 |
| Request → hasil tersimpan | 15.423 | 13.264 | 22.958 | 21.474 |
| Request → hasil terlihat | 16.377 | 13.838 | 23.926 | 22.158 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.319 | 1.374 | +4.1% |
| c17_judge | 3.552 | 3.695 | +4.0% |
| cpp17_run | 1.653 | 1.936 | +17.1% |
| cpp17_judge | 3.841 | 4.130 | +7.5% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 3 sampel; CPU rata-rata 11.3%, maksimum 16.0%; memori available minimum 13.28 GiB.

- single_c17_judge: 5 sampel; CPU rata-rata 15.9%, maksimum 24.5%; memori available minimum 13.27 GiB.

- single_cpp17_run: 4 sampel; CPU rata-rata 10.7%, maksimum 18.2%; memori available minimum 13.25 GiB.

- single_cpp17_judge: 4 sampel; CPU rata-rata 17.2%, maksimum 21.6%; memori available minimum 13.25 GiB.

- run_30: 30 sampel; CPU rata-rata 48.0%, maksimum 64.2%; memori available minimum 13.11 GiB.

- submit_30: 62 sampel; CPU rata-rata 48.4%, maksimum 62.5%; memori available minimum 13.04 GiB.

## Analisis hambatan

- run_30: antre worker rata-rata 4.197 detik; runner 2.981 detik; menunggu lock admission rata-rata 1.338 detik, maksimum 6.003 detik. Lifecycle create/start/remove 0.983 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.221 detik, P95 0.907 detik; health check total 0.140 detik per request.
- submit_30: antre worker rata-rata 9.989 detik; runner 6.963 detik; menunggu lock admission rata-rata 0.722 detik, maksimum 1.111 detik. Lifecycle create/start/remove 2.380 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.094 detik, P95 0.356 detik; health check total 0.157 detik per request.

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
