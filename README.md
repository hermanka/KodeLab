# KodeLab — JudgementSystem C/C++

Fondasi platform pembelajaran C/C++ dengan API FastAPI, MariaDB, Redis, Celery, dan runner Docker. Rancangan lengkap tersedia di [RANCANGAN_PLATFORM.md](RANCANGAN_PLATFORM.md).

**Antarmuka web sudah tersedia di <http://localhost:8000/>.** Desain mengikuti [DESIGN.md](DESIGN.md). Mulai dari [Panduan Web](PANDUAN_WEB.md) untuk alur pengajar dan peserta; Swagger tetap tersedia untuk integrasi API.

Target produk adalah web dinamis: pengajar mengelola materi, soal, solusi acuan/kunci, dan learning path melalui aplikasi; peserta mengikuti urutan/prasyarat serta progres belajar. Rancangan pengelolaan konten, publikasi berversi, dan tahapan berikutnya tersedia pada dokumen tersebut. Kebutuhan keamanan dan selisih terhadap prototipe dijabarkan di [KEBUTUHAN_KEAMANAN.md](KEBUTUHAN_KEAMANAN.md).

## Status implementasi

- API submission, percobaan input bebas, polling hasil, dan dokumentasi Swagger.
- Web responsif: login/registrasi, dashboard, katalog jalur, pembaca materi, editor C/C++, riwayat, studio pengajar, akun admin, dan audit.
- Learning path berversi, langkah materi/latihan, modul, urutan, prasyarat, langkah wajib/opsional, enrollment yang dipatok ke versi, dan laporan progres kelas.
- Progres disimpan server: konfirmasi membaca atau jawaban resmi Accepted; run/jawaban salah tidak menyelesaikan latihan. Akses langsung ke langkah terkunci juga ditolak API.
- Akun student/teacher/admin, password Argon2id, sesi opaque yang disimpan sebagai hash, logout, pencabutan sesi, dan CSRF untuk akses cookie.
- Kelas privat/publik, penugasan pengajar, anggota kelas, dan kepemilikan submission.
- API authoring materi Markdown yang dirender aman, soal, kasus uji, dan solusi acuan privat.
- Draft, konflik revisi, publikasi, pembuatan versi baru, dan arsip; soal wajib lolos validasi acuan C/C++ sebelum terbit.
- Worker validasi acuan terpisah, audit tindakan sensitif, dan kuota transaksi per akun/kelas.
- Profil C17/GCC dan C++17/G++; soal `sum-v1` dengan satu contoh terbuka dan empat kasus tersembunyi.
- Judge custom dengan checker token, nilai biner, batas waktu/memori/output, dan satu container baru per Run/Submit yang digunakan kembali untuk kompilasi serta seluruh input pengujian.
- MariaDB dengan migrasi Alembic dan seed idempoten.
- Antrean berbasis attempt persisten di SQL, dispatch berkala ke Redis, lease worker, retry terbatas, dan idempotency key opsional.
- Kontrak provider dan adaptor DOMjudge cadangan. **Integrasi DOMjudge belum diimplementasikan** dan pilihan tersebut ditolak secara eksplisit.

Belum tersedia integrasi DOMjudge, nilai parsial, MFA/reset password, unggahan berkas, pemindahan enrollment ke versi path baru, atau API penilaian ulang. Gunakan untuk pengembangan lokal; layanan belum ditujukan untuk dibuka ke publik. Panduan API pengajar tersedia di [PANDUAN_PENGAJAR.md](PANDUAN_PENGAJAR.md).

## Prasyarat

- Docker Engine Linux atau Docker Desktop dengan Linux containers.
- Docker Compose v2 dan koneksi internet untuk build pertama.
- PowerShell untuk skrip pembuatan `.env` di Windows; Python host tidak diperlukan.
- Node.js hanya diperlukan bila ingin menjalankan pengujian browser; aplikasi web tidak memerlukan Node.js saat berjalan.

