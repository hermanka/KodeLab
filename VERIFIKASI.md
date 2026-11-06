# Verifikasi fondasi C/C++

## Konfirmasi urutan 12 lalu 8 slot — 4 November 2026

Kedua pengujian 30 pengguna selesai: 128/128 pekerjaan API benar, tanpa retry eksekusi, progres/nilai seluruh peserta 100. P95 Run/Submit sejak percobaan pertama: 12 slot 22,937/42,178 detik; 8 slot 24,534/46,195 detik. Pemenang berbalik dibanding putaran pertama; 8 masih lebih rendah pada statistik gabungan dua putaran, tetapi belum terbukti selalu optimal.

Analyzer awal 8 slot salah membuang commit akhir akibat filter batas timestamp. Koreksi pada alat profiling menghubungkan catatan berdasarkan induk span dan proses, dengan self-check event commit di luar batas waktu sintetis. Data mentah dianalisis ulang tanpa mengulang beban; 64/64 trace per kapasitas tergabung tanpa issue. Analisis/manifest sebelum perbaikan dipertahankan, laporan lama dari putaran pertama tidak diubah. Kode inti aplikasi tidak diubah.

Verifikasi DB: kelas fixture tersisa 0, akun fixture 60 dinonaktifkan, pending 0; worker eksekusi kembali 50, validator 1, scheduler 1 detik. Runner kembali 50 slot dan sandbox gcc12-v2, profiler API/runner nonaktif. Image kelima layanan identik pada empat cohort lengkap yang dibandingkan; pemindaian rahasia konfigurasi di artefak baru lulus.

[Laporan konfirmasi, dua putaran, dan waktu antar-container](artifacts/performance/slot-sweep-20261104-142709-e053a4/LAPORAN_KONFIRMASI_8_12.md).

## Perbandingan 4/8/12/16 slot — 4 November 2026

Sweep mengubah concurrency worker dan slot runner bersama melalui override sementara, tanpa mengedit Compose atau kode aplikasi. Scheduler 1 detik dan kuota kelas 20 dipertahankan. Konfigurasi aktual diverifikasi pada setiap child. Script mendukung resume, mempertahankan percobaan gagal, dan menolak restart jika ada pekerjaan DB aktif.

Empat cohort lengkap masing-masing 64/64 benar, tanpa retry eksekusi. P95 sejak percobaan pertama termasuk antrean/429/retry alat uji:

| Slot/worker | Run P95 | Submit P95 | Durasi fase Run / Submit |
|---:|---:|---:|---:|
| 4 | 30,147 dtk | 61,496 dtk | 30,229 / 61,761 dtk |
| 8 | 20,818 dtk | 43,858 dtk | 20,863 / 43,896 dtk |
| 12 | 25,574 dtk | 54,257 dtk | 25,625 / 54,365 dtk |
| 16 | 23,287 dtk | 45,182 dtk | 23,642 / 45,298 dtk |

Delapan slot menjadi kandidat berdasarkan jumlah P95 Run+Submit pada cohort lengkap. Peringkat bukan bukti optimum: satu cohort lengkap per kapasitas, urutan/cache/variasi host belum dikendalikan, dan dua kapasitas worker/runner berubah bersama. Target 5–7 detik belum tercapai.

Percobaan 8 slot pertama mengalami satu ReadError pada POST Submit (45,163 ms), sehingga hanya 63/64 diterima/ditelusuri. Dampaknya admission failure dan progres satu peserta tetap 50; tidak ditemukan salah nilai pada pekerjaan yang berjalan. Percobaan gagal dipertahankan dan tidak diperingkat; pengulangan 8 slot lengkap tanpa anomali. Total lima percobaan: 319 selesai benar dari 320 yang direncanakan.

Self-check perbandingan/penjagaan overwrite/percobaan gagal dan pemeriksaan sintaks PowerShell lulus. Verifikasi independen mencocokkan image/command normal, worker 50 proses, runner 50 slot, scheduler 1 detik; profiler dilepas. Lima kelas fixture sudah dihapus dan 150 akun dinonaktifkan, tanpa pekerjaan/sandbox tertinggal. Log kelima percobaan tidak memuat cleanup error/judging failed/profiler write failed; scan artefak tidak menemukan secret terkonfigurasi.

[Laporan perbandingan baru](LAPORAN_PERBANDINGAN_SLOT.md) memuat tabel waktu pengguna, runner, antrean, sumber daya, kontrol, serta tautan laporan tiap kapasitas dengan timeline antar-container. Konfigurasi normal 50/50 tetap aktif; kandidat belum diterapkan.

## Admission API lebih singkat dan uji konkurensi ulang — 4 November 2026

Preflight izin/bahasa/provider dilakukan tanpa lock tulis; transaksi/koneksi dilepas sebelum health check/persiapan provider. Setelah admission lock diambil, izin/status/provider diperiksa ulang, lalu kuota dan penyimpanan job/audit dilakukan atomik. Urutan admission sebelum enrollment/kelas tetap dijaga. Default perilaku pemanggil lain `problem_access` dan `authorize_step_submission` tetap memakai lock saat submit. Perubahan provider/revisi saat preflight ditolak 409; retry idempoten tetap bekerja ketika runner offline.

- **100 unit/API lulus, 16 skipped** (12 tes Docker runner yang tidak berubah dan 4 tes MariaDB yang dijalankan terpisah). Dua warning dependensi/fixture ZIP yang sudah dikenal tetap ada.
- **4 tes MariaDB disposable lulus**, termasuk health check tertahan tanpa koneksi/lock yang ditahan, permintaan lain tetap diterima, urutan lock replay, kuota global 49 → 50 tidak terlewati, kiriman ber-key sama tetap satu job, serta pemulihan migrasi sebelumnya. Container/database sementara dibersihkan.
- Uji konkurensi 4 baseline + 30 Run + 30 Submit: **64/64 benar**, tanpa retry eksekusi. Kedua burst awal menerima 23 dan menolak 7 dengan HTTP 429, lalu selesai setelah retry terkontrol. Pending/running maksimum 20.
- Rata-rata menunggu lock Run 5,213 → 1,518 detik; Submit 4,999 → 2,507 detik. Waktu lock dipegang rata-rata 0,188/0,364 detik. Waktu request yang diterima sampai hasil terlihat rata-rata 11,556/23,012 detik, P95 16,160/31,424 detik, maksimum 16,270/32,247 detik.
- Waktu seluruh fase 30 peserta hampir tetap: 22,230/44,586 detik. Maksimum sejak percobaan pertama termasuk retry 22,186/44,571 detik. Target 5–7 detik belum tercapai; pada Submit, menunggu lock masih mencapai 19,151 detik dan runner rata-rata 17,319 detik.
- Analisis 9.344 rekaman lengkap 64/64 tanpa masalah interval atau koreksi commit. Seluruh peserta mencapai progres/nilai 100. Log tidak memuat cleanup error/judging failed/profiler write failed. Command/image normal dipulihkan dengan API baru tetap aktif; fixture dan sandbox dibersihkan.

[Laporan baru admission](LAPORAN_PERFORMA_ADMISSION.md) memuat tabel antar-container, timeline terburuk, kontrol profiler, data mentah, dan keterbatasan. Semua laporan/data lama dipertahankan.

## Konkurensi setelah reuse container dan wait Docker — 4 November 2026

Pengujian baru memakai konfigurasi 50 proses worker, 50 slot runner, scheduler 1 detik, dan kuota pending kelas tetap 20. Empat baseline API, 30 Run, dan 30 Submit selesai: **64/64 benar**, 32 Executed dan 32 Accepted, tanpa retry eksekusi. Burst Run menerima 30/30; Submit menerima 25 dan menolak 5 dengan 429 sebelum retry terkontrol. Seluruh peserta mencapai progres/nilai 100.

