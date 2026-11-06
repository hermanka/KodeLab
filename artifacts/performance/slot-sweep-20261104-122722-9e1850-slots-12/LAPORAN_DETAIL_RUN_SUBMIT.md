# Profil waktu Run dan Submit — konfigurasi 12 worker / 12 slot runner

Pengujian baru: `perf_40391ddce1`. Mulai UTC: 2026-11-04T06:46:06.773371+00:00. Laporan/data pengujian lama dipertahankan.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(12, 12)] (concurrency, jumlah proses). Runner: **12 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: [1]. Fase kompilasi/input terukur: [2, 6]. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_40391ddce1`. Nama kelas: `Performance 30 users perf_40391ddce1`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.363 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.394 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.258 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 6.347 dtk | 0 |
| run_30 | {'202': 25, '429': 5} | {'EXECUTED': 30} | 25.625 dtk | 0 |
| submit_30 | {'202': 20, '429': 10} | {'ACCEPTED': 30} | 54.365 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 14, 'running': 12, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 9603 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 15}`.

Catatan timestamp: `[]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.353 | 0.562 | 0.300 | 0.536 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 3.490 | 11.770 | 1.899 | 3.139 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.344 | 0.823 | 0.454 | 0.946 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 1.566 | 4.878 | 2.172 | 16.294 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.036 | 0.090 | 0.030 | 0.120 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 0.656 | 2.990 | 2.176 | 17.016 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.043 | 0.079 | 0.073 | 0.138 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 5.836 | 8.445 | 15.894 | 19.861 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 0.764 | 2.323 | 0.086 | 0.162 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.763 | 1.725 | 0.941 | 2.588 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 13.086 | 19.629 | 23.084 | 34.868 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 13.850 | 20.246 | 24.025 | 35.800 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 1.946 | 5.750 | 2.656 | 17.156 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 5.595 | 8.051 | 15.721 | 19.708 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 0.389043 | 0.384706 | `runner` → Docker Engine: membuat sandbox. |
| Start | 1.538675 | 5.768714 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.106438 | 0.106015 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 2.034155 | 6.259435 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.108996 | 0.326276 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.197650 | 0.617378 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 0.115354 | 0.434437 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 2.922784 | 7.357089 | `runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker. |
| Atur batas memori | 0.177351 | 0.611814 | `runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang. |
| Kontrol/I/O/tidur/waktu lain | 0.034533 | 0.112331 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 5.594833 | 15.720680 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 0.992340 | 0.997517 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.768953 | 0.797214 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 1.271920 | 7.264984 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000025 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 24, c17, attempt `37fc18dc-697a-4c64-b153-8f9522b3f13b`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 20.459 detik; sejak percobaan pertama: 20.459 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–1.162 | 1.162 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 1.162–12.932 | 11.770 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 12.932–12.932 | 0.000 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 12.932–16.017 | 3.084 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 16.017–16.032 | 0.015 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 16.032–16.319 | 0.287 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 16.319–16.379 | 0.060 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 16.379–19.864 | 3.485 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 19.864–19.880 | 0.016 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 19.880–20.459 | 0.579 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=13.134 detik. Runner internal memerlukan 3.288 detik, termasuk lifecycle 1.468 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 16.793–18.756 | 1.963 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 6f99c72632f9fc0bd01f515e7472ac0d04a74ca8c1857c81847f54d729af9e91. |
| 18.758–19.826 | 1.068 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 6f99c72632f9fc0bd01f515e7472ac0d04a74ca8c1857c81847f54d729af9e91. |

### run_30: terlama sejak percobaan pertama

Peserta indeks 19, cpp17, attempt `bc15a168-fed6-46c6-ad01-3a7162022329`. HTTP: `[429, 202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 5.113 detik; sejak percobaan pertama: 25.584 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–8.503 | 8.503 | HTTP 429 pada `api`/`db`. |
| 8.503–20.471 | 11.969 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 20.471–20.567 | 0.096 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 20.567–21.108 | 0.540 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 21.108–21.702 | 0.595 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 21.702–21.708 | 0.005 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 21.708–21.716 | 0.008 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 21.716–21.719 | 0.003 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 21.719–21.735 | 0.016 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 21.735–25.268 | 3.533 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 25.268–25.298 | 0.030 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 25.298–25.584 | 0.286 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=21.119 detik. Runner internal memerlukan 3.457 detik, termasuk lifecycle 1.017 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 22.010–24.229 | 2.219 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 9b6dabeac5aa11afc3feaee09c779aeb98896dfbf7cf9660ff7afdbc3ff11bc7. |
| 24.229–25.197 | 0.968 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 9b6dabeac5aa11afc3feaee09c779aeb98896dfbf7cf9660ff7afdbc3ff11bc7. |

### submit_30: terlama sejak request yang diterima

Peserta indeks 9, cpp17, attempt `fa799620-fcb8-4617-9497-a7336ae5f105`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 35.873 detik; sejak percobaan pertama: 35.873 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.420 | 0.420 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.420–2.955 | 2.536 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 2.955–3.104 | 0.149 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 3.104–3.117 | 0.012 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 3.117–3.167 | 0.050 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 3.167–20.220 | 17.053 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 20.220–20.318 | 0.098 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 20.318–34.773 | 14.455 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 34.773–34.830 | 0.057 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 34.830–35.873 | 1.043 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=2.988 detik. Runner internal memerlukan 14.253 detik, termasuk lifecycle 4.976 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 20.887–25.294 | 4.407 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: 29447b1a636520a2cea0b7d1708a7fbddd7f599ffe872ae9a30a47444778347a. |
| 25.294–27.355 | 2.060 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: 29447b1a636520a2cea0b7d1708a7fbddd7f599ffe872ae9a30a47444778347a. |
| 27.353–29.267 | 1.913 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: 29447b1a636520a2cea0b7d1708a7fbddd7f599ffe872ae9a30a47444778347a. |
| 29.267–31.429 | 2.162 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: 29447b1a636520a2cea0b7d1708a7fbddd7f599ffe872ae9a30a47444778347a. |
| 31.429–33.168 | 1.738 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: 29447b1a636520a2cea0b7d1708a7fbddd7f599ffe872ae9a30a47444778347a. |
| 33.168–34.665 | 1.498 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: 29447b1a636520a2cea0b7d1708a7fbddd7f599ffe872ae9a30a47444778347a. |

### submit_30: terlama sejak percobaan pertama

Peserta indeks 27, cpp17, attempt `d62169fa-b8fb-43d7-8794-fcea97cfd6c0`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 18.460 detik; sejak percobaan pertama: 54.319 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–6.375 | 6.375 | HTTP 429 pada `api`/`db`. |
| 6.375–35.859 | 29.484 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 35.859–36.088 | 0.229 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 36.088–37.323 | 1.235 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 37.323–38.187 | 0.863 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 38.187–38.197 | 0.010 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 38.197–38.205 | 0.008 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 38.205–38.209 | 0.005 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 38.209–38.263 | 0.054 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 38.263–53.810 | 15.547 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 53.810–53.847 | 0.037 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 53.847–54.319 | 0.472 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=37.349 detik. Runner internal memerlukan 15.392 detik, termasuk lifecycle 5.859 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 38.722–42.691 | 3.968 | compile, input 0: penyiapan/start, input/output, menunggu proses. ID container: d2fb07d40fba3c08fffded4a9288e0921c89a495b0fc267499542a3040af6f64. |
| 42.691–45.251 | 2.560 | run, input 1: penyiapan/start, input/output, menunggu proses. ID container: d2fb07d40fba3c08fffded4a9288e0921c89a495b0fc267499542a3040af6f64. |
| 45.251–47.702 | 2.450 | run, input 2: penyiapan/start, input/output, menunggu proses. ID container: d2fb07d40fba3c08fffded4a9288e0921c89a495b0fc267499542a3040af6f64. |
| 47.702–50.375 | 2.673 | run, input 3: penyiapan/start, input/output, menunggu proses. ID container: d2fb07d40fba3c08fffded4a9288e0921c89a495b0fc267499542a3040af6f64. |
| 50.375–52.739 | 2.364 | run, input 4: penyiapan/start, input/output, menunggu proses. ID container: d2fb07d40fba3c08fffded4a9288e0921c89a495b0fc267499542a3040af6f64. |
| 52.743–53.767 | 1.024 | run, input 5: penyiapan/start, input/output, menunggu proses. ID container: d2fb07d40fba3c08fffded4a9288e0921c89a495b0fc267499542a3040af6f64. |

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-112759-70e705](../judging-profile-20261104-112759-70e705/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| Outbox | 0.441 | 1.946 | 0.535 | 2.656 |
| Dispatcher menunggu worker | 0.037 | 1.566 | 0.039 | 2.172 |
| Pekerjaan menunggu worker | 0.021 | 0.656 | 0.026 | 2.176 |
| Lock admission API | 5.213 | 2.203 | 4.999 | 0.918 |
| Create container | 0.453 | 0.389 | 0.387 | 0.385 |
| Start proses container | 2.044 | 1.539 | 5.475 | 5.769 |
| Remove container | 0.149 | 0.106 | 0.117 | 0.106 |
| Inspeksi Docker | 0.153 | 0.115 | 0.509 | 0.434 |
| Total runner | 6.825 | 5.595 | 16.180 | 15.721 |
| Request → hasil tersimpan | 15.423 | 13.086 | 22.958 | 23.084 |
| Request → hasil terlihat | 16.377 | 13.849 | 23.926 | 24.025 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.481 | 1.421 | -4.0% |
| c17_judge | 3.410 | 3.753 | +10.1% |
| cpp17_run | 1.673 | 1.830 | +9.3% |
| cpp17_judge | 3.995 | 3.994 | -0.0% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 3 sampel; CPU rata-rata 11.3%, maksimum 17.2%; memori available minimum 12.92 GiB.

- single_c17_judge: 5 sampel; CPU rata-rata 16.6%, maksimum 24.0%; memori available minimum 12.90 GiB.

- single_cpp17_run: 4 sampel; CPU rata-rata 16.8%, maksimum 26.0%; memori available minimum 12.90 GiB.

- single_cpp17_judge: 6 sampel; CPU rata-rata 15.2%, maksimum 20.3%; memori available minimum 12.89 GiB.

- run_30: 26 sampel; CPU rata-rata 62.9%, maksimum 89.5%; memori available minimum 12.56 GiB.

- submit_30: 53 sampel; CPU rata-rata 67.6%, maksimum 89.4%; memori available minimum 12.47 GiB.

## Analisis hambatan

- run_30: antre worker rata-rata 0.656 detik; runner 5.595 detik; menunggu lock admission rata-rata 2.203 detik, maksimum 10.163 detik. Lifecycle create/start/remove 2.034 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.270 detik, P95 1.143 detik; health check total 0.180 detik per request.
- submit_30: antre worker rata-rata 2.176 detik; runner 15.721 detik; menunggu lock admission rata-rata 0.918 detik, maksimum 1.943 detik. Lifecycle create/start/remove 6.259 detik berada di dalam runner.
  Waktu lock dipegang sampai observasi commit: rata-rata 0.138 detik, P95 0.641 detik; health check total 0.159 detik per request.

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