## Menjalankan di Windows

Jalankan dari direktori proyek:

```powershell
.\scripts\init-env.ps1
docker compose --profile tools build sandbox-image
docker compose up --build -d
docker compose ps -a
```

Skrip membuat `.env` dengan rahasia acak atau menambahkan pengaturan yang belum ada sambil mempertahankan nilai lama. Untuk sistem lain, salin `.env.example` ke `.env` lalu ganti seluruh placeholder dengan rahasia acak. Jangan commit `.env` atau `.backups/`.

Buka <http://localhost:8000/> dan login dengan username/password dari `BOOTSTRAP_ADMIN_USERNAME` dan `BOOTSTRAP_ADMIN_PASSWORD` di `.env`. Admin dapat membuat akun pengajar/peserta melalui menu **Administrasi**. Setelah itu pengajar dapat membuat seluruh konten melalui **Studio pengajar**. Halaman **Buat akun** pada layar masuk hanya mendaftarkan peserta.

Untuk Swagger di <http://localhost:8000/docs>, jalankan `POST /auth/login`, salin `access_token`, klik **Authorize**, dan masukkan token tanpa awalan `Bearer`. Token API bersama `API_TOKEN`/`X-API-Key` sudah tidak diterima. Jika port tersebut sudah dipakai, ubah `API_PORT` sebelum menjalankan Compose.

Bootstrap membuat admin pertama saat migrasi dan tidak mengganti password akun yang sudah ada. Mengubah password bootstrap di `.env` bukan cara mereset password akun. Untuk instalasi yang sudah berjalan, jalankan ulang skrip inisialisasi lalu `docker compose up --build -d` agar seluruh migrasi hingga `0007` diterapkan. Skrip juga menambah `CLASS_INVITE_SECRET` acak bila belum ada, tanpa mengganti rahasia lama. Data lama dipertahankan. Sembilan submission prototipe tanpa pemilik tetap hanya dapat dibaca admin yang mengetahui ID-nya.

Instalasi baru dimulai tanpa jalur belajar. Pengajar membuat materi/soal, menguji kunci, menerbitkan konten, lalu menyusun dan menerbitkan learning path. Pada workspace pengembangan ini, pengujian browser sudah membuat contoh publik **Dasar Pemrograman C/C++** dengan materi input/output, soal penjumlahan, dan refleksi opsional. Contoh tersebut berisi data nyata yang bisa dipelajari atau dikelola admin.

Siswa membuka menu **Kelas**, memilih **Buka kelas**, lalu memilih learning path di dalamnya. Jalur dan materi/latihan menyediakan breadcrumb kembali ke kelas. `GET /courses/{id}/learning` menampilkan jalur terbit pada kelas tersebut dan enrollment milik pengguna sendiri; akses kelas privat, prasyarat, serta versi progres tetap diperiksa server.

Menu Kelas dan Studio pengajar membuka **Kelas aktif** secara default; tab **Arsip kelas** memisahkan arsip yang hanya dapat ditinjau admin/pengajar sesuai izin. Siswa tidak dapat membuka arsip atau histori kelas arsip. Pemilik/admin dapat memulihkan atau menghapus dari tab arsip. Filter API `GET /courses?status=active` atau `status=archived` diterapkan sebelum pagination dan tidak memperluas izin akses.

