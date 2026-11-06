# Profil waktu Run dan Submit — konfigurasi 50 worker / 50 slot runner

Pengujian baru: `perf_fcf93757fd`, direktori `judging-profile-20261104-103741-bdae8f`. Mulai 4 November 2026 pukul 10:39:33 WIB (03:39:33 UTC). Laporan/data pengujian lama dipertahankan.

**Antrean dispatcher/worker berhasil dipangkas, tetapi waktu tunggu berpindah ke penerimaan API dan pemrosesan Docker/sandbox. Target 5–7 detik belum tercapai.** Rata-rata request sampai hasil terlihat: Run 19,344 detik, Submit 28,066 detik. Angka Submit tersebut dihitung dari request yang diterima; bila mencakup 429 dan retry alat uji, rata-rata menjadi 39,948 detik dan maksimum 53,900 detik.

## Lingkungan dan metode

- Docker: 12 vCPU, 15.52 GiB RAM.
- Worker eksekusi aktual: [(50, 50)] (concurrency, jumlah proses). Runner: **50 slot** dalam satu container pengendali.
- Scheduler: **1.0 detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.
- Batas pending kelas tetap **20** dan batas per jam tetap 200. Angka 50 adalah kapasitas terkonfigurasi, bukan bukti 50 eksekusi aktif; uji memakai 30 siswa pada satu kelas.
- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.
- Kode kompilasi/eksekusi nyata. Run memakai 2 sandbox, Submit 6 sandbox berurutan per pekerjaan. Sandbox tetap dibuat/dihapus per fase; belum menerapkan sandbox per pengguna.
- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.
- Fixture: `perf_fcf93757fd`. Nama kelas: `Performance 30 users perf_fcf93757fd`. Identitas peserta/pekerjaan tersimpan di hasil mentah.

## Hasil dan waktu pengguna

| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |
|---|---|---|---:|---:|
| single_c17_run | {'202': 1} | {'EXECUTED': 1} | 3.262 dtk | 0 |
| single_c17_judge | {'202': 1} | {'ACCEPTED': 1} | 5.262 dtk | 0 |
| single_cpp17_run | {'202': 1} | {'EXECUTED': 1} | 3.235 dtk | 0 |
| single_cpp17_judge | {'202': 1} | {'ACCEPTED': 1} | 6.362 dtk | 0 |
| run_30 | {'202': 30} | {'EXECUTED': 30} | 26.480 dtk | 0 |
| submit_30 | {'429': 10, '202': 20} | {'ACCEPTED': 30} | 53.923 dtk | 0 |

Status harness: **completed**. Anomali: **0**. Puncak sampling: `{'queued': 11, 'running': 20, 'retry_pending': 0, 'own_pending': 20, 'external_pending': 0}`.
Trace: 10845 rekaman; 64/64 pekerjaan berhasil dihubungkan. Masalah analisis: `[]`. Error span: `{'HTTPException': 10}`.

Catatan timestamp: `[{'attempt_id': 'd4538d13-b453-472a-b79c-cc0647f2235d', 'type': 'commit_observed_after_publication', 'overlap_ms': 8.153701}, {'attempt_id': '445302ea-ca6e-476a-88c5-4a354756bbdb', 'type': 'commit_observed_after_publication', 'overlap_ms': 27.440653}]`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.