Rata-rata request yang diterima sampai hasil terlihat: **Run 16,378 detik**, **Submit 23,926 detik**; P95 22,258/34,181 detik dan maksimum 22,282/35,427 detik. Maksimum sejak percobaan pertama termasuk 429/retry Submit 44,389 detik. Target 5–7 detik belum tercapai.

Pada 64 pekerjaan, create/remove masing-masing turun 256 → 64 dan inspeksi 2.361 → 256 dibanding uji 50/50 sebelumnya. Semua pekerjaan menggunakan satu ID container sepanjang kompilasi/input; setiap fase normal tepat satu wait/inspeksi/start. Total runner Submit rata-rata turun 24,991 → 16,180 detik, tetapi lock admission mencapai 24,819 detik. Analisis 7.949 rekaman berhasil 64/64 tanpa masalah interval/penjumlahan atau koreksi commit. Log tidak memuat peringatan cleanup/kegagalan judge/profiler write.

Fixture dibersihkan; kelas dihapus dan 30 akun dinonaktifkan. Command/image normal dipulihkan dengan konfigurasi baru tetap aktif, profiler dilepas; tidak ada sandbox tersisa. [Laporan baru lengkap](LAPORAN_PERFORMA_REUSE_WAIT.md), dengan data mentah, timeline terburuk, waktu antar-container, kontrol profiler dan keterbatasan pengukuran. Seluruh laporan/data sebelumnya dipertahankan.

## Pengurangan inspeksi Docker — 4 November 2026

Loop reload/sleep setiap 25 ms diganti dengan wait pemberitahuan selesai Docker. Timer terpisah menerapkan batas waktu, pembaca output menghentikan container ketika batas stdout/stderr terlampaui, dan satu reload akhir membaca exit code/OOM. Timer dibatalkan serta di-join sebelum input berikutnya. Jika kill gagal karena container sudah keluar, status dikonfirmasi tanpa memberi verdict timeout palsu; kesalahan wait/penegakan tenggat tetap menjadi kegagalan infrastruktur.

- **13 tes unit/regresi runner lulus**, termasuk timer-versus-exit race, wait gagal, kill gagal, checker, kontrak hasil, dan kapasitas runner.
- **12 pengujian Docker nyata lulus**: C17/C++17 Run/Submit, batas waktu/memori/output, kelanjutan input berikutnya setelah kegagalan, isolasi file/proses, dan cleanup. Tes normal menghitung tepat satu inspeksi akhir per fase, bukan sekadar memeriksa output.
- Self-check profiling Docker lulus: satu container fisik, tiga fase, tiga wait dan tiga inspeksi akhir, dengan ID yang sama dan tanpa error span. Pencatatan lifetime PID1 tetap tersedia.
- Runner baru sudah dibangun dan diaktifkan setelah memastikan tidak ada pekerjaan aktif. Provider nyata lewat HTTP mengembalikan Executed untuk Run C++17 dan Accepted untuk Submit C++17, dengan nilai serta penyembunyian test privat sesuai kontrak. Runner sehat dan tidak ada container sandbox tersisa.

Interval `container_wait` pada profiler kini mencakup waktu menunggu compiler/program selesai; tidak seluruhnya biaya overhead Docker. Laporan performa lama tetap merupakan hasil implementasi sebelumnya. Benchmark konkurensi belum diulang untuk perubahan ini.

## Penggunaan ulang satu container per Run/Submit — 4 November 2026

Runner kini membuat satu container fisik `js-<attempt_id>` untuk satu Run/Submit. Proses container di-start kembali antara kompilasi dan setiap input agar PID/tmpfs bersih; batas memori kompilasi/runtime diatur kembali. Container dihapus sekali melalui `finally`. Jawaban acuan/checker tetap di pengendali. Output dipasang sebelum start tanpa membaca log fase sebelumnya. Reaper memakai daftar sparse lalu reload di dalam penanganan NotFound agar container yang sudah dihapus tidak menggagalkan seluruh enumerasi. Container yatim memiliki tenggat 180 detik. Image sandbox menjadi `judgementsystem-sandbox:gcc12-v2`.

- **12 regresi Docker nyata lulus** (`RUN_SANDBOX_TESTS=1`, `tests/test_sandbox_reuse.py`): C17/C++17 Run/Submit, satu ID container sepanjang semua fase, tidak ada kebocoran log kompilasi, jawaban salah/runtime error/timeout/output berlebih/OOM diikuti input berikutnya yang benar, file/proses anak tidak bertahan antar-input, UID/read-only/tanpa socket/token, serta cleanup pada compilation error dan kesalahan infrastruktur.
- **89 unit/API lulus, 14 skipped**, dua warning dependensi/fixture ZIP yang sudah dikenal. Dua belas tes Docker di atas sengaja skipped pada suite biasa dan dijalankan terpisah dengan Docker; dua skip lainnya mengikuti kondisi suite yang tersedia.
- Provider custom nyata melalui HTTP runner: C17 Run menghasilkan `42` tanpa nilai; C++17 Submit menghasilkan Accepted/nilai 100 dan menyembunyikan rincian test privat.
- Self-check profiling dengan Docker: satu operasi create/remove, tiga start/lifetime PID1, dan ID container sama di semua fase. Analyzer membedakan container fisik dan fase; kompatibilitas dua dataset performa lama diuji pada salinan sementara, 64/64 pekerjaan masing-masing, tanpa menulis ulang laporan/data asli. Sintaks wrapper PowerShell lulus.
- Runner baru sudah dibangun dan diaktifkan setelah verifikasi tidak ada pekerjaan aktif. Tidak ada sandbox berlabel proyek tersisa sesudah pemeriksaan.

Ini verifikasi fungsi/isolasi, bukan benchmark konkurensi baru. Create/remove kini sekali per pekerjaan; start proses, transfer binary, dan inspeksi Docker masih dilakukan per fase. Target latensi belum diukur ulang. Panduan lifecycle dan pengujian tersedia di [README](README.md).

## Konkurensi 50 proses worker / 50 slot runner — 4 November 2026

Konfigurasi aktual diverifikasi: 50 proses Celery eksekusi, 1 validator, runner 50 slot, scheduler 1 detik. Cap internal runner 4 slot diperbaiki agar mengikuti environment, dan thread pool endpoint sinkron disesuaikan. Regresi runner/judging **8 passed**, self-check profiler dan sintaks wrapper PowerShell lulus.

Uji baru: 4 baseline, 30 Run, 30 Submit; **64/64 pekerjaan benar**, tanpa retry eksekusi. Burst Run menerima 30/30; burst Submit menerima 20 dan menolak 10 dengan 429 sebelum retry terkontrol. Puncak running/pending 20. Antrean worker rata-rata turun ke 0,028/0,014 detik, tetapi runner naik ke 8,024/24,991 detik untuk Run/Submit. Request yang diterima sampai hasil terlihat rata-rata 19,344/28,066 detik; target 5–7 detik belum tercapai.

Analisis 64/64 trace selesai, termasuk penandaan dua observasi commit terlambat 8,154/27,441 ms. Snapshot log memuat 10 cleanup NotFound tanpa kegagalan job. Seluruh layanan normal kembali berjalan dengan konfigurasi baru, profiler dilepas; diverifikasi tidak ada pekerjaan aktif/sandbox tersisa, kelas fixture terhapus, dan 30 akun fixture nonaktif. Pemeriksaan artefak tidak menemukan secret terkonfigurasi. [Laporan baru](LAPORAN_PERFORMA_50_WORKER.md); laporan/data lama dipertahankan.

## Profil detail Run/Submit — 4 November 2026

