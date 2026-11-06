# Profil waktu Run dan Submit — konfigurasi 16 worker / 16 slot runner

Pengujian baru: `perf_845f516d79`. Mulai UTC: 2026-11-04T06:50:38.583867+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(16, 16)] (concurrency, jumlah proses). Runner: **16 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_845f516d79`. Nama kelas: `Performance 30 users perf_845f516d79`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.387 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 4.271 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.292 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.297 dtk | 0 |
| run_30 | {'202': 25, '429': 5} | {'EXECUTED': 30} | 23.642 dtk | 0 |
| submit_30 | {'202': 20, '429': 10} | {'ACCEPTED': 30} | 45.298 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 14, 'running': 16, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9479 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 15}`.

Catatan timestamp: `[{'attempt_id': '2321932c-62f7-4663-b501-8623c7417622', 'type': 'commit_observed_after_publication', 'overlap_ms': 22.076935}, {'attempt_id': '0faefed8-a6c3-4285-a24d-b7459605828c', 'type': 'commit_observed_after_publication', 'overlap_ms': 30.661815}]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.363 | 0.568 | 0.283 | 0.507 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 3.609 | 12.427 | 2.006 | 4.075 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.335 | 0.913 | 0.479 | 0.929 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 0.703 | 4.963 | 1.556 | 15.603 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.024 | 0.048 | 0.025 | 0.060 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 0.370 | 3.773 | 0.657 | 1.163 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.110 | 0.527 | 0.068 | 0.183 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 5.894 | 9.121 | 15.160 | 20.173 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 1.332 | 2.991 | 0.099 | 0.201 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.881 | 1.724 | 0.801 | 1.806 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 12.740 | 17.929 | 20.331 | 29.128 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 13.621 | 18.265 | 21.132 | 29.862 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 1.063 | 5.541 | 2.059 | 15.807 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 5.566 | 8.411 | 14.953 | 19.979 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.413622 | 0.452094 | `runner` → Docker Engine: membuat sandbox. |
| Start | 1.602782 | 5.281962 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.115278 | 0.096073 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 2.131681 | 5.830129 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.106850 | 0.332871 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.208876 | 0.646548 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.109313 | 0.408738 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 2.777838 | 6.928469 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.193304 | 0.580021 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.035283 | 0.222773 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 5.566255 | 14.952794 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 0.916061 | 1.048876 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.676238 | 0.760449 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 1.241739 | 6.788198 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000027 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 23, cpp17, attempt `9653d084-07d0-4e22-b309-2b71eb548363`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 18.543 detik; sejak percobaan pertama: 18.543 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.568 | 0.568 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.568–9.759 | 9.191 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 9.759–10.218 | 0.459 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 10.218–13.022 | 2.804 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 13.022–13.046 | 0.024 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 13.046–13.190 | 0.144 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 13.190–13.277 | 0.088 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 13.277–18.167 | 4.889 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 18.167–18.182 | 0.015 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 18.182–18.543 | 0.361 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=10.136 detik. Runner internal memerlukan 4.663 detik, termasuk lifecycle 1.736 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 14.121–17.231 | 3.110 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: fe126d5a0e0ac7308e7ba79125a8cca83269f97668fc82576840e1f8a9916def. |
| 17.231–18.133 | 0.902 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: fe126d5a0e0ac7308e7ba79125a8cca83269f97668fc82576840e1f8a9916def. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 3, cpp17, attempt `31fb1126-95b3-4844-82e0-41a52762ec9e`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 5.058 detik; sejak percobaan pertama: 23.635 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–6.410 | 6.410 | HTTP 429 pada `api`/`db`. |
| 6.410–18.577 | 12.167 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 18.577–18.630 | 0.053 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 18.630–19.280 | 0.649 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 19.280–19.306 | 0.026 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 19.306–19.312 | 0.006 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 19.312–19.319 | 0.007 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 19.319–19.325 | 0.005 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 19.325–19.341 | 0.016 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 19.341–22.649 | 3.308 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 22.649–22.663 | 0.014 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 22.663–23.635 | 0.972 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=19.296 detik. Runner internal memerlukan 3.253 detik, termasuk lifecycle 0.945 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 19.610–21.589 | 1.979 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 97d8325dbe2ddbb3584b7bd60b96d0902f8ea2131be9bf7bfb36099cdd1b8ba2. |
| 21.587–22.587 | 0.999 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 97d8325dbe2ddbb3584b7bd60b96d0902f8ea2131be9bf7bfb36099cdd1b8ba2. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 14, c17, attempt `f8fee9ae-c76a-47ee-b571-65de2cb76b9d`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 29.942 detik; sejak percobaan pertama: 29.942 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.356 | 0.356 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.356–4.431 | 4.075 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 4.431–4.580 | 0.149 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 4.580–20.183 | 15.603 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 20.183–20.239 | 0.056 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 20.239–21.401 | 1.163 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 21.401–21.438 | 0.037 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 21.438–29.000 | 7.562 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 29.000–29.042 | 0.042 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 29.042–29.942 | 0.900 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=4.679 detik. Runner internal memerlukan 7.248 detik, termasuk lifecycle 2.965 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 22.253–24.246 | 1.994 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: b902d471fb2b88ccba77e21f51bd87cc6cd2660529d6b06cc52edec8d3b28927. |
| 24.247–25.310 | 1.063 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: b902d471fb2b88ccba77e21f51bd87cc6cd2660529d6b06cc52edec8d3b28927. |
| 25.310–26.240 | 0.930 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: b902d471fb2b88ccba77e21f51bd87cc6cd2660529d6b06cc52edec8d3b28927. |
| 26.240–27.091 | 0.850 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: b902d471fb2b88ccba77e21f51bd87cc6cd2660529d6b06cc52edec8d3b28927. |
| 27.091–27.996 | 0.904 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: b902d471fb2b88ccba77e21f51bd87cc6cd2660529d6b06cc52edec8d3b28927. |
| 27.990–28.932 | 0.943 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: b902d471fb2b88ccba77e21f51bd87cc6cd2660529d6b06cc52edec8d3b28927. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 23, cpp17, attempt `aa285e65-600d-4ef1-bc08-5ead563f8f2e`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 15.241 detik; sejak percobaan pertama: 45.194 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–14.016 | 14.016 | HTTP 429 pada `api`/`db`. |
| 14.016–29.953 | 15.936 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 29.953–30.098 | 0.145 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 30.098–30.813 | 0.716 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 30.813–31.612 | 0.799 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 31.612–31.618 | 0.005 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 31.618–31.631 | 0.014 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 31.631–31.640 | 0.008 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 31.640–31.674 | 0.035 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 31.674–44.266 | 12.592 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 44.266–44.293 | 0.027 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 44.293–45.194 | 0.900 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=30.845 detik. Runner internal memerlukan 12.438 detik, termasuk lifecycle 4.351 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 32.209–36.162 | 3.953 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: e9cf9698b382b30736d6284559f5ca5bd795dc6c4fa825d1e2c73c3a6d7d3264. |
| 36.162–37.787 | 1.625 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: e9cf9698b382b30736d6284559f5ca5bd795dc6c4fa825d1e2c73c3a6d7d3264. |
| 37.787–39.513 | 1.726 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: e9cf9698b382b30736d6284559f5ca5bd795dc6c4fa825d1e2c73c3a6d7d3264. |
| 39.513–41.344 | 1.831 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: e9cf9698b382b30736d6284559f5ca5bd795dc6c4fa825d1e2c73c3a6d7d3264. |
| 41.344–43.261 | 1.917 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: e9cf9698b382b30736d6284559f5ca5bd795dc6c4fa825d1e2c73c3a6d7d3264. |
| 43.261–44.226 | 0.965 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: e9cf9698b382b30736d6284559f5ca5bd795dc6c4fa825d1e2c73c3a6d7d3264. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 1.063 | 0.535 | 2.059 |
| Dispatcher menunggu worker | 0.037 | 0.703 | 0.039 | 1.556 |
| Pekerjaan menunggu worker | 0.021 | 0.370 | 0.026 | 0.657 |
| Lock admission API | 5.213 | 2.322 | 4.999 | 0.919 |
| Create container | 0.453 | 0.414 | 0.387 | 0.452 |
| Start proses container | 2.044 | 1.603 | 5.475 | 5.282 |
| Remove container | 0.149 | 0.115 | 0.117 | 0.096 |
| Inspeksi Docker | 0.153 | 0.109 | 0.509 | 0.409 |
| Total runner | 6.825 | 5.566 | 16.180 | 14.953 |
| Request → hasil tersimpan | 15.423 | 12.740 | 22.958 | 20.331 |
| Request → hasil terlihat | 16.377 | 13.621 | 23.926 | 21.132 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.471 | 1.227 | -16.6% |
| c17_judge | 4.134 | 3.651 | -11.7% |
| cpp17_run | 2.094 | 1.882 | -10.1% |
| cpp17_judge | 4.629 | 4.169 | -9.9% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 3 sampel; CPU rata-rata 15.1%, maksimum 18.0%; memori available minimum 12.76 GiB.

- single_c17_judge: 5 sampel; CPU rata-rata 16.3%, maksimum 27.3%; memori available minimum 12.75 GiB.

- single_cpp17_run: 3 sampel; CPU rata-rata 14.9%, maksimum 19.0%; memori available minimum 12.72 GiB.

- single_cpp17_judge: 5 sampel; CPU rata-rata 14.1%, maksimum 20.5%; memori available minimum 12.71 GiB.

- run_30: 24 sampel; CPU rata-rata 64.2%, maksimum 96.6%; memori available minimum 12.39 GiB.

- submit_30: 45 sampel; CPU rata-rata 68.0%, maksimum 92.6%; memori available minimum 12.24 GiB.

## Analisis hambatan

- run_30: antre worker rata-rata 0.370 detik; runner 5.566 detik; menunggu lock admission rata-rata 2.322 detik, maksimum 11.302 detik. Lifecycle create/start/remove 2.132 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.298 detik, P95 1.335 detik; health check total 0.189 detik per request.
- submit_30: antre worker rata-rata 0.657 detik; runner 14.953 detik; menunggu lock admission rata-rata 0.919 detik, maksimum 2.468 detik. Lifecycle create/start/remove 5.830 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.154 detik, P95 0.642 detik; health check total 0.192 detik per request.

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