Pemilik/admin dapat mengubah nama, deskripsi, dan publik/privat melalui **Kelola kelas → Pengaturan**. Pada kelas privat, kode undangan enam digit berlaku 24 jam dan dapat diganti/dinonaktifkan. Peserta memakai **Kelas → Gabung dengan kode**. Kode aktif tampil di Pengaturan pemilik/admin, disimpan terenkripsi dengan indeks HMAC, dan tidak masuk daftar kelas/log audit. API pengaturan: `GET/PATCH /courses/{id}/settings` (PATCH menyertakan `title`, `description`, `is_public`, `edit_revision`); kode: `POST/DELETE /courses/{id}/invitation`; bergabung: `POST /courses/join` dengan body `{"code":"012345"}`. Perubahan akses mempertahankan progres, tetapi anggota yang hanya masuk otomatis dari publik harus memperoleh undangan/penugasan agar bisa mengakses kelas privat; publik menonaktifkan kode. Pergantian `CLASS_INVITE_SECRET` membatalkan seluruh kode lama dan memerlukan pembuatan kode baru, tanpa mengubah keanggotaan.

Database, Redis, dan runner berada pada jaringan internal dan tidak memiliki port host. API juga terhubung ke jaringan ingress agar Docker Desktop dapat memublikasikan port pada loopback `127.0.0.1`. Layanan `migrate` selesai dengan exit code 0 sebelum API dan worker dimulai; ini perilaku normal.

## Profil dan bahasa UI

Peserta mendaftar dengan nama lengkap serta email; username tetap digunakan untuk login. Menu Profil mendukung ubah nama/email dan password dengan verifikasi password saat ini. Perubahan password mencabut seluruh sesi. API: `PATCH /auth/profile` dengan `full_name,email`; `POST /auth/password` dengan `current_password,new_password`. Email belum diverifikasi melalui pengiriman email.

Pemilih Indonesia/English tersedia pada header. Katalog JSON berada di `web/locales/id.json` dan `en.json`; hanya literal UI yang diterjemahkan, bukan materi/kode/nama dari database. Preferensi bahasa disimpan lokal tanpa token/password. Jalankan `npm.cmd run test:profiles` untuk memeriksa pendaftaran, profil/password, bahasa, dan batas akses privat/arsip pada browser nyata. DOMjudge ditunda sesuai permintaan pengguna.

## Mencoba API

Peserta membuka konten lewat `GET /enrollments/{id}/steps/{step_id}`. Latihan mandiri telah dihapus; `GET /problems` bagi peserta mengembalikan daftar kosong dan pengiriman tanpa konteks learning path ditolak. Endpoint soal generik tetap tersedia bagi staf untuk inspeksi/diagnostik judge. Contoh body `POST /submissions` peserta (ganti seluruh ID dengan ID aktual dari enrollment):

```json
{
  "problem_version_id": "<versi-soal>",
  "enrollment_id": "<uuid-enrollment>",
  "path_step_id": "<uuid-langkah>",
  "language": "cpp17",
  "source": "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<'\\n';}"
}
```

API mengembalikan HTTP 202 dan ID submission. Baca `GET /submissions/{id}` sampai `state` menjadi `completed` atau `system_error`. Pekerjaan dikirim ke worker langsung setelah tersimpan; scheduler (tiap 1 detik) hanya menjadi cadangan bila pengiriman itu gagal. Nilai 100 diberikan jika semua kasus lolos; nilai 0 untuk jawaban gagal. Gangguan sistem tidak menghasilkan nilai.

Gunakan `POST /runs` dengan body yang sama ditambah `"input": "40 2\n"` untuk mencoba input sendiri. Hasil sukses berstatus `EXECUTED`, memiliki output, dan tidak diberi nilai.

Pasangan `enrollment_id` dan `path_step_id` wajib berasal dari enrollment milik peserta. Backend memeriksa kepemilikan, versi soal, bahasa, dan prasyarat. GET `/enrollments/{id}/steps/{step_id}` memberikan konten hanya jika langkah terbuka. POST `/enrollments/{id}/steps/{step_id}/complete` hanya berlaku untuk konfirmasi membaca. Completion latihan dibuat secara atomik oleh worker saat jawaban resmi Accepted; browser tidak boleh menetapkan nilai atau progres.