Pengujian ulang memakai 4 baseline API, 30 Run dan 30 Submit pada kelas/path sementara: **64/64 pekerjaan benar**, 32 Executed dan 32 Accepted. Semua 10.877 rekaman timing berhasil dianalisis tanpa masalah join/penjumlahan critical path. Self-check instrumentasi lulus. Pemeriksaan artefak tidak menemukan nilai password/token/secret terkonfigurasi.

Pada burst Submit, rata-rata outbox 11,918 detik, antre worker 11,716 detik, runner 6,012 detik, dan request sampai hasil tersimpan 31,040 detik. Dispatcher menunggu maksimum 34,588 detik. Dua burst masing-masing menolak 10 permintaan awal dengan 429 sesuai batas pending; retry admission dilakukan alat uji. Tidak ditemukan kegagalan atau retry eksekusi. Kontrol runner sebelum/sesudah instrumentasi menunjukkan kenaikan teramati sekitar 6–13%, dengan hanya dua sampel per bahasa/mode.

Layanan/image asli sudah dipulihkan dan seluruh layanan berjalan; API, DB, Redis, dan runner sehat. Kelas uji dihapus dan 30 akun uji dinonaktifkan. Tidak ada optimasi kode aplikasi atau perubahan kapasitas diterapkan. [Laporan detail dan keterbatasan](artifacts/performance/judging-profile-20261104-093052-80dbc2/LAPORAN_DETAIL_RUN_SUBMIT.md), [panduan pengulangan](scripts/profiling/README.md).

Tanggal: 30 Oktober 2026. Lingkungan: Windows dengan Docker Desktop, Engine Linux, dan Docker Compose.

Hasil terbaru tahap 3: **33 pengujian unit/API, 9 skenario judge, 5 kelompok authoring, dan 6 kelompok alur browser lulus**. Catatan tahap 1 dan 2 dipertahankan sebagai riwayat; pembaruan learning path/web dijabarkan di bagian akhir.

## Pemeriksaan fondasi

| Pemeriksaan | Hasil |
|---|---|
| `docker compose config --quiet` | Lulus |
| Build image aplikasi dan sandbox | Lulus |
| Migrasi Alembic dan seed `sum-v1` di MariaDB | Lulus |
| Menjalankan kembali migrasi/seed pada database yang sama | Lulus |
| `docker compose up -d --wait --wait-timeout 90` | Selesai; API, runner, database, dan Redis sehat; worker/scheduler berjalan |
| `alembic check` pada database aktual | `No new upgrade operations detected.` |
| Akses host ke `http://127.0.0.1:8000/health/ready` dan `/docs` | `ready` dan HTTP 200, setelah menambahkan jaringan ingress untuk publikasi port Docker Desktop |
| Container sandbox tersisa setelah smoke test | Tidak ada |

## Pengujian unit dan API

Hasil: **12 passed** menggunakan image aplikasi dengan Python 3.12.

Mencakup checker token dan batas token, penyembunyian keluaran kasus privat, penolakan hasil tidak lengkap/tidak konsisten, run tanpa nilai, prioritas provider, status DOMjudge yang belum tersedia, batas UTF-8, idempotensi kiriman, snapshot provider, autentikasi dan validasi API, retry tanpa nilai nol, deduplikasi tugas, serta pemulihan lease yang kedaluwarsa.

Pengujian transaksi unit memakai database SQLite sementara yang terisolasi; pengujian integrasi berikut memakai MariaDB aktual. Terdapat peringatan deprecation dari dependensi Starlette/AnyIO pada TestClient. Penggunaan `-p no:cacheprovider` menghindari upaya menulis cache pytest ke direktori aplikasi yang dimiliki root.

## Pengujian seluruh layanan

Perintah: `docker compose exec -T api python scripts/smoke.py`.

| Skenario | Hasil |
|---|---|
| Solusi penjumlahan C17 | `ACCEPTED`, nilai 100 |
| Solusi penjumlahan C++17 | `ACCEPTED`, nilai 100 |
| Jawaban hardcoded `5` | `WRONG_ANSWER`, nilai 0 |
| Sintaks C++ tidak valid | `COMPILATION_ERROR`, nilai 0 |
| Program keluar dengan kode 7 | `RUNTIME_ERROR`, nilai 0 |
| Loop tanpa akhir | `TIME_LIMIT_EXCEEDED`, nilai 0 |
| Keluaran tanpa batas | `OUTPUT_LIMIT_EXCEEDED`, nilai 0 |
| Input bebas `40 2` | `EXECUTED`, output `42`, tanpa nilai |
| Probe isolasi dasar | `EXECUTED`: UID 65534, penulisan filesystem dasar ditolak, Docker socket tidak tersedia, token runner tidak tersedia |

Smoke test juga memeriksa penolakan akses tanpa token, hanya satu contoh soal yang ditampilkan, penolakan provider DOMjudge yang belum diimplementasikan, pengulangan idempotency key tanpa submission ganda, konflik key dengan isi berbeda, dan ketiadaan stdout/stderr/input/jawaban acuan pada rincian kasus tersembunyi.

## Batas hasil verifikasi

Pengujian ini memvalidasi fondasi pengembangan lokal. Belum mencakup integrasi DOMjudge, pengujian beban, autentikasi banyak pengguna, audit keamanan menyeluruh, kesetaraan hasil antar mesin, klasifikasi semua bentuk kehabisan memori, atau crash recovery lintas host pada deployment publik. Probe isolasi dasar bukan bukti bahwa Docker kebal terhadap eksploitasi kernel/runtime.

Kode, konfigurasi, dan langkah pengujian tersedia di repositori ini; kredensial lokal berada di `.env` yang diabaikan oleh Git dan tidak disertakan dalam catatan verifikasi.

## Pembaruan tahap 2 — Akun dan authoring dinamis

### Migrasi dan kompatibilitas data

- Backup lokal dibuat pada `.backups/before-0002.sql` sebelum perubahan skema; file diabaikan Git dan build context Docker.
- Migrasi `0002` selesai pada MariaDB aktual. Sembilan submission sebelumnya tetap ada dengan pemilik NULL dan akses admin saja.
- Seed dan bootstrap admin dapat dijalankan ulang tanpa mengganti konten terbit atau password admin yang sudah ada.
- `alembic check` kembali menghasilkan `No new upgrade operations detected.`

### Pengujian otomatis

**23 passed**, menggunakan image aplikasi. Selain pengujian fondasi, suite memeriksa hash Argon2id, penolakan registrasi berperan tinggi, redaksi password pada error validasi API/bootstrap, CSRF/origin, logout, idle timeout, pencabutan sesi, pembatasan login gagal, kepemilikan submission, idempotensi per akun, scope kelas/daftar anggota/daftar submission, sanitasi Markdown, draft/publikasi/revisi/arsip, konflik edit, invalidasi hasil validasi setelah edit, acuan salah, retry infrastruktur, dan audit tanpa isi kunci.

Pengujian unit/API menggunakan SQLite sementara. Validasi kode acuan pada pengujian unit memakai provider pengganti terkontrol; kompilasi asli dibuktikan oleh suite integrasi berikut. Masih ada peringatan deprecation dari Starlette/AnyIO TestClient, tanpa kegagalan pengujian.

### Integrasi MariaDB, Redis, worker, dan compiler asli

Jalankan:

```powershell
.\scripts\test-integration.ps1 -Suite smoke
.\scripts\test-integration.ps1 -Suite smoke_authoring
```

Suite judge mengulang **sembilan skenario tahap 1** dengan akun peserta individual; semuanya lulus. Suite authoring membuktikan lima kelompok alur berikut:

| Kelompok | Hasil |
|---|---|
| Materi dinamis | Draft tidak terlihat peserta; materi terbit dapat dibaca dan HTML script dirender aman |
| Validasi/publikasi soal | Acuan C17 dan C++17 dikompilasi dan diuji dalam sandbox; hanya draft lolos yang dapat diterbitkan |
| Akses kelas dan submission | Peserta terdaftar mendapat nilai 100 pada soal baru; pihak luar ditolak; kunci/kasus privat tidak dikirim ke peserta |
| Revisi dengan kunci salah | Validasi gagal dan publikasi ditolak; versi terbit sebelumnya tetap dapat dipakai |
| Kuota admission serentak | Dari 12 request bersamaan pada akun uji baru, 10 diterima dan 2 mendapat HTTP 429; semua pekerjaan yang diterima selesai sebagai timeout sesuai program ujinya |

Suite membuat akun, kelas, materi, revisi soal, audit, dan submission uji pada database pengembangan. Kredensial admin dikirim lewat stdin oleh skrip PowerShell dan tidak dicetak atau dimasukkan ke argumen proses. Akun uji menggunakan password acak baru.

### Batas tahap 2

Belum ada learning path/prasyarat/progres, UI belajar, MFA, reset password, unggahan, atau integrasi DOMjudge. Uji serentak admission bukan pengujian beban menyeluruh atau bukti audit keamanan lengkap. Backup sebelum migrasi belum diuji sebagai prosedur disaster recovery. Daftar kontrol yang masih perlu dipenuhi tersedia di [KEBUTUHAN_KEAMANAN.md](KEBUTUHAN_KEAMANAN.md).

## Pembaruan tahap 3 — Learning path dan antarmuka web

### Migrasi dan data

- Backup database sebelum perubahan disimpan di `.backups/before-0003.sql`, diabaikan Git/build context.
- Migrasi `0003` menambahkan versi path, langkah, enrollment, completion, dan konteks submission tanpa menghapus data sebelumnya.
- `alembic check` pada MariaDB aktual melaporkan tidak ada perbedaan skema.
- Bootstrap admin/seed tetap dapat dijalankan ulang tanpa mengganti password admin atau menghapus konten lama.

### Unit/API: 33 passed

Tambahan terhadap 23 pengujian sebelumnya meliputi:

- Penolakan siklus, prasyarat tidak dikenal, key ganda, dan ketergantungan wajib terhadap langkah opsional.
- Langkah terkunci, akses soal/materi generik, serta pengiriman tanpa konteks path tidak dapat melewati prasyarat.
- Konfirmasi membaca idempoten; manual completion pada latihan ditolak.
- Run dan jawaban salah tidak menambah progres; Accepted dari worker membuat completion resmi dengan rujukan attempt, tepat satu kali.
- Kepemilikan enrollment, kecocokan soal/step, serta penolakan field completion palsu.
- Langkah opsional tidak menahan kelulusan.
- Versi enrollment dan progres lama tetap utuh saat versi path baru terbit.
- Arsip mencegah enrollment baru; pencabutan keanggotaan memblokir akses berikutnya.
- Scope kelas pada authoring/laporan dan penolakan rujukan lintas kelas.
- Halaman web/aset lokal tersedia dengan CSP yang tidak mengizinkan inline script.

Unit/API menggunakan SQLite sementara dan provider pengganti untuk skenario terkontrol. Kedua suite integrasi tahap sebelumnya juga dijalankan ulang pada MariaDB/Redis/runner nyata: sembilan skenario judge dan lima kelompok authoring tetap lulus.

### Browser nyata: Microsoft Edge headless

Perintah: `npm.cmd run test:browser`. Playwright memakai Edge yang sudah terpasang pada host Windows, tanpa mengunduh browser tambahan.

| Kelompok | Bukti |
|---|---|
| Akun/admin | Login melalui form, cookie sesi, dan pembuatan akun teacher/student melalui UI administrasi |
| Authoring konten | Pembuatan dua materi, soal, kasus terbuka/tersembunyi, acuan C17/C++17, validasi di sandbox, lalu publikasi melalui UI |
| Penyusun jalur | Pemilihan versi konten terbit, urutan reading/exercise/refleksi, langkah opsional, dan publikasi path |
| Enrollment/prasyarat | Mengikuti path publik, penolakan akses langsung API dan pengiriman ke langkah terkunci, lalu konfirmasi membaca membuka latihan |
| Editor/penilaian/progres | Input bebas `40 2` menghasilkan `42` tanpa menambah progres; jawaban salah tidak menambah progres; jawaban benar bernilai 100 dan membuka langkah berikutnya; reload mempertahankan progres serta draft per bahasa; viewport 390px tidak meluber horizontal |
| Laporan/keamanan web | Pengajar melihat progres 100%; logout mencabut sesi; tidak ada pageerror/CSP error, token pada localStorage/sessionStorage, atau permintaan aset pihak ketiga |

Screenshot desktop dan mobile diperiksa secara visual terhadap [DESIGN.md](DESIGN.md). Aset menggunakan white canvas, border tipis, Mona Sans/Inter, kode sebagai elemen visual, dan satu aksen teal. Tombol teal memakai teks gelap untuk keterbacaan. Tidak ada gambar stok, gradient dekoratif, atau tema badan gelap.

Artefak lokal dibuat oleh test dan diabaikan Git:

- `artifacts/web-login.png`
- `artifacts/web-studio.png`
- `artifacts/web-reading.png`
- `artifacts/web-exercise.png`
- `artifacts/web-dashboard.png`
- `artifacts/web-mobile.png`
- `artifacts/browser-result.json`

Pengujian membuat contoh kelas/path publik nyata, akun uji dengan password acak, konten, audit, dan submission. Screenshot tidak memuat password/token. Tidak ada HAR atau trace jaringan yang menyimpan kredensial. Versi contoh **Dasar Pemrograman C/C++** dapat diikuti akun peserta baru pada workspace ini.

### Cakupan dan batas

Ini membuktikan MVP lokal learning path dan UI peserta/pengajar bekerja dengan judge custom nyata. Belum mencakup pengujian semua browser, uji beban menyeluruh, audit keamanan produksi, DOMjudge, MFA/reset password, upload, rejudge, nilai parsial, debugger, atau migrasi enrollment. Keberhasilan backup sebelum migrasi tidak dianggap sebagai bukti restore/disaster recovery.

## Regresi pilihan compiler C/C++

Perintah: `npm.cmd run test:compiler` (Edge headless, layanan Docker lokal). Sebelum perbaikan, pengujian mereproduksi pilihan C++17 yang kembali menjadi C17 setelah reload. Kiriman bermasalah pada database juga tercatat sebagai C17, sesuai nama berkas `main.c` pada pesan compiler.

Setelah perbaikan, empat pemeriksaan lulus:

- Pilihan C++17, draft, dan nama `main.cpp` bertahan setelah reload; run input `40 2` menghasilkan `42` dan jawaban resmi Accepted memakai G++.
- Jawaban C17 tetap Accepted memakai GCC.
- Pengiriman membaca nilai pilihan yang terlihat walaupun browser mengubah select tanpa event `change`.
- Kode C++ yang secara eksplisit dikirim sebagai C17 tetap mendapat compilation error, disertai petunjuk memilih C++17. Hasil menampilkan compiler aktual dari respons server.

Script membuat akun peserta uji dengan password acak serta kiriman nyata. Pilihan compiler disimpan per akun/latihan dalam sessionStorage bersama draft dan ikut dibersihkan saat logout. Tidak ada perubahan skema database atau pemilihan bahasa otomatis berdasarkan isi kode.

## Pembaruan — Leaderboard dan penghapusan latihan mandiri

