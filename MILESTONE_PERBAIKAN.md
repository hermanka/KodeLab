# Milestone perbaikan audit Ponytail (6 November 2026)

Dokumen ini membagi temuan audit Ponytail menjadi empat milestone. Urutannya dari yang paling penting. Sebuah milestone dianggap selesai bila semua kriteria selesainya terpenuhi dan hasil pengujiannya dicatat di [VERIFIKASI.md](VERIFIKASI.md).

Beban acuan: satu sesi lab berisi 30–60 siswa yang menekan Run atau Submit hampir bersamaan pada satu host Docker. Skenario ini sama dengan `scripts/load-concurrent.py`.

| Milestone | Isi | Sifat |
|---|---|---|
| [M1](#m1--penilaian-tetap-benar-saat-ramai) | Penilaian tetap benar saat ramai | **Wajib**, penghambat sesi lab |
| [M2](#m2--siap-dibuka-untuk-satu-kelas) | Siap dibuka untuk satu kelas | **Wajib** sebelum ada akses dari luar localhost |
| [M3](#m3--perampingan-kode) | Perampingan kode | Sebaiknya |
| [M4](#m4--performa-dan-kerapian) | Performa dan kerapian | Opsional |
| [M5](#m5--run-dan-submit-lebih-cepat) | Run dan Submit lebih cepat | **Prioritas** untuk 11–12 pengguna serentak |

---

## M1 — Penilaian tetap benar saat ramai

**Status:** kode selesai pada 6 November 2026. Uji beban 30 pengguna pada stack lengkap belum dijalankan (lihat bagian *Belum diverifikasi*).

**Tujuan:** saat semua slot penuh, siswa tidak menerima error 503 secara acak, dan program yang benar tidak divonis TLE.

### M1.1 Hentikan pemeriksaan `/health` pada setiap permintaan

**Masalah:** runner hanya memiliki 50 thread, sama dengan jumlah slot. Ketika semua slot terpakai, `/health` harus menunggu thread kosong. Endpoint Submit, Validasi, dan Publikasi memanggil `/health` dengan batas waktu 3 detik, sehingga ketiganya gagal dengan 503 saat ramai. Pada Validasi dan Publikasi, panggilan ini dilakukan sambil memegang lock admission global.

- [x] `create_submission` tidak lagi memanggil runner. Fase preflight (baca, rollback, cek health, lalu baca ulang) dihapus seluruhnya karena hanya ada untuk panggilan jaringan tersebut ([app/main.py](app/main.py)).
- [x] `validate_problem` dan `publish_problem` tidak lagi memanggil `health_check()` ([app/content.py](app/content.py)).
- [x] Runner mendapat 4 thread cadangan: `slot_count + 4` ([runner/main.py](runner/main.py)).
- [x] Uji `test_health_answers_while_every_slot_is_busy` ([tests/test_runner_capacity.py](tests/test_runner_capacity.py)) gagal pada kode lama ("health starved") dan lulus pada kode baru.
- [x] Enam tes preflight di `tests/test_admission.py` dan satu di `tests/test_mariadb_concurrency.py` dihapus karena perilaku yang diujinya sudah tidak ada. Sebagai gantinya ditambahkan uji "runner offline tetap diterima 202".

### M1.2 TLE palsu saat ramai

**Masalah awal:** batas waktu memakai jam dinding (wall-clock), dan ada 50 sandbox untuk 12 thread CPU.

**Hasil pengukuran** (laptop i7-9750H: 6 core fisik / 12 thread; program C yang memakai sekitar 1,4 detik CPU saat sendirian; batas 2 detik):

| Konfigurasi | TLE palsu |
|---|---:|
| Jam dinding, 50 paralel | 45 / 50 |
| Jam dinding, 12 paralel | 43 / 50 |
| Jam dinding, 8 paralel | 31 / 50 |
| Jam dinding, 4 paralel | 0 / 24 (median 2,18 s, di tepi batas) |
| Waktu CPU, 8 paralel | 44 / 50 |

Mengurangi slot saja ternyata tidak cukup. **Waktu CPU program yang sama juga naik saat paralel**: 1,37 s sendirian → sekitar 1,8 s pada 4 paralel → sekitar 2,4 s pada 6–8 paralel, karena hyperthreading dan turbo clock yang turun. Batas apa pun akan gagal bila program sudah dekat batasnya, jadi perlu ruang aman (margin) yang dijamin sejak validasi.

- [x] Batas waktu menjadi **waktu CPU** (`RLIMIT_CPU`, soft = hard, sehingga kernel mengirim SIGKILL yang tidak bisa diabaikan oleh PID 1) di [sandbox/entrypoint.py](sandbox/entrypoint.py). Jam dinding tetap ada sebagai pengaman sebesar 3 × batas + 2 s untuk program yang tidur atau macet. Exit 137 tanpa OOM dipetakan ke TLE ([runner/engine.py](runner/engine.py)).
- [x] Image sandbox naik ke `gcc12-v3`, karena runner baru dengan image lama akan berjalan tanpa batas CPU.
- [x] Validasi menjalankan solusi acuan dengan **separuh batas waktu**, minimal 1 s ([app/tasks.py](app/tasks.py)), dan diuji di `test_reference_validation_runs_with_half_the_time_limit`.
- [x] Kapasitas diubah menjadi 6 worker dan 7 slot runner (6 + 1 validator, sesuai 6 core fisik) di [compose.yaml](compose.yaml).
- [x] Pengujian ulang: program 0,8 s CPU (dalam margin), 50 job pada 7 paralel → **0 TLE**. Program 1,1 s CPU (di luar margin) ditolak oleh validasi separuh batas (TLE pada batas 1 s), sedangkan program 0,8 s diterima.
- [x] Dokumentasi diperbarui: [README.md](README.md) dan [PANDUAN_PENGAJAR.md](PANDUAN_PENGAJAR.md) bagian 5.

**Keterbatasan yang diketahui:**
- Soal dengan batas 1 detik tidak mendapat margin, karena `RLIMIT_CPU` hanya menerima detik bulat.
- Bootstrap Python (sekitar 0,1 s CPU) ikut terhitung dalam batas CPU.
- `time_ms` yang tampil ke siswa masih berupa waktu dinding dan termasuk overhead container: program trivial tercatat 0,5–1,9 s.

**Risiko terbuka (ditemukan 10 November 2026):** pada tiga pengukuran pertama dengan laptop memakai baterai, sekitar 20% Submit program penjumlahan (6 dari 32, 13 dari 48, dan 3 dari 24) mendapat TLE pada **kasus pertama setelah kompilasi**, dengan `time_ms` ±5,5 s. Masalah ini hanya terjadi dengan image `gcc12-v3`; image v2 dengan beban yang sama lulus 24/24. Setelah laptop tersambung ke listrik, 128 job berikutnya pada v3 lulus semua. Dugaan penyebabnya: kerja kernel, seperti reclaim memori saat batas memori diturunkan dari 512 MB (kompilasi) ke 128 MB (eksekusi), ikut terhitung sebagai waktu CPU proses. Hipotesis ini belum dibuktikan. Jika muncul lagi, pilihannya adalah memberi `RLIMIT_CPU` hard limit = batas + 1 s, atau menurunkan batas memori sebelum kompilasi selesai. Sebelum itu, ukur exit code dengan `scripts/profiling/capacity.py` pada 12 paralel.

**Belum diverifikasi:**
- [ ] Uji beban 30 pengguna pada stack lengkap: tidak ada 503 `provider not ready`, runner tetap `healthy`, dan validasi yang berjalan bersamaan berakhir `completed`. Pada 10 November 2026 image aplikasi sudah dibangun ulang dan suite `smoke` (9 skenario judge pada stack lengkap) lulus, tetapi uji beban 30 pengguna tetap belum dijalankan.

---

## M2 — Siap dibuka untuk satu kelas

**Tujuan:** sebelum port dibuka untuk siswa (di belakang reverse proxy dengan HTTPS), batas laju (rate limit) dan fitur khusus admin tidak bisa dipakai untuk mengganggu pengguna lain.

### M2.1 Pakai IP klien yang sebenarnya

**Masalah:** di belakang proxy, `request.client.host` selalu berisi IP proxy. Akibatnya batas pendaftaran 5 per jam dan batas 30 kegagalan kode undangan per 5 menit berlaku untuk seluruh server sekaligus.

- [ ] Beri layanan `api` di [compose.yaml](compose.yaml) perintah `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=<IP proxy>`.
- [ ] Catat langkah ini di bagian deployment pada [KEBUTUHAN_KEAMANAN.md](KEBUTUHAN_KEAMANAN.md).

**Kriteria selesai:** dari dua klien berbeda di belakang proxy, klien kedua tetap bisa mendaftar dan bergabung ke kelas walaupun klien pertama sudah mencapai batasnya.

### M2.2 Login yang berhasil tidak ikut menghabiskan kuota

**Masalah:** [app/auth.py:203](app/auth.py#L203) menghitung semua percobaan login. Siapa pun bisa mengunci akun pengajar dengan 10 password salah, dan bisa mengulanginya setiap 5 menit.

- [ ] Ikuti pola di `join_class`: panggil `consume_rate(..., increment=False)` sebelum verifikasi, dan panggil `consume_rate(...)` hanya ketika password salah.
- [ ] Tambahkan uji: 9 login gagal ditambah 1 login berhasil, kemudian login berikutnya tetap diterima.

**Kriteria selesai:** uji di atas lulus, dan uji login yang sudah ada tetap lulus.

### M2.3 Batasi pemasangan plugin ZIP

**Masalah:** kode plugin dijalankan dengan `exec()` di dalam worker. Worker menyimpan password DB dan `RUNNER_TOKEN`, sedangkan runner memegang Docker socket. Artinya kebocoran password admin (tanpa MFA) setara dengan kendali penuh atas host. Plugin juga bisa mengubah fungsi lain di worker, dan perubahan itu tetap aktif walaupun plugin sudah dinonaktifkan.

- [ ] Di awal `install_plugin` ([app/judge_plugins.py:109](app/judge_plugins.py#L109)), tolak permintaan dengan 403 kecuali `PLUGIN_INSTALL_ENABLED=true`. Nilai bawaannya mati.
- [ ] Tambahkan `PLUGIN_INSTALL_ENABLED` ke `.env.example` dan [scripts/init-env.ps1](scripts/init-env.ps1) dengan nilai `false`.
- [ ] Di [plugin/README.md](plugin/README.md), jelaskan bahwa setelah plugin dinonaktifkan, worker harus di-restart.
- [ ] Sesuaikan [tests/test_judge_plugins.py](tests/test_judge_plugins.py) dan `npm run test:plugins` agar mengaktifkan flag tersebut.

**Kriteria selesai:** dengan pengaturan bawaan, `POST /admin/judge-plugins` mengembalikan 403. Dengan flag aktif, uji plugin tetap lulus.

---

## M3 — Perampingan kode

**Tujuan:** mengurangi kode yang tidak dipakai atau yang ditulis berulang. Perilaku aplikasi tidak berubah.

- [ ] **M3.1** Hapus penulisan file `plugin/installed/<revision>.py` di [app/providers.py:57-67](app/providers.py#L57-L67) dan pakai `compile(self.source, f"plugin:{self.revision}", "exec")`. Hapus juga baris `mkdir`/`chown` untuk `plugin/installed` di [Dockerfile](Dockerfile).
- [ ] **M3.2** Gabungkan tiga salinan pembentukan ulang `PathInput` ([app/learning.py:379](app/learning.py#L379), [app/learning.py:400](app/learning.py#L400), [app/learning.py:508](app/learning.py#L508)) menjadi satu fungsi `path_input(db, version)`.
- [ ] **M3.3** Keluarkan `pytest` dari [requirements.txt](requirements.txt) ke `requirements-dev.txt`, dan hapus `COPY tests` serta `COPY scripts` dari [Dockerfile](Dockerfile). Perintah pengujian di README perlu diubah agar memakai bind mount, misalnya `docker compose run --rm -v ./tests:/app/tests ...`.

**Kriteria selesai:** semua 94 uji unit/API, suite smoke, dan suite authoring lulus tanpa perubahan pada uji tersebut. Selisih kode sekitar −25 baris.

---

## M4 — Performa dan kerapian

**Tujuan:** mengurangi beban DB yang tidak perlu. Milestone ini dikerjakan setelah M1–M3 stabil.

- [ ] **M4.1** Di `current_user` ([app/auth.py:166-167](app/auth.py#L166-L167)), tulis `last_seen` hanya bila nilainya lebih tua dari 60 detik.
- [ ] **M4.2** Hilangkan query satu per baris (N+1): ganti query `Attempt` per baris dengan `join` di `list_submissions` ([app/main.py:295](app/main.py#L295)), dan ambil enrollment, step, serta course sekaligus di `catalog` ([app/learning.py:450-458](app/learning.py#L450-L458)), seperti yang sudah dilakukan `enrollment_summaries`.
- [ ] **M4.3** Pindahkan `LAPORAN_*.md` ke `docs/laporan/` dan perbarui tautannya. Simpan `artifacts/performance/` (49 MB, berisi 11 salinan kode profil) di luar repositori atau dalam arsip per sesi uji.

**Kriteria selesai:** jumlah query untuk `GET /submissions` (100 baris) turun dari 101 menjadi 1–2, dihitung dengan event `before_cursor_execute` SQLAlchemy di sebuah uji. Uji browser lulus.

---

## M5 — Run dan Submit lebih cepat

**Tujuan:** untuk 11–12 pengguna serentak, hasil Run dan Submit tampil secepat mungkin. Dasar angka ada di [LAPORAN_KEBUTUHAN_SERVER.md](LAPORAN_KEBUTUHAN_SERVER.md).

### M5.1 Kirim pekerjaan ke worker langsung setelah commit (selesai 10 November 2026)

**Masalah:** setiap pekerjaan menunggu tick scheduler (hingga 1 detik) dan satu tugas dispatcher sebelum sampai ke worker.

- [x] `create_submission` memanggil `publish_attempt` tepat setelah commit ([app/main.py](app/main.py), [app/tasks.py](app/tasks.py)). Antrean SQL tetap menjadi sumber kebenaran: attempt disimpan dengan `dispatch_after` 30 detik ke depan, sehingga scheduler hanya mengirim ulang bila pesan pertama hilang.
- [x] Bila Redis tidak bisa dihubungi, `dispatch_after` dikembalikan ke saat ini dan scheduler mengambil alih. Permintaan tetap dijawab 202.
- [x] Koneksi broker dibuat gagal cepat (`socket_connect_timeout` 1 s, tanpa retry). Tanpa ini, API tertahan 21 detik per permintaan saat Redis tidak menjawab; sekarang 1,1 detik.
- [x] Uji `test_submission_is_published_immediately_and_falls_back_to_scheduler`, dan `tests/conftest.py` yang mencegah uji unit menghubungi Redis.

**Hasil ukur (stack lengkap, satu pengguna, 6 kali per jenis):** waktu dari permintaan sampai worker mulai bekerja median 0,10–0,11 s, maksimum 0,13 s. Permintaan sampai hasil: Run median 2,0 s, Submit median 4,95 s. Uji Redis dimatikan: POST tetap 202, pekerjaan selesai ACCEPTED setelah Redis hidup kembali, dan worker tersambung ulang sendiri.

**Belum dikerjakan:** validasi soal oleh pengajar masih menunggu tick scheduler.

### M5.2 Polling hasil lebih rapat (selesai 10 November 2026)

- [x] Editor memeriksa hasil setiap 0,4 detik selama 15 detik pertama, lalu kembali ke 1,2 detik ([web/app.js](web/app.js)). Diuji dengan `npm run test:compiler` (4 skenario lulus).

### M5.3 Semua kasus uji dalam satu kali start container (rencana)

**Masalah:** satu Submit dengan 5 kasus uji memakai ±10,5 detik-CPU dan ±4,2 detik di runner, padahal kompilasinya hanya ±0,7 detik. Sisanya habis karena container dinyalakan ulang untuk kompilasi dan untuk setiap kasus uji (6 kali start, masing-masing ±0,6–0,9 detik termasuk bootstrap Python).

**Rancangan:** runner mengirim satu payload berisi source dan semua input. Bootstrap di sandbox mengompilasi, lalu menjalankan program untuk tiap kasus sebagai proses anak, dan mengembalikan satu JSON berisi hasil per kasus.

- [ ] Fase `judge` baru di [sandbox/entrypoint.py](sandbox/entrypoint.py): kompilasi, lalu per kasus `fork`/`exec` program dengan `RLIMIT_CPU`, stdin dari berkas, stdout/stderr dibatasi `output_bytes`, dan waktu CPU diambil dari `wait4` (ini sekaligus memberi `time_ms` yang akurat dan batas waktu di bawah 1 detik).
- [ ] Isolasi antar-kasus yang sekarang didapat dari restart container harus diganti secara eksplisit: bunuh seluruh grup proses setelah tiap kasus, kosongkan `/work` dan `/tmp`, dan jalankan program sebagai UID yang berbeda dari bootstrap agar program tidak bisa mengubah bootstrap, membaca input kasus berikutnya, atau memalsukan JSON hasil.
- [ ] Batas memori: sekarang 512 MB untuk kompilasi lalu diturunkan ke batas soal lewat `container.update`. Dalam satu start, batas program perlu dipasang per proses anak (`RLIMIT_AS` atau cgroup anak) dan vonis MLE dideteksi tanpa `OOMKilled` milik container.
- [ ] Expected output tetap tidak boleh masuk sandbox; pembandingan token tetap di runner.
- [ ] [runner/engine.py](runner/engine.py) `judge_in_sandbox` menjadi satu `execute`; image naik ke `gcc12-v4`.
- [ ] Perbarui [tests/test_sandbox_reuse.py](tests/test_sandbox_reuse.py): uji isolasi berkas dan proses antar-kasus harus tetap lulus, ditambah uji bahwa program tidak bisa memalsukan hasil kasus lain.
- [ ] Ukur ulang dengan `scripts/profiling/capacity.py` dan perbarui [LAPORAN_KEBUTUHAN_SERVER.md](LAPORAN_KEBUTUHAN_SERVER.md).

**Kriteria selesai:**
- Submit 5 kasus saat sendirian ≤ 2 detik di runner (sekarang ±4,2) dan ≤ 5 detik-CPU (sekarang ±10,5).
- Semua uji sandbox dan suite `smoke` lulus, termasuk skenario loop tak berujung, output berlebihan, dan isolasi.
- Risiko TLE palsu `RLIMIT_CPU` dari M1 diperiksa ulang pada protokol baru (12 paralel, 0 TLE pada program penjumlahan).

**Risiko:** ini mengubah batas keamanan sandbox. Jangan digabung dengan perubahan lain, dan pertahankan `gcc12-v3` sebagai jalan kembali.

---

## Di luar cakupan milestone ini

- Integrasi DOMjudge tetap ditunda.
- MFA untuk admin dan sandbox khusus untuk plugin merupakan perbaikan jangka panjang untuk M2.3, karena membutuhkan desain tersendiri.