Menu **Leaderboard** menampilkan satu peringkat keseluruhan melalui `GET /leaderboards`, tanpa pemilih kelas/jalur. Leaderboard kelas langsung tertanam pada halaman kelas melalui `GET /courses/{course_id}/leaderboard`, tersedia bagi admin, pengajar, dan siswa sesuai izin kelas. Nilai kelas menjumlahkan nilai jalur (maksimal 100 per jalur); nilai sama dibandingkan dengan total durasi penyelesaian tercepat. Leaderboard per jalur dan endpoint lamanya sudah dihapus. Aturan nilai, waktu, versi, dan akses dijelaskan pada [PANDUAN_WEB.md](PANDUAN_WEB.md).

Di **Studio pengajar**, pemilik kelas/admin dapat **Arsipkan kelas**, **Pulihkan kelas**, atau **Hapus kelas** beserta seluruh data akademiknya. API: `POST /courses/{id}/archive`, `POST /courses/{id}/restore`, serta `DELETE /courses/{id}` dengan body `{"confirmation_title":"nama kelas persis"}`. Hapus bersifat permanen dan ditolak saat ada pekerjaan penilaian berjalan; arsip mempertahankan histori/progres sebagai data hanya-baca. Akun pengguna, kelas lain, dan audit administratif tetap dipertahankan.

Header opsional `Idempotency-Key` harus berupa UUID dan berlaku per pemilik. Mengulang permintaan dengan key dan body yang sama mengembalikan submission sebelumnya; body berbeda dengan key sama ditolak HTTP 409. Peserta tidak dapat melakukan override provider; server memilih mesin sesuai konfigurasi soal/kelas/default.

Endpoint data memakai `Authorization: Bearer <access_token>` atau sesi cookie. Untuk cookie, operasi perubahan data memerlukan `X-CSRF-Token` dari respons login/cookie `judgement_csrf`, dengan origin yang diizinkan. Sesi memiliki idle timeout 30 menit dan batas absolut 12 jam. `GET /health/live` dan `/health/ready` tidak memerlukan token. Registrasi mandiri hanya membuat akun student; admin membuat teacher/admin melalui `/admin/users`.

Batas sumber kode/input adalah 32 KiB UTF-8 dan body API 2 MiB. Admission dilindungi lock transaksi MariaDB: maksimal 50 pekerjaan penilaian tertunda global, 10 tertunda/40 per jam per akun, dan 20 tertunda/200 per jam per kelas. Validasi acuan dibatasi 2 tertunda/10 per jam per pengajar, 4 tertunda/20 per jam per kelas, serta 10 tertunda global. Nilai batas masih konstanta pengembangan. Belum ada kuota penyimpanan total atau penagihan waktu komputasi.

## Verifikasi

Perbaikan audit Ponytail: replay dan audit disimpan atomik dengan urutan lock admission sebelum kelas; batas body juga mencakup DELETE. Kuota undangan IP menghitung tebakan gagal dan dicek sebelum pencocokan kode, sehingga satu kelas dapat bergabung dari IP yang sama. Halaman Kelas/Studio, anggota, materi/soal dan path memiliki pagination; detail kelas memakai `GET /courses/{id}`, dan Studio memfilter `managed=true` sebelum limit. Statistik latihan berhasil memakai `GET /my/stats` yang menghitung semua Accepted sesuai izin, bukan riwayat 100 kiriman terakhir. Laporan progres memakai pembacaan batch. Publikasi path memerlukan satu langkah wajib; path referensi lama tetap tersimpan dan tidak mengurangi progres kelas.

Tambahan pemeriksaan: `npm.cmd run test:audit-ui` menggunakan API tiruan untuk race editor/pagination tanpa menulis ke data pengguna. `scripts/test-mariadb-concurrency.ps1` menjalankan tes urutan lock pada MariaDB sementara dengan data tmpfs, tanpa port host atau volume database aplikasi, kemudian membuang container tersebut. Pengujian ini tidak memerlukan dependensi baru.