- Latihan mandiri dihapus dari navigasi, dashboard, dan halaman editor terpisah. Tautan lama diarahkan ke katalog. API peserta menolak pembukaan soal generik serta run/submission tanpa enrollment; kiriman historis dipertahankan. Tes lama untuk kepemilikan, kuota, dan authoring disesuaikan agar latihan peserta dilakukan melalui enrollment.
- Progres memuat `started_at`, `completed_at`, `elapsed_seconds`, `completion_seconds`, serta nilai jalur. Durasi memakai timestamp server yang sudah tersimpan, sehingga data lama didukung tanpa migrasi. Completion wajib terakhir menentukan waktu selesai; langkah opsional dan pengiriman ulang tidak mengubahnya.
- Leaderboard per versi jalur dan keseluruhan tersedia bagi tiga peran. Agregasi memfilter akses kelas, akun nonaktif, dan keanggotaan yang dicabut sebelum pemeringkatan. Nilai tidak berasal dari input browser. Leaderboard tidak memuat kode/kunci/kasus uji privat.

Verifikasi backend mencakup urutan nilai/waktu, peringkat bersama saat seri, agregasi banyak jalur tanpa nilai ganda, durasi tetap, langkah opsional, pemisahan versi, kelas privat, autentikasi, akun nonaktif/pencabutan akses, dan penolakan latihan mandiri. Alur penilaian dua latihan wajib memeriksa nilai 50 setelah satu Accepted, tetap 50 setelah run/jawaban salah, lalu 100 dan durasi final setelah Accepted kedua.

Total cakupan unit/API kini **40 tes**: seluruh suite 39 tes lulus sebelum penambahan tes alur dua latihan, lalu suite leaderboard final tujuh tes lulus, termasuk tes tambahan tersebut. Satu peringatan deprecation dari dependensi Starlette/AnyIO tidak menggagalkan pengujian.

Browser Edge nyata (`npm.cmd run test:browser`) lulus tujuh kelompok alur: termasuk leaderboard per jalur/keseluruhan untuk admin, pengajar, dan peserta; durasi tetap setelah selesai; laporan progres pengajar; pengalihan URL latihan mandiri; serta tampilan mobile tanpa halaman meluber. Header tabel diberi `scope="col"` agar pembaca layar mengenali kolom. Screenshot tambahan `artifacts/web-leaderboard-path.png` dan `artifacts/web-leaderboard-mobile.png` diperiksa secara visual.

Integrasi authoring pada MariaDB/Redis/sandbox nyata (`scripts/test-integration.ps1 -Suite smoke_authoring`) tetap lulus lima kelompok, termasuk submission melalui enrollment, kerahasiaan kunci, dan kuota serentak 10 diterima/2 ditolak. Regresi compiler (`npm.cmd run test:compiler`) kini memakai editor dalam learning path dan tetap lulus empat pemeriksaan C17/C++17.

Batas: durasi adalah waktu kalender sejak enrollment, termasuk jeda/offline dan antrean penilaian, bukan pelacakan waktu aktif. Cakupan global mengikuti izin kelas pengguna yang melihatnya. Agregasi lintas versi tidak menyetarakan kesulitan soal. Belum ada pagination leaderboard atau uji beban pemeringkatan skala besar.

## Penyederhanaan navigasi

Top menu dan bar navigasi mobile dihapus; satu sidebar menjadi navigasi aplikasi. Desktop menampilkan sidebar tetap, sedangkan layar sampai 900px menggunakan sidebar yang dibuka melalui tombol menu. Header tetap memuat logo serta kontrol akun. Browser Edge pada 1440px dan 390px memverifikasi enam tautan admin, navigasi ke leaderboard/katalog, penutupan setelah memilih tautan, Escape/latar/tombol tutup, putaran fokus keyboard, pemulihan fokus, resize ke desktop, logout, serta tidak adanya overflow horizontal atau JavaScript error. Screenshot lokal: `artifacts/web-sidebar-desktop.png` dan `artifacts/web-sidebar-mobile.png`.

## Pembaruan — Leaderboard tertanam dan siklus hidup kelas

Leaderboard ditampilkan langsung pada ringkasan learning path dengan versi enrollment yang sama. Tautan leaderboard pada kartu/ringkasan jalur dihapus. Menu leaderboard keseluruhan dan pemilih versi tetap tersedia. Gangguan pemuatan leaderboard tidak menghilangkan materi/progres pada halaman jalur.

Migrasi `0004` menambah `courses.archived`, default false untuk data yang sudah ada. Backup sebelum migrasi tersimpan di `.backups/before-0004.sql`, diabaikan Git/build. Migrasi pada MariaDB aktual berhasil dan `alembic check` melaporkan tidak ada perbedaan model/skema. API, worker, validator, dan scheduler memakai implementasi terbaru.

Seluruh suite **45 unit/API test lulus**. Lima skenario tambahan siklus hidup kelas menguji:

- Arsip/pemulihan mempertahankan progres, membatasi penyuntingan/pengerjaan, menyembunyikan katalog/agregat keseluruhan, dan mempertahankan akses tinjau anggota lama.
- Hanya pemilik kelas berperan pengajar atau admin dapat mengarsipkan/memulihkan/menghapus. Peserta, pengajar asing, dan pengajar tambahan tidak memperoleh hak ini.
- Hapus kelas berisi materi, soal beserta revisi/kunci/kasus uji/validasi, path/langkah, enrollment, completion, kiriman, dan attempt membersihkan seluruh data tersebut tanpa menghapus akun atau kelas lain. Foreign key SQLite diaktifkan secara eksplisit pada pengujian ini.
- Penilaian berjalan maupun validasi berjalan menolak penghapusan tanpa perubahan sebagian. Pesan Celery untuk data yang sudah dihapus tidak membangkitkan ulang data.
- Kegagalan yang sengaja disisipkan di tengah penghapusan mengembalikan seluruh perubahan melalui rollback transaksi.

`npm.cmd run test:browser` lulus kembali tujuh kelompok alur web dengan leaderboard yang langsung tertanam. `npm.cmd run test:course-lifecycle` lulus tiga kelompok tambahan pada Edge/MariaDB/Redis/GCC nyata: menyiapkan kelas uji baru, memvalidasi kunci C/C++, memperoleh Accepted, memeriksa leaderboard tertanam/mobile, mengarsipkan dan memulihkan melalui tombol, menolak nama konfirmasi yang salah, kemudian menghapus permanen melalui UI. Versi konten lama, validasi, enrollment, histori, dan progres kelas uji tidak lagi tersedia setelah penghapusan. Daftar kelas yang sudah ada diperiksa tetap utuh. Pengujian tidak menghapus kelas pengguna yang telah ada.

Screenshot lokal tambahan: `artifacts/web-path-embedded-leaderboard.png`, `artifacts/web-course-archived.png`, dan `artifacts/web-course-delete-confirmation.png`. Semua browser pengujian ditutup; tidak ada HAR/trace atau keluaran kredensial. Audit administratif serta backup terdahulu tetap dipertahankan, terpisah dari konten akademik yang dihapus. Pemulihan backup dan pengujian beban serentak penghapusan belum menjadi bukti pada tahap ini.

## Pembaruan — Navigasi Kelas → Learning path

Menu sidebar **Kelas** membuka daftar kelas aktif yang dapat diakses pengguna, dengan pencarian nama. **Buka kelas** menampilkan learning path dalam kelas tersebut; tombol **Mulai belajar** baru tersedia di dalam kelas. Ringkasan menggunakan kartu kelas, sedangkan halaman jalur/langkah memiliki breadcrumb ke kelas asal. URL katalog jalur/latihan mandiri lama dialihkan ke daftar kelas. Tidak ada migrasi data untuk perubahan ini.

`GET /courses/{id}/learning` memeriksa akses kelas sebelum menampilkan jalur terbit dan enrollment pengguna sendiri. Filter `GET /paths?course_id={id}` diterapkan sebelum batas daftar. Enrollment tetap menggunakan versi yang dipatok; jalur yang diarsipkan setelah diikuti tetap tersedia sebagai riwayat dalam kelas. Kelas arsip yang telah diikuti tetap dapat ditinjau dari kartu Ringkasan.

