# Profil waktu Run dan Submit — konfigurasi 8 worker / 8 slot runner

Pengujian baru: `perf_17edfe4605`. Mulai UTC: 2026-11-04T06:41:57.959177+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(8, 8)] (concurrency, jumlah proses). Runner: **8 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_17edfe4605`. Nama kelas: `Performance 30 users perf_17edfe4605`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.336 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 4.315 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.275 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 4.228 dtk | 0 |
| run_30 | {'202': 23, '429': 7} | {'EXECUTED': 30} | 20.863 dtk | 0 |
| submit_30 | {'202': 20, '429': 10} | {'ACCEPTED': 30} | 43.896 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 17, 'running': 8, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9465 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 17}`.

Catatan timestamp: `[{'attempt_id': '011b6dec-27a9-447d-890f-93e85fe4f713', 'type': 'commit_observed_after_publication', 'overlap_ms': 1.118461}]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.290 | 0.506 | 0.227 | 0.369 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 2.134 | 6.454 | 1.568 | 2.439 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.308 | 0.923 | 0.465 | 0.923 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 1.435 | 3.718 | 1.727 | 17.216 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.022 | 0.048 | 0.021 | 0.039 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 0.911 | 4.279 | 3.635 | 9.977 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.028 | 0.058 | 0.038 | 0.057 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 3.424 | 4.441 | 8.497 | 10.221 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 0.280 | 1.142 | 0.064 | 0.120 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.621 | 1.164 | 0.577 | 1.061 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 8.833 | 14.676 | 16.241 | 27.883 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 9.454 | 15.572 | 16.818 | 28.593 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 1.765 | 4.666 | 2.213 | 17.943 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 3.295 | 4.201 | 8.382 | 10.066 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.243579 | 0.290306 | `runner` → Docker Engine: membuat sandbox. |
| Start | 0.868621 | 2.785090 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.066918 | 0.067282 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 1.179118 | 3.142678 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.052615 | 0.156539 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.094250 | 0.293480 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.069046 | 0.217506 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 1.784190 | 4.194548 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.102374 | 0.317144 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.012108 | 0.058412 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 3.294518 | 8.381914 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 0.623417 | 0.619545 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.578987 | 0.569142 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 0.758959 | 3.983590 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000060 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 19, cpp17, attempt `e3411611-2a24-4294-90db-673b0d052a93`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 15.587 detik; sejak percobaan pertama: 15.587 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.413 | 0.413 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.413–2.483 | 2.070 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 2.483–3.293 | 0.810 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 3.293–7.012 | 3.718 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 7.012–7.060 | 0.048 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 7.060–11.230 | 4.170 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 11.230–11.255 | 0.025 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 11.255–14.657 | 3.403 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 14.657–14.676 | 0.019 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 14.676–15.587 | 0.910 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=2.543 detik. Runner internal memerlukan 3.302 detik, termasuk lifecycle 0.993 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 11.620–13.829 | 2.209 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 06ee9952431c9baea5a90b54e2158a038fbfa8eafe08570286f38b90409745fa. |
| 13.829–14.615 | 0.786 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 06ee9952431c9baea5a90b54e2158a038fbfa8eafe08570286f38b90409745fa. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 15, cpp17, attempt `0c8fc1f8-12a5-4290-bcb1-5325d4da8029`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 5.222 detik; sejak percobaan pertama: 20.820 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–5.379 | 5.379 | HTTP 429 pada `api`/`db`. |
| 5.379–15.598 | 10.218 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 15.598–15.671 | 0.073 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 15.671–16.393 | 0.722 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 16.393–17.316 | 0.923 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 17.316–17.325 | 0.009 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 17.325–17.330 | 0.005 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 17.330–17.337 | 0.006 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 17.337–17.354 | 0.017 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 17.354–20.407 | 3.053 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 20.407–20.439 | 0.032 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 20.439–20.820 | 0.381 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=16.422 detik. Runner internal memerlukan 2.971 detik, termasuk lifecycle 0.755 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 17.575–19.745 | 2.170 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 3e2f129c65704950beb69b990eaec3b07bd4e77004635721904a55b6352ea86d. |
| 19.745–20.366 | 0.621 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 3e2f129c65704950beb69b990eaec3b07bd4e77004635721904a55b6352ea86d. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 1, cpp17, attempt `601cdd9b-dfbd-42b1-bd65-a86a504006f0`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 28.641 detik; sejak percobaan pertama: 28.641 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.276 | 0.276 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.276–3.242 | 2.965 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 3.242–3.489 | 0.247 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 3.489–20.705 | 17.216 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 20.705–20.723 | 0.018 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 20.723–21.219 | 0.496 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 21.219–21.273 | 0.054 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 21.273–27.870 | 6.597 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 27.870–27.892 | 0.022 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 27.892–28.641 | 0.749 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=3.400 detik. Runner internal memerlukan 6.460 detik, termasuk lifecycle 2.387 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 21.767–23.736 | 1.969 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 46d15891a4750a97d95217c687f2e00455d307f64e22d43a48433f5200a34df6. |
| 23.736–24.647 | 0.912 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 46d15891a4750a97d95217c687f2e00455d307f64e22d43a48433f5200a34df6. |
| 24.647–25.488 | 0.840 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 46d15891a4750a97d95217c687f2e00455d307f64e22d43a48433f5200a34df6. |
| 25.488–26.378 | 0.890 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 46d15891a4750a97d95217c687f2e00455d307f64e22d43a48433f5200a34df6. |
| 26.378–27.111 | 0.734 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 46d15891a4750a97d95217c687f2e00455d307f64e22d43a48433f5200a34df6. |
| 27.112–27.811 | 0.700 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 46d15891a4750a97d95217c687f2e00455d307f64e22d43a48433f5200a34df6. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 3, cpp17, attempt `de4ea277-d665-4ad9-bdfb-8ccf69cf9db5`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 15.252 detik; sejak percobaan pertama: 43.890 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–5.075 | 5.075 | HTTP 429 pada `api`/`db`. |
| 5.075–28.638 | 23.562 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 28.638–28.804 | 0.167 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 28.804–29.687 | 0.883 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 29.687–30.495 | 0.808 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 30.495–30.502 | 0.006 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 30.502–30.518 | 0.017 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 30.518–38.739 | 8.220 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 38.739–38.795 | 0.056 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 38.795–43.788 | 4.993 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 43.788–43.812 | 0.025 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 43.812–43.890 | 0.078 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=29.709 detik. Runner internal memerlukan 4.891 detik, termasuk lifecycle 1.774 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 39.140–40.765 | 1.625 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: c567e09836e18183e71ad07d22baf8d5fdf9132be71b5705958c10ec823844bc. |
| 40.765–41.347 | 0.582 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: c567e09836e18183e71ad07d22baf8d5fdf9132be71b5705958c10ec823844bc. |
| 41.347–42.085 | 0.738 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: c567e09836e18183e71ad07d22baf8d5fdf9132be71b5705958c10ec823844bc. |
| 42.086–42.690 | 0.605 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: c567e09836e18183e71ad07d22baf8d5fdf9132be71b5705958c10ec823844bc. |
| 42.690–43.235 | 0.545 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: c567e09836e18183e71ad07d22baf8d5fdf9132be71b5705958c10ec823844bc. |
| 43.235–43.757 | 0.522 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: c567e09836e18183e71ad07d22baf8d5fdf9132be71b5705958c10ec823844bc. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 1.765 | 0.535 | 2.213 |
| Dispatcher menunggu worker | 0.037 | 1.435 | 0.039 | 1.727 |
| Pekerjaan menunggu worker | 0.021 | 0.911 | 0.026 | 3.635 |
| Lock admission API | 5.213 | 1.165 | 4.999 | 0.714 |
| Create container | 0.453 | 0.244 | 0.387 | 0.290 |
| Start proses container | 2.044 | 0.869 | 5.475 | 2.785 |
| Remove container | 0.149 | 0.067 | 0.117 | 0.067 |
| Inspeksi Docker | 0.153 | 0.069 | 0.509 | 0.218 |
| Total runner | 6.825 | 3.295 | 16.180 | 8.382 |
| Request → hasil tersimpan | 15.423 | 8.833 | 22.958 | 16.241 |
| Request → hasil terlihat | 16.377 | 9.454 | 23.926 | 16.818 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.382 | 1.284 | -7.1% |
| c17_judge | 3.346 | 3.602 | +7.7% |
| cpp17_run | 1.644 | 1.683 | +2.4% |
| cpp17_judge | 3.759 | 3.984 | +6.0% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 3 sampel; CPU rata-rata 13.6%, maksimum 19.7%; memori available minimum 13.10 GiB.

- single_c17_judge: 4 sampel; CPU rata-rata 16.9%, maksimum 21.1%; memori available minimum 13.08 GiB.

- single_cpp17_run: 4 sampel; CPU rata-rata 12.4%, maksimum 16.1%; memori available minimum 13.08 GiB.

- single_cpp17_judge: 4 sampel; CPU rata-rata 14.5%, maksimum 18.5%; memori available minimum 13.08 GiB.

- run_30: 21 sampel; CPU rata-rata 57.3%, maksimum 81.2%; memori available minimum 12.85 GiB.

- submit_30: 43 sampel; CPU rata-rata 60.1%, maksimum 78.3%; memori available minimum 12.83 GiB.

## Analisis hambatan

- run_30: antre worker rata-rata 0.911 detik; runner 3.295 detik; menunggu lock admission rata-rata 1.165 detik, maksimum 5.156 detik. Lifecycle create/start/remove 1.179 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.166 detik, P95 0.474 detik; health check total 0.141 detik per request.
- submit_30: antre worker rata-rata 3.635 detik; runner 8.382 detik; menunggu lock admission rata-rata 0.714 detik, maksimum 1.147 detik. Lifecycle create/start/remove 3.143 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.108 detik, P95 0.473 detik; health check total 0.168 detik per request.

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