## Waktu pada setiap tahap dan jalur container

Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |
|---|---:|---:|---:|---:|---|
| Request → awal handler API | 0.337 | 0.419 | 0.184 | 0.305 | Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| API → commit pekerjaan | 7.554 | 19.945 | 1.083 | 4.223 | `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| Menunggu pemicu scheduler | 0.384 | 0.863 | 0.448 | 0.900 | Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| Dispatcher menunggu worker | 0.038 | 0.081 | 0.020 | 0.055 | Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| Dispatcher memublikasikan pekerjaan | 0.021 | 0.085 | 0.023 | 0.056 | Dispatcher di `worker` → `db` dan `redis`. |
| Pekerjaan menunggu worker eksekusi | 0.028 | 0.051 | 0.014 | 0.032 | Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| Worker claim/load | 0.134 | 0.498 | 0.114 | 0.662 | `worker` → `db`: klaim lease, muat source/test case. |
| Worker memanggil runner | 8.423 | 12.624 | 25.231 | 32.026 | `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| Worker validasi/simpan hasil | 1.539 | 3.657 | 0.161 | 0.876 | `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| Polling melihat hasil | 0.887 | 1.893 | 0.789 | 1.734 | Jeda polling + klien uji → `api` → `db` → klien. |
| **Total request diterima server → hasil tersimpan** | 18.457 | 25.555 | 27.277 | 35.048 | Total sebelum polling; bukan tahap tambahan. |
| **Total request → hasil terlihat klien** | 19.344 | 26.352 | 28.066 | 35.627 | Total seluruh jalur di atas; bukan tahap tambahan. |
| Subtotal outbox | 0.442 | 0.952 | 0.490 | 0.971 | Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi. |
| Di dalam runner | 8.024 | 12.021 | 24.991 | 31.903 | Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner. |

Nama container layanan: `judgementsystem-<service>-1`. Sandbox: `js-<attempt_id>-compile` dan `js-<attempt_id>-run`; nama runtime dipakai ulang sesudah kasus sebelumnya dihapus. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.

## Biaya di dalam runner

Detik rata-rata per pekerjaan; agregat 2 container Run / 6 container Submit. Baris subtotal dan diagnostik saling tumpang tindih.

| Bagian | Run | Submit | Jalur container / arti pengukuran |
|---|---:|---:|---|
| Create | 1.233327 | 4.177057 | `runner` → Docker Engine: membuat sandbox. |
| Start | 2.246092 | 7.979238 | `runner` → Docker Engine → proses sandbox. |
| Remove | 0.355175 | 1.301423 | `runner` → Docker Engine: menghapus sandbox. |
| Subtotal create/start/remove | 3.834594 | 13.457718 | Gabungan tiga baris di atas. |
| Siapkan stdin | 0.152130 | 0.624195 | `runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi. |
| Siapkan output | 0.373788 | 1.476319 | `runner` → Docker Engine → stream sandbox; hanya penyiapan stream. |
| Inspect | 2.721723 | 7.203429 | `runner` → Docker Engine: memeriksa status sandbox. |
| Wait | 0.161622 | 0.586736 | `runner` → Docker Engine: status akhir sandbox. |
| Kontrol/I/O/tidur/waktu lain | 0.779783 | 1.631288 | Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus. |
| Total runner | 8.024326 | 24.990616 | Seluruh pemrosesan pengendali dan sandbox. |
| Compiler wall (diagnostik) | 1.143230 | 1.423289 | Compiler di sandbox; tumpang tindih dengan total, bukan tambahan. |
| Compiler CPU (diagnostik) | 0.854089 | 0.955192 | CPU child compiler di sandbox. |
| PID1 runtime (diagnostik) | 1.698641 | 9.112300 | Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program. |
| Pemeriksaan output | 0.000000 | 0.000114 | Perbandingan token di `runner`, di luar sandbox. |

## Timeline terburuk dari pekerjaan nyata

Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama.

### run_30: terlama sejak request yang diterima

Peserta indeks 29, cpp17, attempt `14eed738-b10e-430b-9d20-61d59e1a2b2e`. HTTP: `[202]`. Hasil `EXECUTED`. Waktu sejak request diterima: 26.425 detik; sejak percobaan pertama: 26.425 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.420 | 0.420 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.420–20.671 | 20.251 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 20.671–20.856 | 0.185 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 20.856–20.903 | 0.047 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 20.903–20.910 | 0.007 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 20.910–20.939 | 0.029 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 20.939–20.975 | 0.036 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 20.975–25.872 | 4.897 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 25.872–25.883 | 0.011 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 25.883–26.425 | 0.541 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=20.774 detik. Runner internal memerlukan 4.685 detik, termasuk lifecycle 1.846 detik; angka ini berada di dalam langkah HTTP runner.

Rincian di dalam langkah runner (bukan tambahan): sandbox kompilasi pada t=21,170–25,035, durasi 3,865 detik; sandbox program pada t=25,035–25,855, durasi 0,819 detik. Setiap interval mencakup lifecycle, input/output, menunggu proses, dan cleanup, bukan waktu CPU murni program.

### submit_30: terlama sejak request yang diterima