Seluruh **48 unit/API test lulus**, termasuk tiga skenario tambahan: pembatasan jalur ke kelas serta enrollment ke pemiliknya, penolakan kelas privat/pencabutan akses melalui URL langsung, dan pemeliharaan progres versi lama serta path/kelas arsip. Pengujian browser nyata (`npm.cmd run test:browser`) lulus tujuh kelompok alur setelah siswa diarahkan melalui pencarian kelas dan halaman learning path kelas. Pengujian juga memastikan katalog kelas tidak menyediakan tombol enrollment jalur langsung dan breadcrumb materi/latihan kembali ke kelas yang benar. Penilaian nyata, leaderboard tertanam, mobile, laporan pengajar, dan logout tetap lulus. Screenshot tambahan: `artifacts/web-class-paths.png`.

Manajemen profil, leaderboard kelas, serta halaman/filter arsip khusus pada Studio tetap menjadi butir terpisah di `TODO.md`.

## Regresi daftar kelas setelah penghapusan

Penghapusan dari kartu Studio kini memuat ulang daftar jika pengguna sudah berada di `#/studio`; penghapusan dari detail kelas tetap mengarahkan ke Studio. Sebelumnya, navigasi ke hash yang sama tidak memicu render sehingga kartu lama bertahan. `npm.cmd run test:course-lifecycle` lulus dengan pemeriksaan respons daftar baru dan hilangnya kartu kelas uji tanpa reload halaman. Arsip/pemulihan, konfirmasi nama, penghapusan data terkait pada MariaDB, dan keutuhan kelas yang sudah ada tetap lulus.

## Pembaruan — Leaderboard kelas menggantikan leaderboard jalur

Leaderboard langsung tampil di halaman kelas melalui `GET /courses/{id}/leaderboard`; tabel/endpoint leaderboard jalur dihapus. Halaman keseluruhan hanya memuat satu leaderboard melalui `/leaderboards`, tanpa pemilih kelas/jalur/versi dan tanpa kolom Latihan wajib. Kedua tabel memakai kolom peringkat, peserta, nilai total, jalur selesai, dan waktu penyelesaian.

Agregasi kelas menggunakan aturan keseluruhan yang sama, tetapi memfilter satu kelas sebelum perhitungan: maksimal 100 poin per jalur, sekali per enrollment yang dipatok versinya. Nilai tertinggi diutamakan, lalu jumlah durasi final tersingkat pada jalur yang menyumbang nilai. Durasi belum final diurutkan setelah durasi final pada nilai sama; seri berbagi peringkat. Jalur arsip/tanpa latihan wajib tidak berkontribusi. Kelas arsip tetap dapat ditinjau anggota/pengelola pada leaderboard kelas, sedangkan peringkat keseluruhan mengecualikannya.

Seluruh **49 unit/API test lulus**. Pengujian mencakup dua jalur dalam kelas yang sama, jumlah durasi, prioritas nilai terhadap kecepatan, kelas lain yang tidak mencampuri nilai, versi baru tanpa penggandaan, akun nonaktif/pencabutan akses, penolakan kelas privat, arsip kelas/jalur, dan hapus kelas.

`npm.cmd run test:browser` lulus tujuh kelompok, termasuk leaderboard kelas bagi admin/pengajar/siswa, ketiadaan leaderboard pada halaman jalur, ketiadaan pemilih dan kolom Latihan wajib pada keseluruhan, serta tampilan mobile. `npm.cmd run test:course-lifecycle` lulus setelah assertion disesuaikan ke halaman kelas: leaderboard arsip dapat ditinjau, skor tetap, dan penghapusan kelas menghilangkan endpoint peringkatnya. Satu pemeriksaan awal terhenti karena pencarian teks banner halaman jalur yang sudah diganti; kelas uji yang ditinggalkannya dibersihkan berdasarkan ID dan nama yang diverifikasi, lalu pemeriksaan akhir lulus. Kelas pengguna yang telah ada tetap dipertahankan.

Screenshot lokal: `artifacts/web-leaderboard-class.png`, `artifacts/web-class-embedded-leaderboard.png`, dan `artifacts/web-leaderboard-mobile.png`. Tidak diperlukan migrasi skema.

## Pembaruan — Pemisahan kelas aktif dan arsip

Studio pengajar dan daftar kelas siswa memiliki tab **Kelas aktif** dan **Arsip kelas**. Halaman awal serta Ringkasan menampilkan kelas aktif. Status arsip tersimpan pada URL (`#/studio/archive` / `#/classes/archive`) sehingga tetap dipilih setelah reload. Anggota lama dapat meninjau kelas arsip; tombol pulihkan/hapus tetap terbatas pada pemilik/admin. Pemulihan dan penghapusan dari daftar arsip memuat ulang daftar tanpa mengganti tab.

Filter `GET /courses?status=active|archived` diterapkan sebelum pagination. Seluruh **50 unit/API test lulus**. Skenario tambahan membuat 101 kelas arsip dan satu kelas aktif untuk memeriksa bahwa kelas aktif tetap ditemukan, halaman arsip berikutnya tersedia, nilai status tidak sah ditolak, serta siswa hanya melihat arsip tempat ia menjadi anggota.

`npm.cmd run test:course-lifecycle` lulus pada Edge/MariaDB/Redis/sandbox nyata: kelas uji hilang dari daftar aktif setelah diarsipkan, muncul dalam tab arsip pengajar dan siswa, dapat ditinjau, tetap berada di tab arsip setelah reload, kembali aktif setelah dipulihkan, dan hilang segera setelah dihapus dari tab arsip. Progres/durasi, leaderboard kelas, penolakan perubahan pada arsip, dan keutuhan kelas pengguna yang sudah ada tetap lulus. Screenshot `artifacts/web-course-archived.png` kini menampilkan tab arsip Studio. Tidak diperlukan migrasi skema.

## Pembaruan — Pengaturan visibilitas dan kode undangan

Migrasi `0005` menambah deskripsi, revisi pengaturan, digest undangan unik, dan waktu kedaluwarsa pada kelas; akses dan progres kelas lama dipertahankan. Backup pra-migrasi: `.backups/before-0005.sql`. `scripts/init-env.ps1` menambah secret undangan acak bila belum ada tanpa mengganti nilai lama atau mencetak rahasia. `alembic check` pada MariaDB melaporkan tidak ada selisih skema/model setelah migrasi.

Pemilik/admin dapat mengubah nama, deskripsi teks, dan akses melalui tab Pengaturan. Perubahan memakai revisi untuk menolak formulir usang. Kode enam digit dibuat dengan RNG kriptografis dan disimpan sebagai HMAC dengan secret tersendiri; kode aktif hanya diperlihatkan sekali, berlaku 24 jam, dan dapat diganti/dicabut. Penukaran kode hanya memberikan keanggotaan peserta dan tidak membuat enrollment. Pergantian akses ke publik membatalkan kode, sedangkan anggota/progres lama tetap ada.

Seluruh **56 unit/API test lulus**. Enam pengujian tambahan memeriksa perubahan publik/privat tanpa kehilangan progres, batas izin pemilik/admin, idempotensi keanggotaan, peran pengajar yang tidak diturunkan, tidak dimulainya enrollment oleh kode, digest/audit tanpa kode mentah, rotasi/pencabutan/kedaluwarsa/arsip, invalidasi saat menjadi publik, pembatasan tebakan yang tetap tercatat pada kegagalan, format ASCII enam digit, penanganan benturan kode, dan nol di depan.