```powershell
docker compose run --rm --no-deps api python -m pytest -q -p no:cacheprovider
.\scripts\test-integration.ps1 -Suite smoke
.\scripts\test-integration.ps1 -Suite smoke_authoring
```

Smoke test menggunakan seluruh layanan nyata dan menulis submission uji ke MariaDB: solusi C/C++ benar, hardcoded, gagal kompilasi, runtime error, loop tak berujung, output berlebihan, input bebas, idempotensi, penyembunyian output kasus privat, serta pemeriksaan UID, filesystem read-only, dan ketiadaan Docker socket/kredensial di sandbox.

Skrip PowerShell mengirim kredensial bootstrap melalui stdin, tidak melalui argumen perintah atau log. Suite authoring membuat akun/kelas/data uji dan memeriksa publikasi materi, acuan C/C++, pembatasan akses, penolakan kunci salah, serta admission 12 request serentak. Data uji dipertahankan untuk penelusuran audit.

Pengujian browser nyata menggunakan Microsoft Edge yang sudah terpasang:

```powershell
npm.cmd ci --ignore-scripts
npm.cmd run test:browser
```

Browser berjalan headless. Skrip membaca rahasia admin dari `.env` hanya ke memori, membuat akun pengajar/peserta uji, menjalankan seluruh alur UI hingga progres 100%, dan menyimpan screenshot lokal ke `artifacts/`. Font, JavaScript, dan CSS dilayani dari aplikasi sendiri; tidak ada permintaan ke CDN pada UI.

Hasil verifikasi: **33 pengujian unit/API**, **9 skenario judge**, **5 kelompok authoring/integrasi**, dan **6 kelompok alur browser** lulus. `alembic check` pada MariaDB tidak menemukan perbedaan skema. Rincian tersedia di [VERIFIKASI.md](VERIFIKASI.md).

Untuk melihat log tanpa membuka rahasia:

```powershell
docker compose logs --tail=100 worker validator runner scheduler
```

Hentikan layanan tanpa menghapus data:

```powershell
docker compose down
```

Volume database dan Redis dipertahankan. Jika kredensial `.env` diganti setelah database diinisialisasi, pengguna database yang ada tidak otomatis berubah; lakukan perubahan kredensial terencana pada database.

## Batas isolasi dan keandalan

Runner adalah komponen tepercaya yang memiliki Docker socket dan dapat mengontrol host Docker. API serta worker Celery tidak mendapat socket tersebut. Untuk deployment publik, penuhi persyaratan tersisa pada dokumen keamanan, termasuk host judge khusus, HTTPS, MFA pengelola, manajemen rahasia, backup/restore teruji, dan penguatan isolasi. Aktifkan `SESSION_COOKIE_SECURE=true` saat menggunakan HTTPS; nilai false hanya untuk localhost HTTP.

Container peserta memakai UID non-root, jaringan `none`, filesystem dasar read-only, tmpfs terbatas, drop seluruh capabilities, no-new-privileges, seccomp default Docker, batas proses, satu CPU, memori/swap, dan log terbatas. Tidak ada mount direktori host atau kredensial di container peserta. Checker dan jawaban acuan tetap di luar sandbox. Kompilasi mendapat 512 MiB; eksekusi soal awal mendapat 128 MiB dan dua detik waktu CPU (`RLIMIT_CPU`); jam dinding hanya pengaman sebesar 3 × batas + 2 detik untuk program yang tidur atau macet. Validasi acuan menjalankan kunci dengan separuh batas waktu (minimal 1 detik) agar jawaban sama cepat tidak terkena TLE saat server ramai. Kapasitas bawaan 6 worker penilaian dan 7 slot runner (6 + 1 validator), disesuaikan dengan 6 core fisik host pengembangan; ukur ulang dengan `docker info` bila host berbeda. Kompilasi serta runtime memakai image GCC yang sama pada tahap awal; image runtime minimal terpisah dapat ditambahkan kemudian.