Peserta indeks 13, cpp17, attempt `cffde47d-7aec-4f05-a496-1fbebc1a6b66`. HTTP: `[202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 35.643 detik; sejak percobaan pertama: 35.643 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–0.298 | 0.298 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 0.298–4.521 | 4.223 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 4.521–4.521 | 0.000 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 4.521–4.555 | 0.034 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 4.555–4.611 | 0.056 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 4.611–4.636 | 0.025 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 4.636–5.619 | 0.984 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 5.619–33.898 | 28.279 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 33.898–35.048 | 1.150 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 35.048–35.643 | 0.595 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=4.874 detik. Runner internal memerlukan 27.477 detik, termasuk lifecycle 14.326 detik; angka ini berada di dalam langkah HTTP runner.

Rincian sandbox berikut berada di dalam langkah HTTP runner, bukan tahap tambahan. Batas span berasal dari timestamp wall clock dan durasi monotonic; terdapat ketidakselarasan sekitar 5 ms pada batas kasus 4/5. Urutan kasus dalam kode tetap serial; tabel tidak membuktikan kasus tersebut berjalan paralel.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |
|---:|---:|---|
| 6,385–15,110 | 8,725 | Kompilasi. |
| 15,110–19,420 | 4,309 | Program kasus 1. |
| 19,420–23,607 | 4,187 | Program kasus 2. |
| 23,608–28,360 | 4,752 | Program kasus 3. |
| 28,360–31,602 | 3,242 | Program kasus 4. |
| 31,597–33,857 | 2,260 | Program kasus 5. |

Interval ini mencakup create/start, input/output, menunggu compiler/program, dan cleanup. Sebagai contoh, 8,725 detik fase kompilasi bukan durasi CPU compiler selama 8,725 detik.

### submit_30: terlama sejak percobaan pertama

Peserta indeks 11, cpp17, attempt `3fa3bab1-ad16-4d11-86c4-591da546101a`. HTTP: `[429, 202]`. Hasil `ACCEPTED`. Waktu sejak request diterima: 18.248 detik; sejak percobaan pertama: 53.900 detik.

| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |
|---:|---:|---|
| 0.000–12.567 | 12.567 | HTTP 429 pada `api`/`db`. |
| 12.567–35.652 | 23.085 | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |
| 35.652–35.762 | 0.110 | Request → awal handler API: Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler. |
| 35.762–36.755 | 0.993 | API → commit pekerjaan: `api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`. |
| 36.755–37.574 | 0.820 | Menunggu pemicu scheduler: Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba. |
| 37.574–37.623 | 0.049 | Dispatcher menunggu worker: Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat. |
| 37.623–37.633 | 0.009 | Dispatcher memublikasikan pekerjaan: Dispatcher di `worker` → `db` dan `redis`. |
| 37.633–37.640 | 0.008 | Pekerjaan menunggu worker eksekusi: Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat. |
| 37.640–37.681 | 0.041 | Worker claim/load: `worker` → `db`: klaim lease, muat source/test case. |
| 37.681–52.962 | 15.280 | Worker memanggil runner: `worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP. |
| 52.962–52.980 | 0.019 | Worker validasi/simpan hasil: `worker` → `db`; sandbox telah dibersihkan oleh runner. |
| 52.980–53.900 | 0.920 | Polling melihat hasil: Jeda polling + klien uji → `api` → `db` → klien. |

Respons HTTP 202 tiba pada t=36.778 detik. Runner internal memerlukan 15.136 detik, termasuk lifecycle 7.769 detik; angka ini berada di dalam langkah HTTP runner.

## Perbandingan dengan konfigurasi lama

Pembanding: [judging-profile-20261104-093052-80dbc2](../judging-profile-20261104-093052-80dbc2/LAPORAN_DETAIL_RUN_SUBMIT.md): 2 proses worker, 3 slot runner, scheduler 5 detik. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.

| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |
|---|---:|---:|---:|---:|
| outbox_wait_ms | 2.894 | 0.442 | 11.918 | 0.490 |
| dispatcher_wait_after_commit_ms | 0.007 | 0.038 | 9.496 | 0.020 |
| broker_worker_wait_ms | 9.471 | 0.028 | 11.716 | 0.014 |
| runner_total_ms | 2.388 | 8.024 | 6.012 | 24.991 |
| request_to_db_ready_ms | 15.883 | 18.457 | 31.040 | 27.277 |
| client_observed_ms | 16.458 | 19.344 | 31.541 | 28.066 |

## Kontrol pengaruh profiler

RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.

| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |
|---|---:|---:|---:|
| c17_run | 1.483 | 1.371 | -7.5% |
| c17_judge | 4.495 | 4.127 | -8.2% |
| cpp17_run | 2.078 | 1.979 | -4.8% |
| cpp17_judge | 4.868 | 4.483 | -7.9% |

## Sumber daya host Docker

Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container.