`npm.cmd run test:browser` tetap lulus tujuh kelompok alur utama. `npm.cmd run test:course-lifecycle` lulus dengan alur tambahan pada Edge/MariaDB nyata: pemilik mengubah nama/deskripsi/privasi melalui UI, siswa baru bergabung lewat formulir enam digit, kode tidak ditampilkan lagi setelah reload, kode lama ditolak setelah rotasi/pencabutan, perubahan kembali ke publik mempertahankan progres, lalu arsip/pemulihan/hapus tetap berhasil. Satu pemeriksaan awal terhenti karena dua tombol penutup dialog memiliki nama yang sama; selector pengujian diperjelas dan kelas uji tersebut dibersihkan berdasarkan ID/nama terverifikasi. Pemeriksaan akhir lulus dan kode undangan tidak dicetak atau disimpan pada screenshot/trace/HAR. Pengujian kini mencoba membersihkan kelas uji miliknya jika terjadi kegagalan.

Screenshot `artifacts/web-course-settings.png` diperiksa secara visual dan dibuat setelah kode dicabut serta dialog ditutup. Akun/kelas pengguna yang sudah ada tidak dihapus. Batas: undangan adalah kode bersama, bukan undangan satu pengguna; pencabutan anggota perlu disertai rotasi/nonaktifkan kode bila akses undangan juga ingin ditutup.

Tata letak akhir formulir dirapikan untuk desktop dan viewport 390px. Screenshot pengaturan desktop serta `artifacts/web-course-settings-mobile.png` diperbarui menggunakan kelas pratinjau sementara tanpa kode undangan, kemudian kelas tersebut dihapus. Tidak ditemukan overflow horizontal; seluruh layanan lokal tetap berjalan sehat.

## Penyelesaian TODO — Profil, pendaftaran, bahasa UI, dan akses kelas

DOMjudge ditunda atas permintaan pengguna; provider tetap adaptor cadangan dan tidak ada layanan DOMjudge yang dijalankan. Tugas lainnya di TODO sudah diimplementasikan.

Migrasi `0006` menambah nama lengkap/email unik, undangan terenkripsi, dan asal keanggotaan (`assignment`, `invite`, `public`). Migrasi `0007` memperbaiki kasus penugasan historis yang pernah dicabut agar tidak dipakai sebagai bukti akses privat saat ini. Backup sebelum masing-masing migrasi tersimpan di `.backups/before-0006.sql` dan `before-0007.sql`. Anggota publik lama perlu kode/penugasan untuk kelas yang kini privat; progres dan enrollment tidak dihapus. Urutan audit lama yang tidak dapat dipastikan diperlakukan secara konservatif, sedangkan penugasan baru dicatat eksplisit. `alembic check` pada MariaDB tidak menemukan perbedaan skema/model.

Menu Profil mendukung ubah nama lengkap/email sendiri dan password dengan verifikasi password saat ini. Username login tetap; nama lengkap menjadi nama tampilan. Password di-hash dan perubahan mencabut seluruh sesi. Pendaftaran memerlukan nama lengkap/email; email belum diverifikasi melalui pengiriman email. Akun lama dapat melengkapi profil tanpa mengganti username/password.

UI memiliki katalog lokal `web/locales/id.json` dan `en.json`, pemilih bahasa pada header/login, dan preferensi locale pada localStorage. Penerjemahan literal UI dilakukan sebelum interpolasi konten; tidak ada penggantian otomatis pada nama, materi, soal, kode, atau keluaran. Parser pengembangan membantu pemindahan literal tanpa mengubah sintaks. Bahasa dan terjemahan tidak dikirim ke layanan eksternal. Playwright diperbarui ke versi yang dipatok; audit npm melaporkan nol temuan.

Kode undangan aktif kini tampil kembali di Pengaturan pemilik/admin, termasuk setelah reload. Selain indeks HMAC, kode disimpan terenkripsi dengan Fernet; kode lama yang belum terenkripsi perlu diganti sekali. Deskripsi tampil pada paragraf halaman kelas siswa maupun pengelolaan pengajar. Siswa tidak memperoleh tab arsip dan ditolak pada URL/API kelas arsip, enrollment, leaderboard, serta histori. Kiriman ulang dengan idempotency key juga memeriksa akses terkini sehingga tidak melewati perubahan privat/arsip.

Seluruh suite **60 unit/API test lulus**. Pengujian tambahan mencakup pendaftaran lengkap, validasi nama/email dan larangan role injection; CSRF/profil milik sendiri; email unik dan nama login tetap; password salah serta pencabutan seluruh sesi; asal keanggotaan publik yang tidak dapat melewati privat; penerimaan undangan tanpa mengubah enrollment lama; pembatasan arsip siswa; kerahasiaan email pada leaderboard; dan migrasi penugasan lama yang dicabut. Pemeriksaan tambahan setelah perubahan akhir mencakup nama tampilan serta replay idempoten dan kepemilikan akun.

Pengujian browser nyata:

- `npm.cmd run test:browser`: tujuh kelompok alur utama tetap lulus setelah teks UI dipindahkan ke katalog dan menu Profil ditambahkan; penilaian C/C++, progres, leaderboard, mobile, authoring, serta logout tetap berjalan.
- `npm.cmd run test:profiles`: tiga kelompok lulus untuk pendaftaran/nama/email, penggantian bahasa yang mempertahankan teks materi/nama asli, akses privat dengan undangan, penolakan arsip, perubahan password, penolakan password lama, pencabutan sesi kedua, dan login dengan password baru. Tidak ada JavaScript error atau overflow pada 390px.
- `npm.cmd run test:course-lifecycle`: lima kelompok lulus dengan kode yang tetap tampil pada Pengaturan setelah reload, penolakan peserta publik setelah kelas menjadi privat sebelum undangan, serta arsip yang hanya dapat ditinjau pengelola. Kelas uji dibersihkan; kelas pengguna yang sudah ada dipertahankan.

Screenshot `artifacts/web-profile-en.png` dan `web-material-en-ui.png` diperiksa secara visual: kontrol berbahasa Inggris, sementara nama/isi materi Indonesia tetap utuh. Kode undangan tidak dicetak pada log/screenshot/trace/HAR. Uji end-to-end memakai akun serta kelas baru, dan tidak mengubah password akun pengguna yang sudah ada. Reset password karena lupa, verifikasi email, MFA, dan DOMjudge belum termasuk hasil implementasi ini.
# Verifikasi laporan progres dan pekerjaan peserta — 2 November 2026

- Regresi pengelolaan kelas: `npm run test:course-lifecycle` lulus lima kelompok, termasuk arsip/pemulihan, visibilitas, dan penghapusan kelas uji. Layanan API, MariaDB, Redis, serta runner sehat; worker, validator dan scheduler berjalan.
- Backend: 64 pengujian lulus, termasuk empat pengujian baru untuk agregasi lintas path, peserta belum mulai, versi enrollment tetap, isolasi histori per peserta/path, izin admin/pengajar/siswa, replay versi soal lama, serta penolakan eksekusi kelas arsip. Setelah menambah contoh eksplisit 75%, empat pengujian laporan dijalankan ulang dan lulus. Ada satu peringatan deprecation AnyIO pada TestClient, tanpa kegagalan.
- Browser nyata (Edge, MariaDB, Redis, worker dan sandbox GCC/G++): suite `npm run test:browser` lulus. Verifikasi baru menunjukkan draft tidak memengaruhi 100%, publikasi path yang belum dimulai menurunkan menjadi 50%, lalu penyelesaian separuh path kedua menghasilkan 75%, tetap satu baris per peserta.
- Melalui Learning path → Hasil peserta → Detail pengerjaan → Lihat kode, source C++ siswa terbaca, pengajar menjalankannya dengan input `20 22` dan memperoleh output `42`. Progres siswa tetap 100% pada path asli dan waktu selesai tidak berubah. Tampilan detail lulus pemeriksaan lebar seluler 390px serta perpindahan Indonesia/Inggris. Tidak ada JavaScript/CSP error atau permintaan aset pihak ketiga.
- Tangkapan layar ditinjau: `artifacts/web-class-progress.png` dan `artifacts/web-instructor-code-review.png`. Tidak ada token/password/kode undangan dalam artefak ini. Data pengujian browser berupa akun dan kelas baru tersimpan seperti pola suite sebelumnya; data pengguna yang sudah ada tidak diubah.
- Pengujian browser pertama menemukan selector tombol Tutup ambigu (dua tombol modal yang sah); selector diperjelas, lalu suite lulus seluruhnya. Tidak ada perubahan skema/migrasi database dan DOMjudge tetap ditunda.


