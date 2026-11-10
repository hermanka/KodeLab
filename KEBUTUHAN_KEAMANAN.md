# Kebutuhan Keamanan Platform Pembelajaran C/C++

Status: persyaratan rancangan dan acuan pengujian; **bukan pernyataan bahwa seluruh kontrol sudah tersedia**.  
Tanggal: 30 Oktober 2026.  
Dokumen terkait: [Rancangan platform](RANCANGAN_PLATFORM.md), [status implementasi](README.md), dan [verifikasi fondasi](VERIFIKASI.md).

## 1. Tujuan, aset, dan batas kepercayaan

Platform memproses konten pengajar dan mengeksekusi kode C/C++ dari pengguna. Keamanan mencakup aplikasi web, proses publikasi, kebenaran nilai/progres, kerahasiaan kunci, serta host judge.

Aset yang dilindungi: akun/sesi, keanggotaan kelas, materi privat, solusi acuan, kasus uji tersembunyi, kode peserta, nilai/progres resmi, kredensial integrasi, database, dan host Docker.

Ancaman utama:

- Pengguna membaca atau mengubah objek milik pengguna/kelas lain dengan mengganti ID.
- Akun pengajar disalahgunakan untuk membocorkan kunci, mengubah nilai, atau mengunggah konten berbahaya.
- HTML/JavaScript dalam materi, kode, nama berkas, atau output menyerang browser pengguna.
- Program peserta/solusi acuan menghabiskan sumber daya, menyerang runtime, atau mengakses rahasia.
- Permintaan massal, unggahan besar, dan pengujian paket membanjiri antrean atau penyimpanan.
- Manipulasi permintaan, event ganda, dan perubahan versi memalsukan kelulusan/progres.

Browser, semua kode C/C++, unggahan, serta data dari provider diperlakukan sebagai masukan tidak tepercaya. Pengajar berwenang mengelola konten tertentu, tetapi tidak diberi akses shell, Docker socket, atau kredensial layanan.