- single_c17_run: 3 sampel; CPU rata-rata 13.2%, maksimum 15.6%; memori available minimum 11.55 GiB.

- single_c17_judge: 6 sampel; CPU rata-rata 17.3%, maksimum 23.0%; memori available minimum 11.53 GiB.

- single_cpp17_run: 3 sampel; CPU rata-rata 22.4%, maksimum 26.5%; memori available minimum 11.53 GiB.

- single_cpp17_judge: 6 sampel; CPU rata-rata 18.9%, maksimum 22.4%; memori available minimum 11.54 GiB.

- run_30: 26 sampel; CPU rata-rata 76.4%, maksimum 91.4%; memori available minimum 11.15 GiB.

- submit_30: 53 sampel; CPU rata-rata 74.6%, maksimum 95.3%; memori available minimum 10.84 GiB.

## Anomali, validasi, dan batas kesimpulan

### Analisis hambatan pada konfigurasi baru

1. **Antrean bukan lagi biaya dominan.** Rata-rata waktu pesan eksekusi menunggu worker turun dari 9,471 menjadi 0,028 detik untuk Run, dan 11,716 menjadi 0,014 detik untuk Submit. Dispatcher pada Submit turun dari 9,496 menjadi 0,020 detik. Interval scheduler rata-rata teramati di bawah setengah detik. Jadi, perubahan concurrency dan scheduler bekerja pada bagian yang ditargetkan.
2. **Pemrosesan runner menjadi jauh lebih lambat saat burst.** Rata-rata Run naik dari 2,388 menjadi 8,024 detik; Submit naik dari 6,012 menjadi 24,991 detik. Runner kini menyumbang sekitar 91,6% waktu request sampai hasil tersimpan pada Submit. Biaya lifecycle create/start/remove Submit naik dari 2,642 menjadi 13,458 detik, ditambah inspeksi Docker 7,203 detik. Gabungan lifecycle dan inspeksi sekitar 82,7% waktu runner. Ini mendukung adanya kontensi pada jalur Docker/host saat banyak sandbox aktif; bukan bukti bahwa seluruh selisih berasal dari CPU program siswa.
3. **Penerimaan API juga mengalami antrean lock.** Saat burst Run, lock admission rata-rata 6,856 detik, P95 19,359 detik, maksimum 19,918 detik. API sampai commit rata-rata 7,554 detik dan maksimum 20,251 detik. Lock `QuotaLock(id="admission")` pada `app/main.py` berlaku global, bukan per pengguna. Di dalam transaksi tersebut terdapat pengecekan akses/kuota dan health check provider. Health check rata-rata 0,316 detik pada Run, maksimum 1,001 detik. Pemisahan rinci SQL/penjadwalan CPU di luar span yang ada belum diukur. Sebanyak 30 Run akhirnya diterima karena pekerjaan lebih awal dapat selesai selagi request berikutnya masih menunggu admission; ini tidak berarti batas pending 20 dihapus.
4. **Respons aplikasi ikut melambat saat burst.** Polling hasil tetap HTTP 200, tetapi median 0,791 detik, P95 3,039 detik, maksimum 7,376 detik. Probe `/my/learning` median 0,171 detik, P95 3,587 detik, maksimum 5,769 detik. Jadi, menambah concurrency tidak hanya memengaruhi compiler; jalur pengambilan hasil juga terpengaruh.
5. **CPU terpakai tinggi, tanpa tanda kekurangan RAM pada sampling ini.** CPU VM Docker mencapai 91,4% pada Run dan 95,3% pada Submit; memori available minimum 10,84 GiB. Ini bukan pengukuran CPU per container atau bukti penyebab tunggal. Tidak ada kegagalan eksekusi/kehabisan memori yang tercatat pada pekerjaan uji.
6. **Ada peringatan cleanup meskipun penilaian berhasil.** Snapshot [log profiling](service-profile.log) mencatat 10 `Sandbox cleanup error: NotFound`. Snapshot diambil sebelum akhir seluruh fase sehingga jumlah tersebut bukan hitungan lengkap seluruh interval profiling. Sesuai jalur `cleanup_expired`, Docker SDK dapat menginspeksi container yang sudah dihapus oleh eksekusi lain saat enumerasi berlangsung. Ini merupakan dugaan penyebab dari pembacaan kode; tidak ada traceback penuh yang membuktikan sumber setiap peringatan. Setelah pengujian tidak ada container berlabel sandbox yang tersisa. Tidak ada kegagalan job atau retry eksekusi yang berkorelasi dengan peringatan tersebut.