## Hasil perbaikan audit dan review Ponytail — 3 November 2026

- Seluruh 10 temuan unik audit/review ditangani: urutan lock, transaksi audit replay, batas DELETE, kuota IP undangan, race editor, detail/pagination kelas, path tanpa langkah wajib, statistik dashboard, query laporan, dan empat baris filter siswa yang tidak terjangkau.
- Suite backend final: 72 passed, 1 skipped. Skip adalah tests/test_mariadb_concurrency.py yang membutuhkan database disposable; bukan tes gagal yang diabaikan. Satu peringatan deprecation AnyIO/TestClient tetap berasal dari dependensi.
- scripts/test-mariadb-concurrency.ps1: 1 passed pada MariaDB 11.4 nyata terpisah. Sambil admission ditahan, NOWAIT dapat mengambil kelas (membuktikan replay belum mengunci kelas); setelah dilepas, replay dan submission sama-sama 202. Container memakai tmpfs, tidak memasang port/volume aplikasi, dan berhasil dibuang.
- tests/test_audit_fixes.py memeriksa rollback audit tanpa job tertinggal, audit idempoten sekali, body DELETE besar sebelum auth, 40 undangan sah satu IP serta batas tebakan yang tidak bisa dipakai probing, detail kelas di luar 100 pertama, metadata materi/path halaman kedua, kebijakan path wajib dan versi referensi lama, serta statistik setelah 101 run.
- Laporan kelas dan path diuji dengan 41 peserta dan 200 enrollment; masing-masing dibatasi maksimal 18 SELECT, menggantikan pola query per enrollment.
- npm run test:audit-ui: 3 kelompok lulus, semua API dimock. Respons editor A ditunda hingga B terbuka, lalu B tetap menyimpan key/konten yang benar; materi di halaman kedua, pagination Kelas/Studio, detail kelas di luar halaman pertama, statistik, mobile dan English juga lulus. Tidak ada penulisan ke aplikasi nyata dalam suite ini.
- npm run test:browser: 8 kelompok lulus, mencakup validasi C/C++, Accepted nyata, progres 50%/75%, leaderboard, detail peserta, replay C++ output 42 tanpa perubahan hasil siswa, serta locale/mobile/CSP.
- npm run test:profiles: 3 kelompok lulus. npm run test:course-lifecycle: 5 kelompok lulus; hanya kelas uji baru yang dihapus. Akun/data pengguna yang sudah ada tetap dipertahankan.
- alembic check: No new upgrade operations detected. API, MariaDB, Redis, runner sehat; worker/validator/scheduler berjalan dengan versi akhir. Tidak ada dependensi baru, migrasi, atau penghapusan data lama.
- DOMjudge tetap ditunda. Peta Graphify/Obsidian ditandai sebagai snapshot sebelum perbaikan; belum dibangun ulang.

## Plugin penilaian installable — 3 November 2026

Implementasi aktif pada image lokal `44eac9f3f72151700cfc2284575dc9d034875551d388230853832a42cc5c4ccd`. Celery/Redis dan runner/sandbox tetap dipertahankan. Penilai bawaan dipindah ke `plugin/custom/provider.py`; contoh installable berada di `plugin/examples/sandbox-delegate.zip`. Tidak ada dependensi baru.

- Suite backend: **88 passed**, mencakup 16 kasus plugin; tes MariaDB opt-in dijalankan terpisah. Setelah penambahan metadata versi tervalidasi, 16 tes plugin dijalankan kembali dan seluruhnya lulus.
- MariaDB disposable: **2 passed** untuk pemulihan migrasi parsial/aditif 0008, kesesuaian metadata Alembic, serta urutan lock replay/submission. Database memakai tmpfs tanpa volume pengguna dan container dibersihkan.
- `npm run test:plugins`: 3 kelompok lulus — upload ZIP/konfirmasi trust, aktivasi/pemilihan versi, pilihan plugin saat menyimpan soal, nonaktif/uninstall, bahasa Inggris, mobile, tanpa error JS. API penulisan dalam tes browser ini ditiru; tidak memasang plugin nyata.
- `./scripts/test-integration.ps1 -Suite smoke_plugins`: 5 kelompok lulus — instalasi/discovery plugin nyata, validasi referensi C17/C++17, penilaian Accepted dan filtrasi test tersembunyi, run input 20 22 menghasilkan 42 tanpa nilai, proteksi uninstall, serta pembersihan kelas/plugin fixture baru. Data lama tidak dihapus.
- `npm run test:audit-ui`: 3 kelompok regresi editor lambat/pagination/statistik lulus.
- `npm run test:browser` final: 8 kelompok alur web/judge nyata lulus, termasuk authoring C/C++, learning path, prasyarat, leaderboard, progres, review/replay pengajar, bahasa, mobile, dan CSP. Uji ini juga memastikan koreksi label UTF-8 pada UI lama.
- Migrasi 0008 sudah diterapkan. `alembic check`: No new upgrade operations detected. API, MariaDB, Redis, dan runner sehat; worker, validator, scheduler berjalan.

Paket terpasang merupakan kode server tepercaya dan bukan sandbox untuk plugin pihak ketiga. Pemeriksaan sintaks tidak membuktikan keamanan kode. Nonaktif tidak membatalkan pekerjaan yang sudah diterima; versi lama tetap diperlukan oleh soal/histori. DOMjudge dan aturan AST pedagogis belum diimplementasikan. Peta Graphify belum dibangun ulang; lihat source dan [panduan plugin](plugin/README.md).

### Visibilitas pilihan plugin pada soal terbit

Pemeriksaan API dan browser nyata mengonfirmasi Sandbox Delegate aktif tersedia pada selector soal baru. Pada soal terbit, fieldset dinonaktifkan sehingga selector tidak dapat dibuka. UI diperjelas dengan daftar plugin aktif di luar fieldset dan tombol Ganti plugin melalui revisi yang menggunakan alur revisi yang sudah tersedia. Tidak ada soal pengguna yang diubah. Regresi browser plugin mencakup pembuatan draft dari soal terbit, pemilihan plugin pada revisi, serta perlindungan versi terbit.

## Performa konkuren 30 pengguna — 4 November 2026

Uji HTTP/Celery/sandbox nyata selesai: 30 pengguna pada satu path, 30 run, 30 submit, lalu 60 run/submit serentak. Seluruh 120 pekerjaan selesai dengan verdict yang diharapkan setelah retry admission terkontrol. Batas kelas menolak 10/30 pada setiap burst tunggal, serta 38/60 pada burst campuran awal. Pending maksimum 20, running maksimum 2, antre maksimum 53 detik. Satu RemoteProtocolError pada polling pulih pada poll berikutnya; dua peringatan runner cleanup NotFound tidak meninggalkan sandbox. Tidak ditemukan salah nilai/output atau retry eksekusi.

Laporan dan keterbatasan pengukuran: [LAPORAN_PERFORMA.md](LAPORAN_PERFORMA.md). Generator dan wrapper dapat diulang; hanya alat uji serta dokumentasi yang ditambahkan. Kelas sementara dihapus, 30 akun sementara dinonaktifkan, data lama tidak dihapus.