Runner menggunakan satu container fisik `js-<attempt_id>` sepanjang satu Run/Submit. Proses container selesai lalu di-start kembali untuk kompilasi dan setiap input; ruang PID dan tmpfs dibersihkan antar-fase. Binary hasil kompilasi disimpan sementara di pengendali dan dikirim ulang ke proses runtime, sehingga kode tidak dapat meninggalkan file atau proses untuk input berikutnya. Batas memori disesuaikan sebelum setiap start. Stream output dipasang sebelum start tanpa membaca log fase sebelumnya. Container dihapus sekali dalam `finally` setelah pekerjaan selesai atau mengalami kegagalan infrastruktur; container yatim kedaluwarsa setelah 180 detik. Penggunaan ulang ini mengurangi create/remove, tetapi tidak menghilangkan start proses, transfer binary, atau inspeksi Docker. Container tidak dipertahankan untuk klik Run/Submit berikutnya.

Image protokol ini adalah `judgementsystem-sandbox:gcc12-v3` (v3 menambah batas waktu CPU); bangun image sandbox dan aplikasi sebelum memperbarui runner. Pengujian Docker khusus dapat dijalankan dengan `docker compose run --rm --no-deps -T -e RUN_SANDBOX_TESTS=1 runner python -m pytest tests/test_sandbox_reuse.py -q -p no:cacheprovider`. Pengujian ini memverifikasi ID container yang sama, cleanup, input/output, batas sumber daya, dan isolasi file/proses antar-input; tidak membuat akun/kelas. Perilaku tmpfs saat stop/restart dijelaskan pada [dokumentasi Docker](https://docs.docker.com/engine/storage/tmpfs/).

Waktu hasil adalah waktu nyata pengendalian container, bukan waktu CPU algoritma atau metrik kompetisi yang presisi. OOM dilaporkan sebagai batas memori hanya jika Docker mengonfirmasinya; alokasi memori yang ditolak lalu berakhir error dapat muncul sebagai runtime error. Compiler diagnostics dibatasi 16 KiB; executable maksimal 2 MiB. Output runtime stdout/stderr gabungan dibatasi 64 KiB per kasus. Image menggunakan tag versi, dan digest image sandbox aktual dicatat pada hasil; dependensi transitif serta paket OS belum dikunci penuh untuk build yang identik.

Runner menunggu pemberitahuan selesai melalui `container.wait(condition="not-running")`, tanpa loop inspeksi status setiap 25 ms. Timer terpisah menghentikan container ketika batas waktu tercapai, dan pembaca stdout/stderr menghentikannya jika output melebihi batas. Timer dibatalkan serta ditunggu sebelum beralih ke input berikutnya agar tidak menghentikan proses berikutnya. Satu inspeksi akhir mengambil exit code dan status OOM; inspeksi tambahan hanya diperlukan bila penghentian beradu dengan program yang sudah selesai. Kesalahan komunikasi/pengawasan menjadi kegagalan infrastruktur, bukan nilai peserta. Pemeriksaan container yatim berkala tetap terpisah dari pengawasan ini. Lihat [kontrak wait Docker SDK](https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.wait).

Worker memakai lease SQL 180 detik; attempt yang ditinggalkan dijadwalkan ulang dengan maksimal dua percobaan ulang. Runner mencegah attempt yang sama berjalan bersamaan dalam prosesnya dan membersihkan container berlabel proyek yang kedaluwarsa. Pengulangan eksekusi setelah crash masih mungkin, tetapi hasil attempt diperbarui menggunakan lease token agar hasil worker lama tidak menimpa yang baru. Belum ada penyimpanan permanen hasil di runner ataupun audit payload mentah lengkap. Hasil API menyimpan keluaran kasus terbuka dan ringkasan kasus tersembunyi.

Penerimaan Run/Submit melakukan preflight izin/bahasa/provider tanpa mengambil lock tulis, kemudian melepas transaksi baca dan koneksi sebelum health check serta persiapan provider. Setelah itu barulah admission mengambil lock global, memeriksa ulang izin/enrollment/status/provider, memeriksa kuota, dan menyimpan submission+attempt+audit secara atomik. Urutan lock tetap admission sebelum enrollment/kelas. Jika provider/revisi berubah selama preflight, request ditolak 409 agar dapat diulang; retry idempoten yang sudah tersimpan tetap dapat dibaca ketika runner offline. Tidak ada perubahan kuota atau penghapusan transaksi.

Validasi acuan memakai antrean `validation` dengan satu worker, lease 360 detik, dan maksimal dua retry. Worker submission hanya mengambil antrean `celery`. Runner menyediakan tiga slot untuk dua pekerjaan peserta dan satu validasi. Keluaran validasi bersifat privat dan tidak digunakan sebagai nilai peserta. Publikasi tidak otomatis dilakukan setelah validasi. Audit saat ini tersimpan di database yang sama dan belum memiliki jaminan penyimpanan tahan perubahan oleh operator database.

UI memakai cookie HttpOnly dan CSRF; access token tidak disimpan di localStorage/sessionStorage. Draft kode milik peserta disimpan sementara di sessionStorage berdasarkan identitas, langkah, dan bahasa, lalu dibersihkan saat logout. Progres resmi disimpan di MariaDB. Editor mendukung input kode, nomor baris, indentasi Tab, pergantian C/C++, dan shortcut menjalankan; autocomplete/debugger belum tersedia.

Enrollment mempertahankan versi path saat pertama mengikuti jalur; penerbitan versi baru tidak memindahkan peserta lama. Semua versi path terbit bersifat immutable. Konten yang telah dipatok peserta tetap dapat dipelajari ketika revisi baru terbit; arsip mencegah penggunaan baru. Pencabutan keanggotaan kelas tetap memblokir akses dan pengiriman baru. Migrasi enrollment lintas versi belum disediakan.

## Struktur

```text
app/             API, model MariaDB, kontrak provider, adaptor, dan tugas Celery
web/             UI lokal, CSS sesuai DESIGN.md, JavaScript modul, dan font berlisensi terbuka
runner/          Pengendali Docker internal dan checker
sandbox/         Image compiler serta bootstrap kompilasi/eksekusi
migrations/      Migrasi Alembic
scripts/         Inisialisasi lingkungan dan smoke test integrasi
artifacts/       Screenshot dan ringkasan pengujian browser lokal, diabaikan Git
tests/           Pengujian checker, kontrak, dan kerahasiaan hasil
compose.yaml     Layanan pengembangan lokal
```

## Plugin penilaian yang dapat dipasang

Penilai bawaan berada di `plugin/custom/`. Admin dapat memasang paket ZIP API v1 melalui **Plugin penilaian**, tanpa mengubah registry inti atau restart worker. Contoh paket dan panduan pengembangan tersedia di [plugin/README.md](plugin/README.md). Penyimpanan paket berversi memakai MariaDB; tidak ada dependensi baru.

Terapkan migrasi `0008` sebelum menjalankan image baru. Soal terbit, validasi, dan kiriman mengunci revisi plugin. Menonaktifkan plugin menolak pekerjaan baru; pekerjaan yang sudah diterima tetap diproses. Histori tidak dihapus ketika plugin dinonaktifkan.

Verifikasi tambahan:

```powershell
docker compose run --rm --no-deps api python -m pytest tests/test_judge_plugins.py -q -p no:cacheprovider
npm run test:plugins
./scripts/test-integration.ps1 -Suite smoke_plugins
```

Plugin adalah kode tepercaya dengan akses proses worker. Installer memeriksa format dan sintaks, bukan membuktikan keamanan source. DOMjudge dan pemeriksaan AST pedagogis tetap belum diimplementasikan.