Kesimpulannya, 50 proses/slot mengatasi antrean worker pada skenario ini, tetapi **belum memberi latensi rendah**. Durasi fase Run turun 47,318 → 26,480 detik dan Submit 97,357 → 53,923 detik dibanding uji detail sebelumnya, sementara rata-rata Run dari request yang diterima justru memburuk 16,458 → 19,344 detik. Perbandingan durasi fase mencakup perbedaan jumlah penolakan 429 dan retry terkontrol, sehingga bukan perbandingan waktu eksekusi murni.

Langkah berikut yang disarankan adalah mengkalibrasi concurrency pada beberapa tingkat dengan fixture yang sama, serta memeriksa lock admission dan biaya lifecycle/inspeksi Docker. Belum ada perubahan optimasi lanjutan yang diterapkan setelah benchmark ini.

### Validasi dan pembersihan

- Anomali harness: `[]`.
- Pemulihan fixture: `{'class_deleted': True, 'test_accounts_disabled': 30}`. Akun dinonaktifkan, bukan dihapus; akun/kelas lama tidak dihapus.
- Jumlah delivery worker teramati 64 untuk 64 pekerjaan API; cek retry dan trace sebelum menafsirkan delivery tambahan sebagai eksekusi ganda.
- Seluruh 30 peserta mencapai progres/nilai 100. Seluruh 32 Run menghasilkan Executed dan 32 Submit menghasilkan Accepted; tidak ada salah output/nilai, kebocoran rincian kasus privat, kegagalan eksekusi, atau retry eksekusi yang ditemukan oleh harness. Sepuluh error span HTTPException adalah penolakan admission 429.
- Image aplikasi baru berisi scheduler 1 detik dan perbaikan batas runner: cap internal 4 slot dihapus agar `RUNNER_SLOTS=50` dihormati; thread pool AnyIO juga menyediakan sedikitnya 50 thread untuk endpoint sinkron. Tanpa perbaikan ini, perubahan Compose saja belum menghasilkan 50 slot yang dapat digunakan.
- Analisis otomatis pertama berhenti karena dua interval outbox negatif dari observasi hook commit yang terlambat. Setelah keterbatasan tersebut dicatat dan batas interval ditangani eksplisit, analisis ulang data yang sama berhasil 64/64 dengan pemeriksaan jumlah jalur tetap konsisten. Burst pengguna tidak diulang; raw trace dipertahankan.
- Konfigurasi normal tanpa profiler dipulihkan setelah pengujian: worker tetap 50 proses, runner 50 slot, scheduler 1 detik, sandbox image reguler. Ini pemulihan dari instrumentasi sementara, bukan pengembalian ke konfigurasi lama 2/3/5. Kelas/akun fixture dibersihkan; layanan berjalan dan tidak ada sandbox tersisa. Pemeriksaan artefak tidak menemukan nilai password/token/secret yang terkonfigurasi di `.env`.
- Self-check profiler dan regresi kapasitas runner dijalankan sebelum burst. Trace memakai metadata eksplisit dan tidak mencatat source, input, password, atau token.
- Pengujian hanya satu host, satu soal sederhana, burst 30 pengguna dan kuota pending 20; belum membuktikan kapasitas 50 program aktif, beban berkelanjutan, fault injection, atau target 5–7 detik pada soal lain.
- Selesainya seluruh pekerjaan setelah retry admission tidak berarti seluruh burst awal diterima. Waktu sejak percobaan pertama mencakup jeda retry alat uji.

## Berkas dan pengulangan

[Hasil HTTP/jobs](results.json), [analisis tahap](stage-analysis.json), [CSV pekerjaan](job-stages.csv), [CSV container](container-stages.csv), [requests](requests.csv), [antrean](queue.csv), [trace](traces/), [konfigurasi aktual worker](runtime-config.json), [slot runner](runner-runtime.json), [lingkungan/image](environment.json).

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Wrapper membaca command worker dari Compose, sehingga tidak memaksa concurrency lama. Build dan aktifkan konfigurasi yang hendak diuji terlebih dahulu. Wrapper memverifikasi kapasitas aktual, memasang profiling sementara, lalu mengembalikan command/image tanpa profiling di `finally`. Proses PowerShell yang dihentikan paksa tetap perlu pemulihan manual. Setiap pengulangan menghasilkan direktori baru.