Gunakan [OWASP ASVS 5.0](https://asvs.owasp.org/) sebagai acuan verifikasi dengan target kontrol Level 2 yang relevan untuk aplikasi publik ini. Buat pemetaan kontrol saat implementasi; dokumen ini tidak mengklaim kepatuhan penuh atau sertifikasi ASVS.

## 2. Prioritas penerapan

| Prioritas | Batas penggunaan | Kebutuhan |
|---|---|---|
| P0 | Sebelum dipakai banyak pengguna dengan data privat | Identitas per pengguna, otorisasi objek, pemisahan kunci, kuota, integritas nilai/progres, audit, dan isolasi kode |
| P1 | Sebelum tersedia melalui internet | Seluruh P0, HTTPS/sesi aman, CSRF/XSS, unggahan aman, MFA pengelola, pemisahan host judge, pembaruan dependensi, backup/pemulihan, serta pengujian keamanan |
| P2 | Peningkatan operasional berkelanjutan | Isolasi tambahan sesuai risiko, pengujian penetrasi berkala, deteksi penyalahgunaan lanjutan, dan penyesuaian kapasitas |

P1 tidak berarti kontrol boleh ditunda jika fiturnya sudah digunakan: sanitasi wajib sejak editor materi tersedia, dan upload aman wajib sejak endpoint unggahan diaktifkan. Kontrol yang belum tersedia harus menyebabkan fitur terkait dibatasi atau dinonaktifkan pada lingkungan yang membutuhkan kontrol tersebut.

## 3. Matriks izin minimum (SEC-01)

| Operasi | Peserta | Pengajar | Administrator |
|---|---|---|---|
| Membaca materi terbit | Sesuai akses kelas/path | Sesuai akses kelas/konten | Sesuai tugas administratif |
| Membaca draft | Tidak | Konten milik/penugasannya | Akses administratif tercatat |
| Mengubah materi, soal, dan path | Tidak | Konten dengan izin penyuntingan | Sesuai hak administratif |
| Membaca/mengubah kunci privat | Tidak | Soal dengan izin pengelolaan kunci | Akses khusus tercatat |
| Menerbitkan revisi | Tidak | Dengan izin publikasi, setelah validasi | Sesuai hak administratif |
| Mengirim program | Untuk akun sendiri dan langkah yang terbuka | Preview/validasi pada konten yang dikelola | Sesuai kebutuhan pengujian |
| Membaca submission | Milik sendiri | Peserta di kelas yang ditugaskan | Akses administratif tercatat |
| Mengubah nilai resmi | Tidak | Hanya lewat prosedur koreksi/rejudge berwenang | Prosedur yang sama dengan audit |
| Mengubah peran/provider/rahasia | Tidak | Tidak; hanya memilih provider yang telah diizinkan | Ya, sesuai izin operasional |

Tolak secara default. Periksa peran, kepemilikan, penugasan, status publikasi, dan keanggotaan pada setiap endpoint, unduhan, serta ekspor. UUID bukan mekanisme otorisasi. Gunakan daftar field yang boleh diubah; abaikan/tolak input seperti `owner_id`, `role`, `score`, `completed`, dan `provider` yang tidak boleh dipilih pemanggil. Pilihan provider resmi ditentukan server.

Acuan: [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## 4. Identitas, autentikasi, dan sesi (SEC-02)

- Ganti token API bersama prototipe dengan identitas per pengguna sebelum P0; akun peserta tidak dapat mendaftarkan dirinya sebagai pengajar/admin.
- Hash password menggunakan Argon2id dengan salt unik dan parameter yang memenuhi panduan OWASP serta pengukuran mesin target. Jangan menyimpan password plaintext atau enkripsi password yang dapat dibalik.
- Terapkan pembatasan login/pemulihan dan pesan kegagalan yang tidak mengungkap keberadaan akun. Token reset harus acak, disimpan sebagai hash, sekali pakai, serta kedaluwarsa.
- Administrator wajib memakai MFA sebelum akses publik; terapkan MFA juga pada pengajar yang memiliki akses publikasi/kunci. Pemulihan MFA harus tercatat dan tidak boleh menjadi jalan pintas mengambil alih akun.
- Operasi perubahan peran, kredensial, dan pengaturan sensitif memerlukan autentikasi ulang sesuai kebijakan; penonaktifan akun mencabut sesi aktif.

Acuan: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Kebijakan MFA dan pemisahan peran di atas merupakan kebutuhan produk ini.

Untuk web pihak pertama, gunakan sesi server dengan cookie `HttpOnly`, `Secure` pada HTTPS, dan `SameSite` yang sesuai alur aplikasi. Rotasi ID sesi setelah login/perubahan hak, sediakan logout yang mencabut sesi, dan terapkan idle timeout serta absolute timeout di server. Jangan menyimpan token sesi jangka panjang di localStorage atau URL. Endpoint yang mengubah data dengan autentikasi cookie harus memiliki perlindungan CSRF, termasuk pemeriksaan origin dan token CSRF; `SameSite` bukan satu-satunya kontrol. Gunakan CORS dengan origin spesifik dan kebijakan credential yang ketat.

Acuan: [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## 5. Perlindungan kunci dan data peserta (SEC-03)

- Pisahkan skema respons peserta dari skema authoring: solusi acuan, input/output tersembunyi, checker privat, dan payload mentah provider tidak masuk respons peserta.
- Lindungi kunci pada API detail, daftar, pencarian, preview, ekspor, unduhan, cache, dan pesan error. Menyembunyikan tombol di UI tidak cukup.
- Penyimpanan kunci/artefak privat tidak berada di direktori publik. Unduhan memerlukan otorisasi; tautan akses sementara dibatasi masa berlaku dan cakupannya jika digunakan.
- Browser peserta tidak menerima seluruh paket uji untuk menjalankan judge lokal. Sandbox hanya menerima input kasus saat itu, tanpa expected output, solusi acuan, atau kredensial.
- Keluaran dan log kasus tersembunyi disaring sebelum disimpan sebagai hasil yang dapat dibaca peserta. Sanitasi juga log validasi pengajar agar tidak bocor lewat monitoring umum.
- Submission peserta dan statistik kelas bersifat privat secara default. Leaderboard yang diaktifkan membagikan username, nilai, jumlah penyelesaian, dan durasi bagi pengguna terautentikasi sesuai akses kelas: publik, anggota/pengelola kelas privat, atau admin. Kode, kunci, kasus tersembunyi, email, dan rahasia sesi tidak masuk respons leaderboard. Akun nonaktif dan keanggotaan yang dicabut tidak diperingkatkan. Agregat keseluruhan wajib memfilter akses sebelum menjumlahkan nilai agar data kelas privat tidak bocor.
- Nilai leaderboard hanya berasal dari completion resmi, bukan angka dari browser. Waktu mulai/selesai memakai timestamp enrollment dan completion di server; pengiriman ulang serta langkah opsional tidak memperbarui waktu selesai. Akses latihan peserta selalu memerlukan enrollment dan langkah terbuka.
- Halaman/payload sensitif memakai kebijakan cache privat atau `no-store` sesuai kebutuhan; cache bersama dipisahkan menurut identitas dan izin. Perubahan izin harus membatalkan akses berikutnya.

## 6. Konten dinamis, XSS, dan unggahan (SEC-04)

Materi menggunakan Markdown atau editor dengan daftar elemen/atribut yang diizinkan. HTML mentah, script, event handler, URL `javascript:`, iframe, dan embed aktif dinonaktifkan pada versi awal. Sanitasi hasil rendering di server dan lakukan output encoding sesuai konteks. Kode, compiler log, dan output program ditampilkan sebagai teks. CSP membatasi sumber skrip serta embed; jangan mengandalkan CSP sebagai pengganti sanitasi. Jangan memasukkan HTML pengguna lewat mekanisme rendering yang melewati escaping.

Acuan: [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).

Jika unggahan diaktifkan:

- Batasi jenis, ukuran, jumlah, dan kuota penyimpanan; cocokkan ekstensi, signature/MIME, dan kebutuhan konten. MIME dari browser tidak dipercaya.
- Versi awal dapat membatasi gambar ke PNG/JPEG dan data uji ke teks. SVG/HTML aktif dan executable yang diunggah tidak dilayani sebagai konten web.
- Gunakan nama objek acak; tolak traversal path dan penimpaan berkas. Simpan di area privat atau origin statis terpisah yang tidak menjalankan konten pengguna.
- Impor ZIP memerlukan batas ukuran setelah ekstraksi, jumlah file, kedalaman, dan rasio kompresi; tolak path absolut, `..`, symlink/hardlink, dan ZIP bomb.
- Pemroses berkas berjalan dengan hak terbatas; pindai unggahan bila relevan. Seluruh endpoint upload/download memeriksa kepemilikan.

Acuan: [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

Pengambilan materi/paket dari URL eksternal dinonaktifkan pada versi awal. Jika ditambahkan, cegah SSRF dengan validasi tujuan, IP hasil resolusi, redirect, skema, dan pembatasan jaringan. URL provider hanya dapat diatur administrator melalui konfigurasi tujuan yang diizinkan.

## 7. Isolasi eksekusi dan batas sumber daya (SEC-05)

- Kode peserta dan solusi acuan pengajar sama-sama dijalankan sebagai kode tidak tepercaya. Tidak ada eksekusi C/C++, shell command, template executable, atau checker unggahan langsung di proses API/worker aplikasi.
- Buat satu container sandbox baru per pekerjaan Run/Submit dengan non-root, jaringan nonaktif, filesystem dasar read-only, ruang sementara terbatas, drop capabilities, no-new-privileges, serta profil syscall yang diuji. Untuk penggunaan ulang dalam pekerjaan yang sama, setiap kompilasi/input memakai proses container baru melalui stop/start; ruang PID dan tmpfs wajib bersih, seluruh proses turunan dihentikan, dan batas memori/output/waktu diterapkan kembali. Container tidak dibagi antarpengguna atau antarpekerjaan.
- Terapkan batas waktu nyata, CPU, memori/swap, proses, file, output gabungan, ukuran executable, dan anggaran total submission. Batas maksimum ditentukan administrator; pengajar hanya memilih dalam rentang yang diizinkan.
- Jangan memasang host path sensitif, Docker socket, token, database, paket kunci, atau checker ke sandbox. Perintah compiler berasal dari profil tepercaya, tanpa shell interpolation dari input pengguna.
- Hentikan seluruh proses turunan serta bersihkan container/artefak setelah selesai, timeout, pembatalan, atau crash. Tetapkan label kepemilikan dan tenggat agar pembersihan tidak menyentuh pekerjaan lain.
- Runtime, compiler, library, dan kernel harus diperbarui. Untuk publik, tempatkan judge pada host khusus dengan akses jaringan minimum; uji isolasi lebih kuat sesuai risikonya.
- DOMjudge harus dikonfigurasi dan diuji sebagai sistem terpisah, termasuk izin judgehost. Jangan menganggap kontrol custom otomatis berlaku pada DOMjudge.

## 8. Kuota dan pencegahan penyalahgunaan (SEC-06)

- Kuota server per akun dan kelas mencakup laju submission/run, pekerjaan paralel, pekerjaan tertunda, waktu komputasi, jumlah kasus, validasi solusi acuan, serta penyimpanan.
- Tambahkan batas IP pada endpoint publik/login sebagai lapisan tambahan, dengan mempertimbangkan peserta di jaringan bersama. IP bukan identitas pengguna.
- Pengecekan kuota harus atomik saat ada permintaan bersamaan. Batas antrean perkiraan prototipe tidak dianggap sebagai kuota keras.
- Terapkan pagination, batas rentang ekspor, batas request termasuk transfer chunked, dan tenggat pemrosesan.
- Prioritaskan antrean secara adil; validasi paket pengajar tidak boleh menghabiskan semua kapasitas submission peserta.
- Tampilkan penolakan yang jelas tanpa membuat nilai nol. Sediakan penghentian penerimaan pekerjaan saat overload dan tindakan administratif terhadap penyalahgunaan yang tercatat.

## 9. Integritas konten, penilaian, dan progres (SEC-07)

- Pengguna tidak boleh menetapkan nilai/verdict/kelulusan lewat request browser. Backend memverifikasi bahwa hasil provider berasal dari layanan yang diizinkan dan merujuk attempt aktif yang tepat.
- Endpoint runner internal diautentikasi dan tidak dipublikasikan. Jika lintas host, gunakan TLS serta autentikasi antar layanan yang sesuai, misalnya mTLS; jangan menerima callback hasil anonim.
- Bekukan versi soal, path, profil compiler, checker, dan kebijakan nilai pada konteks pekerjaan/enrollment. Validasi nomor revisi dan gunakan transaksi untuk publikasi agar referensi tidak setengah terbit.
- Periksa prasyarat serta akses pada endpoint materi, submission, run, dan unduhan yang terkait langkah. Tolak siklus prasyarat saat authoring/publikasi.
- Terapkan idempotensi, lease, dan penguncian/transaksi agar event ganda, worker lama, atau permintaan paralel tidak menggandakan nilai/progres.
- Run, draft, gagal validasi, atau gangguan infrastruktur tidak menambah kelulusan. Koreksi/rejudge harus membuat attempt/riwayat baru dan menetapkan hasil resmi secara eksplisit.
- Perubahan peran, kunci, publikasi, bobot, batas, provider, nilai resmi, dan migrasi progres dicatat dalam audit dengan aktor, waktu, objek/versi, hasil, serta ringkasan perubahan yang aman.

## 10. Aplikasi, database, dan operasional (SEC-08)

- Gunakan query terparameterisasi/ORM dan daftar field yang diizinkan; jangan membangun SQL, shell, atau path dari input mentah. Tampilkan pesan error umum ke pengguna dengan ID korelasi, bukan traceback/kredensial.
- Terapkan HTTPS pada deployment publik, header keamanan termasuk `nosniff`, pembatasan framing, dan CSP. Batasi dokumentasi/endpoint administratif produksi sesuai kebutuhan operasi.
- Database, Redis, runner, dan database DOMjudge tidak memiliki port publik. Pisahkan jaringan dan kredensial per layanan. Hanya pengendali runner di host judge yang memperoleh akses Docker yang diperlukan.
- Gunakan akun database runtime dengan hak minimum; pisahkan hak migrasi dan operasi administratif. Akun root database tidak dipakai aplikasi.
- Rahasia produksi dikelola di secret store/berkas terproteksi yang dipasang ke layanan terkait; jangan masukkan ke image, Git, frontend, log, atau payload antrean. Tetapkan rotasi, pencabutan, dan prosedur saat bocor.
- Patok dependensi/image, buat inventaris/SBOM, pindai kerentanan, dan tetapkan penanganan temuan sebelum rilis. Pembaruan tetap memerlukan pengujian integrasi judge agar perubahan compiler/checker tidak mengubah hasil tanpa versi.
- Backup database dan artefak privat dienkripsi serta dibatasi aksesnya; tentukan retensi, sasaran kehilangan data/waktu pemulihan, dan uji restore. Redis bukan satu-satunya sumber nilai resmi.
- Tetapkan retensi submission, log, dan audit; jangan menyimpan token sesi/password/kunci tersembunyi di log. Penghapusan data pribadi perlu mempertimbangkan riwayat akademik serta kebijakan organisasi yang ditetapkan tersendiri.
- Penghapusan seluruh kelas diizinkan khusus pemilik kelas yang berperan pengajar atau admin, dengan konfirmasi nama kelas di server. Seluruh data akademik terkait dihapus secara transaksional sesuai foreign key; akun, kelas lain, audit administratif, dan backup yang sudah ada tidak dihapus. Tolak penghapusan saat penilaian/validasi berjalan; pekerjaan mengantre dapat dihapus dan pesan worker lama harus menjadi operasi tanpa efek. Arsip/pemulihan menjadi alternatif yang mempertahankan histori; kelas arsip menolak pengerjaan/penyuntingan baru dan tidak masuk katalog maupun leaderboard keseluruhan.
- Perubahan pengaturan dan pengelolaan undangan kelas hanya untuk pemilik/admin. Perubahan nama/deskripsi/akses memakai nomor revisi agar formulir lama tidak menimpa perubahan baru; deskripsi di-encode sebagai teks di web. Anggota/progres lama dipertahankan ketika akses berubah.
- Kode undangan enam digit dibuat dengan generator kriptografis, diindeks menggunakan HMAC-SHA256 dan disimpan terenkripsi menggunakan Fernet dengan kunci terpisah secara derivasi dari `CLASS_INVITE_SECRET`. Kode aktif berlaku 24 jam dan hanya dapat ditampilkan kembali lewat Pengaturan pemilik/admin. Jangan catat kode di URL, log, audit, screenshot, atau storage browser. Rotasi, pencabutan, serta perubahan ke publik membatalkan kode lama. Arsip menolak penukaran kode; pergantian secret membatalkan semua kode lama. Kode lama yang belum terenkripsi harus diganti agar dapat ditampilkan kembali.
- Asal keanggotaan membedakan penugasan, undangan, dan pendaftaran publik. Keanggotaan publik tidak memberi izin ke kelas yang kemudian menjadi privat. Status hanya dapat ditingkatkan oleh penugasan yang sah atau penukaran kode aktif. Migrasi memakai audit untuk mempertahankan penugasan/undangan yang terbukti, serta tidak memulihkan penugasan yang pernah dicabut; urutan historis yang tidak dapat dipastikan memerlukan undangan/penugasan baru. Progres tetap disimpan.
- Siswa tidak dapat membuka kelas arsip, termasuk konten, enrollment, leaderboard, serta histori kiriman melalui URL/API langsung. Admin dan pengajar yang berwenang tetap dapat meninjau arsip; pemulihan kelas mempertahankan data/progres.
- Profil hanya dapat mengubah nama lengkap dan email sendiri, bukan username login, role, atau status akun. Email unik dinormalisasi dan tidak ditampilkan pada leaderboard. Pendaftaran memerlukan nama/email; akun lama dapat melengkapinya tanpa membuat alamat email palsu. Password baru memerlukan verifikasi password saat ini, memenuhi kebijakan minimal, dicatat tanpa rahasia pada audit, dan mencabut seluruh sesi. Percobaan perubahan dibatasi persisten.
- Penerjemahan hanya menerima literal UI pada kode sumber sebelum data dinamis disisipkan. Konten Markdown, nama, email, input/output dan kode tidak dikirim ke penerjemah. Browser hanya menyimpan preferensi locale pada localStorage, tanpa token/password; katalog JSON/aset dilayani lokal sesuai CSP.
- Penukaran kode memerlukan akun aktif dan perlindungan CSRF untuk cookie, dibatasi persisten 5 percobaan/akun dan 30/IP per 5 menit termasuk kegagalan. Pesan kode salah/kedaluwarsa/kelas tak tersedia seragam; keanggotaan hanya sebagai peserta dan tidak menimpa peran pengajar yang sudah ada. Penukaran tidak memulai enrollment/progres. Kode pendek tetap merupakan kredensial bersama; pencabutan anggota perlu disertai rotasi/nonaktifkan kode jika akses undangan juga perlu dihentikan.
- Pantau antrean, retry, OOM, timeout, penolakan izin/login, akses kunci, dan kesehatan provider. Sediakan prosedur insiden, penghentian runner yang dicurigai, pencabutan rahasia, dan pemulihan.

## 11. Kriteria penerimaan keamanan

| ID uji | Skenario | Hasil yang harus dibuktikan |
|---|---|---|
| SEC-T01 | Peserta mengganti ID submission/enrollment | Tidak dapat membaca atau mengubah data peserta lain |
| SEC-T02 | Pengajar mengakses draft/kunci kelas lain | Ditolak kecuali memiliki penugasan/izin objek yang sah |
| SEC-T03 | Permintaan memasukkan role/score/completed/provider terlarang | Tidak meningkatkan hak, mengubah nilai, atau memilih mesin di luar izin |
| SEC-T04 | Mengambil kunci lewat detail, daftar, ekspor, cache, error, atau URL artefak | Data privat tidak terungkap |
| SEC-T05 | Materi/output/nama berkas berisi payload XSS | Ditampilkan aman; tidak menjalankan skrip atau mengambil sesi |
| SEC-T06 | Request CSRF, sesi kedaluwarsa, logout, atau penonaktifan akun | Perubahan tak sah ditolak; sesi yang dicabut tidak berlaku |
| SEC-T07 | Unggahan oversize, traversal, ZIP bomb, dan MIME palsu | Ditolak dan tidak menulis di luar area penyimpanan yang diizinkan |
| SEC-T08 | Program mencoba jaringan, filesystem host, fork, loop, atau output berlebihan | Akses dibatasi; sumber daya/tenggat ditegakkan dan pekerjaan dibersihkan |
| SEC-T09 | Banyak request serentak dari satu akun/kelas | Kuota keras dan keadilan antrean tetap berlaku |
| SEC-T10 | Memanggil materi/submission terkunci atau memalsukan progres | Prasyarat dan hasil resmi tetap menjadi sumber kelulusan |
| SEC-T11 | Hasil provider palsu, event ganda, dan worker dengan lease lama | Tidak mengubah nilai/progres resmi secara tidak sah |
| SEC-T12 | Revisi/path terbit bersamaan atau prasyarat bersiklus | Konflik/siklus ditolak; versi terbit tetap konsisten |
| SEC-T13 | Memulihkan backup dan mencabut rahasia uji | Data dapat dipulihkan sesuai target; rahasia lama tidak diterima |
| SEC-T14 | Pengajar menjalankan solusi acuan berbahaya | Mendapat sandbox, kuota, dan pembatasan setara prinsipnya dengan peserta |

Pengujian dijalankan pada lingkungan uji terisolasi. Setiap persyaratan diberi pemilik implementasi, bukti pengujian, dan status sebelum rilis. Persyaratan yang tidak relevan harus memiliki alasan tertulis, bukan ditandai lulus tanpa pengujian.

## 12. Selisih dengan prototipe saat ini

| Area | Kondisi saat ini | Pekerjaan yang diperlukan |
|---|---|---|
| Identitas/izin | Akun student/teacher/admin, Argon2id, sesi hashed, CSRF cookie, pencabutan sesi, kepemilikan submission, dan izin kelas melalui API | MFA, reset password, penguatan recovery, dan evaluasi autentikasi sebelum publik |
| Materi/kunci/path | Authoring melalui web, respons kunci privat, publikasi/revisi/arsip, validasi sandbox, path berversi, prasyarat server, dan progres resmi | Migrasi enrollment serta izin kolaborasi per konten yang lebih rinci |
| Runner custom | Ada pembatasan Docker dan probe isolasi dasar | Uji ancaman lebih luas, host terpisah untuk publik, dan pemantauan |
| Kuota | Admission terkunci di MariaDB, batas tertunda/per jam per akun dan kelas, antrean validasi terpisah | Kuota penyimpanan/komputasi total, pembersihan bucket lama, dan konfigurasi kuota melalui admin |
| Web/sesi/upload | Web dengan cookie HttpOnly/CSRF, sanitasi Markdown, output encoding, CSP tanpa inline script, font/aset lokal, dan source draft terikat akun/tab | HTTPS/Secure cookie produksi, pengujian keamanan menyeluruh, serta pengolahan berkas saat upload diaktifkan |
| Nilai | Attempt persisten, lease, retry, nilai biner, kepemilikan, audit, dan completion yang dicatat atomik oleh worker | Audit koreksi/rejudge serta migrasi progres lintas versi |
| Operasional | Compose lokal, rahasia di `.env`, backup lokal sebelum migrasi, audit database, dan image berversi sebagian | Secret store produksi, dependensi terkunci/pembaruan, audit tahan perubahan, restore teruji, dan uji publik |
| DOMjudge | Adaptor cadangan yang menolak eksekusi | Integrasi beserta pengujian otorisasi serta batas kepercayaan |

Cakupan tercatat: 60 unit/API test, 9 skenario judge pada verifikasi sebelumnya, 5 kelompok integrasi authoring yang diuji ulang, dan 7 kelompok browser nyata pada [VERIFIKASI.md](VERIFIKASI.md). Cakupan bertambah pada SEC-T10/11/12: akses langkah terkunci dan bypass API ditolak, run/jawaban salah tidak menambah progres, completion idempoten, siklus ditolak, serta enrollment lama tetap pada versi awal. Browser juga memeriksa tidak adanya token pada browser storage, logout, CSP/JavaScript error, dan permintaan aset eksternal. Ini belum membuktikan semua variasi SEC-T01 sampai SEC-T14 atau kesiapan publik penuh. Backup lokal sebelum migrasi belum sama dengan pengujian pemulihan bencana.
# Peninjauan pekerjaan dan eksekusi pengajar — 2 November 2026

Laporan progres kelas serta detail peserta per learning path hanya dapat diakses admin atau pengajar yang berwenang pada kelas. Identitas laporan mencakup nama/username tanpa email. Histori detail dibatasi enrollment, pemilik submission, dan versi langkah yang sesuai. Source dimuat hanya saat Lihat kode; nama, judul, source dan output tetap di-escape pada UI.

Eksekusi ulang oleh pengajar menerima input saja: source, compiler dan versi soal diambil dari submission asli di server. Kuota, admission lock, antrean, pembatasan input, CSRF dan sandbox tetap berlaku. Hasil disimpan atas akun pengajar sebagai run tanpa enrollment/step siswa; tidak menimpa jawaban asli, completion, nilai, atau waktu selesai siswa. Kelas arsip hanya bisa ditinjau, tidak menerima eksekusi baru. Peninjauan dan replay dicatat dalam audit tanpa isi kode. Pengujian backend terbaru 64 lulus, termasuk batas akses lintas kelas dan replay; browser memverifikasi eksekusi C++ nyata tanpa perubahan hasil siswa.


## Perbaikan audit dan review — 3 November 2026

Pembaruan admission 4 November: pemeriksaan awal memakai akses baca tanpa lock, koneksi/transaksi dilepas sebelum health check/persiapan provider, lalu izin dan status mutable diperiksa ulang setelah admission lock diperoleh. Urutan admission sebelum enrollment/kelas, pemeriksaan kuota, snapshot provider, idempotensi, serta penyimpanan job/audit atomik dipertahankan. Pemilihan provider/revisi yang berubah selama preflight ditolak; preflight bukan bukti izin yang boleh dipakai tanpa pemeriksaan ulang.

Replay pengajar dan submission peserta mengambil admission lock sebelum kelas; uji MariaDB terpisah memastikan replay tidak memegang lock kelas saat menunggu admission. Pembuatan run dan audit atomik; kegagalan audit tidak menyisakan job tersimpan. Replay idempoten tidak menggandakan run/audit, dan tetap memeriksa akses kelas pada pengulangan. DELETE sekarang mendapat batas body sebelum autentikasi dan validasi.

Undangan mempertahankan 5 permintaan/akun/5 menit. Batas bersama 30/IP/5 menit menghitung kode gagal; precheck dilakukan sebelum pencocokan sehingga kode benar juga ditolak bila IP sudah terkena pembatasan. Empat puluh akun sah dari satu IP dapat bergabung ketika tidak ada tebakan gagal. Detail kelas dan statistik baru tidak mengandung kode undangan; statistik memakai batas akses yang sama dengan histori milik sendiri.

Verifikasi: 72 pengujian backend lulus; satu tes MariaDB sengaja diskip pada suite SQLite lalu dijalankan terpisah dan lulus pada container MariaDB tmpfs tanpa volume produksi. Empat suite browser lulus (audit UI tiruan, alur web/judge nyata, profil/privat, lifecycle kelas). Tidak ada dependensi baru atau migrasi skema. Pengujian ini tidak menggantikan uji penetrasi atau uji beban publik.

## Instalasi plugin penilaian — 3 November 2026

- Hanya admin terautentikasi dapat memasang, mengaktifkan, memilih versi, menonaktifkan, dan menghapus paket. Cookie tetap membutuhkan CSRF/origin yang valid. Setiap perubahan masuk audit tanpa source atau kunci.
- Paket harus dikonfirmasi sebagai kode tepercaya. Batas ZIP dan total isi 256 KiB; root hanya plugin.json, plugin.py, dan README.md opsional. Path traversal, symlink, entri duplikat, ZIP terenkripsi, metadata API yang tidak didukung, serta sintaks Python rusak ditolak tanpa eksekusi source.
- Plugin adalah kode server tepercaya dengan hak proses worker (database, jaringan internal, test privat), bukan sandbox untuk plugin pihak ketiga. Pemeriksaan format/sintaks tidak membuktikan keamanan kode. Hanya runner memegang Docker socket; kode siswa tetap melalui sandbox.
- Source dan metadata versi immutable disimpan di database dan tercakup backup. Revisi soal/job dipin; cache source lokal worker dapat diregenerasi. Penghapusan plugin yang masih dirujuk soal/histori ditolak.
- Nonaktif tidak membatalkan pekerjaan diterima. Jika plugin berbahaya, hentikan worker dan tangani kredensial/data yang terdampak; jangan menganggap nonaktif sebagai isolasi atau penghentian kode.
- Installer tidak mengeksekusi pip/shell, tidak memasang dependensi otomatis, dan tidak mengunduh paket dari URL. Eksekusi plugin tetap dibatasi durasi task Celery; kesalahan menjadi retry/system_error, bukan nilai nol.

## Catatan perubahan sandbox (10 November 2026)

Kompilasi dan seluruh input kini berjalan dalam satu start container, dan runner menyiapkan container lebih dulu (tetap satu container baru per pekerjaan). Isolasi antar-input yang sebelumnya diperoleh dari restart container digantikan oleh mekanisme eksplisit di bootstrap: `PR_SET_DUMPABLE=0`, `kill -1` dari PID 1, pengosongan direktori tulis, dan sysctl yang menonaktifkan IPC SysV/POSIX. Rincian dan pengujiannya ada di [MILESTONE_PERBAIKAN.md](MILESTONE_PERBAIKAN.md#m53-semua-kasus-uji-dalam-satu-kali-start-container-selesai-10-november-2026) dan `tests/test_sandbox_reuse.py`. Mekanisme ini belum ditinjau pihak lain; tinjauan keamanan independen tetap menjadi syarat sebelum deployment publik.
