# Panduan Web KodeLab

## Membuka aplikasi

Buka **http://localhost:8000/** setelah layanan Docker berjalan. Semua halaman dan font dilayani aplikasi lokal. UI memakai acuan [DESIGN.md](DESIGN.md): tema terang, hairline border, Mona Sans/Inter, dan aksen teal.

Navigasi aplikasi menggunakan sidebar. Pada desktop, sidebar selalu terlihat; pada tablet/ponsel, pilih **Buka menu** untuk menampilkan sidebar. Pilih tujuan, tekan Escape, klik latar di luar sidebar, atau gunakan tombol tutup untuk menutupnya. Bagian atas hanya memuat logo dan kontrol akun.

Untuk admin awal, gunakan `BOOTSTRAP_ADMIN_USERNAME` serta `BOOTSTRAP_ADMIN_PASSWORD` pada `.env`. Jangan membagikan file tersebut. Admin dapat memakai menu **Administrasi** untuk membuat akun pengajar dan peserta. Registrasi mandiri melalui **Buat akun** menghasilkan akun peserta.

## Profil, pendaftaran, dan password

Pendaftaran peserta memerlukan nama lengkap, email, username, dan password minimal 15 karakter. Email disimpan unik tanpa membedakan huruf besar/kecil; belum ada verifikasi email atau pengiriman email otomatis. Akun lama tetap dapat login tanpa perubahan username/password dan dapat melengkapi nama/email melalui Profil.

Buka **Profil** dari sidebar atau avatar. Ubah nama lengkap serta email lalu pilih **Simpan profil**. Nama lengkap menjadi nama tampilan pada header, Ringkasan, dan leaderboard; username login tetap. Pada **Ubah password**, isi password saat ini, password baru, dan konfirmasinya. Setelah berhasil, seluruh sesi akun dicabut; masuk kembali dengan password baru. Password saat ini tetap diverifikasi server dan percobaan perubahan dibatasi.

## Pilihan bahasa antarmuka

Pilih **Indonesia** atau **English** di header, termasuk pada halaman login/pendaftaran. Pilihan disimpan sebagai preferensi bahasa pada browser dan halaman dimuat ulang. Nama pengguna, judul/deskripsi kelas, materi, soal, kode, input/output, dan progres tidak diterjemahkan. Draft kode di tab tetap dipertahankan ketika mengganti bahasa.

Katalog teks UI tersedia di `web/locales/id.json` dan `web/locales/en.json`. Penerjemahan diterapkan pada literal UI sebelum nilai konten disisipkan, bukan dengan mengganti teks pada DOM. Pengembang dapat menambah pasangan terjemahan pada katalog; utilitas `scripts/build-ui-locales.cjs` dan `scripts/localize-ui.cjs` membantu pemeliharaan teks sumber.

## Alur pengajar

### 1. Buat kelas

Masuk sebagai pengajar/admin, buka **Studio pengajar**, lalu pilih **Buat kelas**. Kelas publik dapat diikuti peserta melalui jalur yang terbit; kelas privat memerlukan penugasan peserta atau kode undangan.

Pada tab **Peserta**, pemilik kelas/admin dapat menambahkan akun berdasarkan username. Akun yang ditugaskan sebagai pengajar harus sudah memiliki peran pengajar. Pencabutan akses tidak menghapus riwayat akademik.

### Pengaturan nama, deskripsi, dan akses kelas

Buka **Studio pengajar → Kelola kelas → Pengaturan** sebagai pemilik kelas atau admin. Ubah **Nama kelas**, **Deskripsi kelas**, serta centang/hapus centang **Kelas publik**, kemudian pilih **Simpan pengaturan**. Deskripsi ditampilkan sebagai teks pada kartu dan halaman kelas.

Kelas publik ditemukan oleh pengguna yang masuk. Kelas privat hanya dapat diakses anggota yang ditugaskan atau bergabung menggunakan kode undangan. Perubahan publik/privat tidak menghapus enrollment, versi jalur, atau progres. Namun, anggota yang dahulu bergabung otomatis saat kelas masih publik harus memakai kode undangan atau ditugaskan pengajar sebelum dapat mengakses kelas yang kini privat. Anggota yang memang ditugaskan/diundang tetap memiliki akses. Mengubah kelas menjadi publik menonaktifkan kode undangan. Pengajar tambahan tidak dapat mengubah pengaturan akses atau mengelola kode. Kelas arsip harus dipulihkan sebelum pengaturannya diubah.

### Kode undangan kelas privat

Pada tab **Pengaturan** kelas privat, pilih **Buat kode undangan**, lalu **Buat kode**. Kode berisi tepat enam digit, termasuk kemungkinan nol di depan, dan berlaku selama 24 jam. Kode aktif tampil pada halaman Pengaturan bagi pemilik kelas/admin, termasuk setelah reload; bagikan hanya kepada calon anggota. Kode disimpan terenkripsi di server dan tidak muncul pada daftar kelas atau halaman siswa. Kode yang dibuat sebelum fitur penyimpanan terenkripsi perlu diganti sekali agar dapat ditampilkan kembali. Pilih **Ganti kode undangan** bila membutuhkan kode baru; kode sebelumnya langsung tidak berlaku. **Nonaktifkan kode** mencabut kode tanpa menghapus anggota yang telah bergabung.

Siswa membuka **Kelas → Gabung dengan kode**, memasukkan kode enam digit, lalu memilih **Gabung kelas**. Keanggotaan yang diperoleh adalah peserta; tindakan ini belum memulai enrollment atau penghitung waktu learning path. Memilih **Mulai belajar** pada jalur tetap menjadi awal enrollment. Kode kelas arsip, publik, kedaluwarsa, atau yang telah dicabut tidak dapat digunakan.

Percobaan bergabung dibatasi lima kali per akun dan 30 kali per alamat IP dalam lima menit, termasuk percobaan berhasil. Mencabut anggota tidak melarangnya bergabung lagi jika ia masih memiliki kode aktif; ganti atau nonaktifkan kode bila akses undangan perlu ditutup.

### Arsip, pemulihan, dan hapus kelas

Pemilik kelas dan admin melihat tombol **Arsipkan kelas** serta **Hapus kelas** pada kartu kelas di **Studio pengajar** dan pada halaman **Kelola kelas**. Pengajar tambahan yang ditugaskan ke kelas dapat mengelola konten, tetapi tidak memiliki hak mengarsipkan/menghapus seluruh kelas.

Daftar kelas bagi admin/pengajar di **Studio pengajar** dan menu **Kelas** menyediakan tab **Kelas aktif** dan **Arsip kelas**. Siswa hanya mendapat daftar kelas aktif. Secara default hanya kelas aktif yang ditampilkan; pilih **Arsip kelas** untuk meninjau arsip yang dapat diakses. Tab arsip tetap dipilih setelah halaman dimuat ulang, pemulihan, atau penghapusan dari daftar. Kelas yang diarsipkan langsung keluar dari daftar aktif; kelas yang dipulihkan langsung keluar dari daftar arsip.

Pada tab arsip Studio, pilih **Tinjau kelas**, **Pulihkan kelas**, atau **Hapus kelas** sesuai izin akun. Siswa tidak dapat membuka kelas arsip, termasuk melalui URL/API langsung, enrollment, leaderboard kelas, dan histori kiriman kelas tersebut. Data tetap tersimpan untuk pengajar/admin dan kembali dapat diakses siswa setelah kelas dipulihkan sesuai izin keanggotaannya. Ringkasan hanya menampilkan kelas aktif.

- **Arsipkan kelas** menyembunyikan jalur dari katalog dan mengeluarkan nilainya dari leaderboard keseluruhan. Hanya admin dan pengajar yang berwenang dapat meninjau materi, kiriman, leaderboard kelas, dan progres arsip. Pendaftaran, penyuntingan, konfirmasi membaca, run, dan pengiriman jawaban baru dinonaktifkan. Pekerjaan penilaian yang sudah diterima sebelum arsip tetap dapat selesai.
- **Pulihkan kelas** mengaktifkan kembali kelas dengan progres dan versi sebelumnya. Konten yang sebelumnya diarsipkan secara terpisah tetap diarsipkan. Durasi tetap memakai waktu kalender sejak enrollment, termasuk masa arsip.
- **Hapus kelas** membuka konfirmasi. Ketik nama kelas persis seperti yang ditampilkan lalu pilih **Hapus permanen**. Sistem menghapus materi beserta semua versinya, soal, kunci, kasus uji, pekerjaan validasi, learning path/versi/langkah, enrollment, completion/progres, nilai, run, submission/attempt dan keanggotaan kelas dalam satu transaksi. Tindakan ini tidak dapat dibatalkan melalui aplikasi. Akun pengguna dan kelas lain tetap ada.

Jika ada penilaian atau uji kunci berstatus berjalan, penghapusan ditolak sampai pekerjaan selesai; coba kembali setelah itu. Pekerjaan yang masih mengantre ikut dihapus, dan pesan antrean lama tidak dapat membuat data kelas muncul kembali. Log audit administratif tetap disimpan sebagai jejak tindakan, tanpa mempertahankan kode atau konten akademik kelas. Backup yang sudah dibuat sebelumnya tidak ikut diubah oleh penghapusan kelas.

### 2. Tulis dan terbitkan materi

Pada tab **Materi**, pilih **Buat materi**. Isi judul dan penjelasan menggunakan Markdown, termasuk blok kode. **Simpan draft** menyimpan tanpa membagikan kepada peserta. **Terbitkan** menyimpan dan menerbitkan versi materi.

Materi terbit dapat ditinjau tetapi tidak diedit langsung. Pilih **Revisi** atau **Buat revisi baru** untuk membuat draft baru. Versi sebelumnya tetap tersimpan. **Arsipkan** menyembunyikan konten dari penggunaan baru.

### 3. Buat soal dan kunci privat

Pada tab **Bank soal**, pilih **Buat soal**, lalu isi:

- Judul, tugas, batas nilai, dan format input/output yang dibaca peserta.
- Bahasa yang diizinkan: C17 dan/atau C++17.
- Kasus uji input dan output yang diharapkan. Centang **Contoh terbuka** hanya untuk kasus yang boleh dilihat peserta.
- Solusi acuan untuk setiap bahasa yang diizinkan. Bagian ini privat.
- Batas eksekusi bila perlu, dalam rentang yang disetujui sistem.

Pilih **Uji kunci**. Aplikasi menyimpan draft lalu menjalankan semua solusi acuan dalam sandbox. Tunggu hasil **Kunci lolos pengujian**, kemudian pilih **Terbitkan**. Jika gagal, periksa pesan compiler/hasil uji dan perbaiki. Perubahan draft membatalkan hasil validasi sebelumnya sehingga perlu diuji ulang.

Nilai peserta berasal dari perilaku program pada kasus uji, bukan kesamaan teks dengan solusi acuan. Siapkan variasi input yang relevan; lolosnya acuan tidak otomatis membuktikan seluruh kemungkinan input sudah benar.

### 4. Susun learning path

Pada tab **Learning path**, pilih **Buat jalur**. Isi nama, deskripsi, bahasa, dan susunan langkah.

Setiap langkah memiliki judul, modul, jenis (**Materi** atau **Latihan kode**), dan rujukan ke versi konten terbit dalam kelas yang sama. Gunakan tombol panah untuk mengubah urutan, **Tambah langkah** untuk menambah, dan tombol hapus untuk menghapus langkah draft.

**Buka langkah secara berurutan** menjadikan semua langkah wajib sebelumnya sebagai prasyarat otomatis. Jika dinonaktifkan, atur prasyarat tambahan secara eksplisit. Semua prasyarat harus selesai; siklus dan rujukan tidak sah ditolak server. Langkah wajib tidak dapat bergantung pada langkah opsional.

Centang **Langkah wajib** untuk langkah yang dihitung terhadap kelulusan jalur. Langkah opsional tidak menahan kelulusan. Path tanpa langkah wajib diperlakukan sebagai referensi, tanpa status kelulusan otomatis.

Simpan draft, tinjau susunan, lalu **Terbitkan**. Materi/soal harus telah terbit dan mendukung bahasa jalur sebelum dapat digunakan. Jalur dan semua rujukan versinya dibekukan saat terbit.

### 5. Pantau pembelajaran

- **Progres** menampilkan satu baris per peserta, nama lengkap dan username, jumlah path selesai, progres kelas, serta total lama pengerjaan path. Progres kelas adalah rata-rata proporsi langkah wajib selesai dari seluruh learning path terbit yang tidak diarsipkan. Path yang belum dimulai bernilai 0%; draft dan path arsip tidak dihitung. Contoh: satu path selesai dan satu path separuh selesai menghasilkan 75%. Jika tidak ada path terbit, progres 0%. Path referensi lama tanpa langkah wajib dikecualikan dari pembagi, termasuk bila enrollment masih dipatok pada versi referensi sebelum revisi baru terbit. Publikasi path baru harus memiliki minimal satu langkah wajib; draft boleh disimpan saat semua langkah masih opsional. Langkah opsional tidak menambah persentase. Pengerjaan lama tetap menggunakan versi saat peserta mendaftar; persentase dihitung sebelum pembulatan dua desimal.
- **Learning path → Hasil peserta** menampilkan peserta beserta status, versi, progres, dan lama pengerjaan masing-masing. Pilih **Detail pengerjaan** untuk melihat langkah materi/latihan serta riwayat kode peserta pada path tersebut. Tombol **Lihat kode** menampilkan program, compiler, waktu, dan hasil uji. **Jalankan kode** mengeksekusi ulang kode asli dengan input pengajar melalui sandbox; tidak mengubah nilai, progres, atau waktu selesai siswa. Kelas arsip tetap dapat ditinjau, tetapi eksekusi baru dinonaktifkan. Daftar laporan menampilkan hingga 100 data per halaman dengan navigasi halaman. Tab **Kiriman kode** telah dihapus; riwayat siswa sendiri tetap tersedia.
- Akses pengajar dibatasi pada kelas yang dimiliki/ditugaskan. Administrator dapat memeriksa **Audit**.

Revisi path berlaku untuk peserta baru. Peserta lama tetap mengikuti versi yang sudah dipatok; progresnya tidak direset. Pemindahan enrollment ke versi baru belum tersedia.

## Alur peserta

1. Daftar atau masuk, lalu buka menu **Kelas**. Cari kelas berdasarkan nama dan pilih **Buka kelas**. Daftar ini menampilkan kelas publik aktif serta kelas privat aktif yang dapat kamu akses.
2. Di dalam kelas, pilih learning path lalu **Mulai belajar**. Untuk kelas publik, keanggotaan dibuat saat mengikuti jalur; kelas privat memerlukan penugasan pengajar atau kode undangan. Membuka halaman kelas saja tidak memulai penghitung waktu enrollment.
3. Buka langkah yang tersedia. Ikon gembok menunjukkan prasyarat yang belum selesai.
4. Baca materi lalu pilih **Selesai membaca**. Ini hanya mencatat konfirmasi membaca, bukan bukti penguasaan konsep.
5. Pada latihan, pilih C17/C++17, tulis kode, dan gunakan **Jalankan** dengan input sendiri untuk mencoba.
6. Pilih **Kirim jawaban** untuk penilaian resmi. Jawaban Accepted menyelesaikan langkah dan membuka prasyarat berikutnya. Jawaban salah, run, dan gangguan infrastruktur tidak menambah kelulusan.
7. Lihat **Riwayat kode** untuk kode serta hasil sebelumnya. Progres jalur tetap tersimpan setelah reload atau login kembali.

Alur utama adalah **Kelas → Learning path → Materi/latihan**. Ringkasan menampilkan kartu kelas aktif; di dalam kelas, kartu learning path menampilkan progres dan lama pengerjaan. Breadcrumb pada jalur dan langkah belajar menyediakan tautan kembali ke kelas asal. Enrollment lama tetap menggunakan versi jalur sebelumnya meskipun ada revisi baru. Jalur yang sudah diikuti tetapi kemudian diarsipkan tetap dapat ditinjau melalui kelasnya. Kelas arsip hanya tersedia bagi admin/pengajar yang berwenang melalui **Kelas → Arsip kelas**.

Latihan dikerjakan melalui learning path. Fitur latihan mandiri telah dihapus; tautan katalog jalur dan latihan mandiri lama dialihkan ke daftar kelas. API peserta menolak pembukaan soal generik dan pengiriman tanpa enrollment/step, sehingga prasyarat tetap berlaku. Riwayat kiriman lama tetap tersimpan.

Editor menyediakan nomor baris, Tab untuk indentasi, Ctrl/⌘+Enter untuk menjalankan, dan draft per bahasa yang disimpan sementara di tab. Draft ini terpisah dari progres resmi di MariaDB. Kunci serta kasus tersembunyi tidak dikirim ke browser peserta.

Pilihan **Compiler** menentukan cara kode dikompilasi: **C17 · GCC** untuk C dan **C++17 · G++** untuk C++. Kode dengan `#include <iostream>` memerlukan C++17. Pilihan compiler terakhir dan draft masing-masing bahasa dipertahankan per latihan dalam tab yang sama, termasuk setelah reload; keduanya dihapus saat logout. Hasil pengujian menampilkan compiler yang benar-benar digunakan. Jika muncul pesan `main.c` dan `iostream: No such file or directory`, periksa pilihan compiler lalu jalankan kembali dengan C++17.

## Lama pengerjaan dan leaderboard

**Lama pengerjaan** tampil pada kartu jalur yang diikuti, ringkasan progres jalur, panel langkah belajar, dan laporan progres pengajar. Waktu dimulai saat peserta memilih **Mulai belajar**, termasuk jeda/offline dan waktu penilaian, lalu berhenti ketika seluruh langkah wajib selesai. Langkah opsional serta pengiriman ulang tidak mengubah waktu selesai. Durasi dihitung dari timestamp server; jam browser hanya memperbarui tampilannya. Data enrollment/completion lama ikut dihitung tanpa mereset progres.

**Leaderboard kelas** langsung tertanam pada halaman kelas, di bawah daftar learning path. Admin, pengajar, dan siswa dapat melihatnya sesuai izin kelas. Leaderboard per learning path sudah dihapus; nilai setiap jalur tetap terlihat pada progres dan digunakan untuk menghitung peringkat kelas.

- Nilai jalur = persentase latihan wajib yang sudah Accepted, maksimal 100. Materi baca, latihan opsional, run, jawaban salah, dan gangguan layanan tidak menambah nilai.
- Nilai kelas = jumlah nilai learning path dalam kelas tersebut. Setiap jalur dihitung sekali sesuai versi enrollment; publikasi versi baru tidak menggandakan nilai atau memindahkan progres lama. Jalur arsip dan jalur tanpa latihan wajib tidak berkontribusi.
- Nilai lebih besar mendapat peringkat lebih tinggi. Pada nilai sama, total durasi penyelesaian yang lebih singkat didahulukan. Durasi kelas adalah jumlah waktu jalur yang menyumbang nilai dan baru final setelah semua jalur tersebut selesai. Mengikuti jalur tambahan dengan nilai nol tidak mengubah durasi pembanding.
- Peserta yang belum memiliki durasi final berada setelah peserta dengan durasi final pada nilai yang sama. Nilai dan durasi yang identik berbagi peringkat. Waktu dihitung oleh server dan termasuk jeda sejak enrollment.
- **Leaderboard keseluruhan** tersedia melalui sidebar dan hanya menampilkan satu peringkat, tanpa pemilih kelas/jalur maupun kolom Latihan wajib. Nilainya menjumlahkan kontribusi dari kelas yang dapat diakses pengguna; kelas arsip dikecualikan.
- Leaderboard kelas arsip hanya dapat ditinjau admin/pengajar yang berwenang. Menghapus kelas menghapus data yang menyumbang peringkat tersebut. Hanya akun siswa aktif dengan keanggotaan yang masih berlaku dan enrollment pada jalur berlatihan wajib yang diperingkatkan.

Kolom tabel adalah peringkat, peserta, nilai total, jalur selesai, dan waktu penyelesaian. Kode jawaban, kunci, dan kasus tersembunyi tidak dimuat dalam leaderboard. Kelas publik dapat dilihat pengguna yang masuk; kelas privat hanya oleh anggota/pengelola dan admin. Cakupan keseluruhan dapat berbeda antar akun. Agregasi lintas versi merupakan akumulasi nilai, bukan penyetaraan tingkat kesulitan soal.

## Contoh yang sudah tersedia di workspace

Pengujian UI membuat jalur publik **Dasar Pemrograman C/C++**: materi input/output, latihan penjumlahan dua bilangan, dan refleksi opsional. Akun peserta baru dapat mengikutinya. Ini konten nyata di database pengembangan, bukan kartu atau progres contoh di frontend. Admin dapat meninjau/merevisinya melalui studio.

Instalasi baru di mesin lain tidak otomatis memiliki data pengujian ini. Gunakan alur pengajar di atas atau jalankan pengujian browser untuk memvalidasi seluruh alur dan membuat contoh yang sama.

## Batas versi ini

Judge custom sudah berfungsi; DOMjudge masih adaptor cadangan. Nilai parsial, reset password/MFA, unggahan berkas, debugger/autocomplete, rejudge, dan migrasi enrollment belum tersedia. Aplikasi saat ini dikonfigurasi untuk localhost. Persyaratan publikasi produksi tetap mengikuti [KEBUTUHAN_KEAMANAN.md](KEBUTUHAN_KEAMANAN.md).

Status pekerjaan manajemen profil, ubah nama/password, alur siswa melalui kelas, leaderboard kelas, serta pemisahan tampilan kelas aktif dan arsip dicatat di [TODO.md](TODO.md). Seluruh tugas yang disetujui pada TODO sudah tersedia; integrasi DOMjudge ditunda atas permintaan pengguna.

## Plugin penilaian

Admin dapat membuka **Plugin penilaian** di sidebar atau `#/admin/plugins`, memasang ZIP buatan sendiri, mengaktifkan/menonaktifkan, memilih versi aktif, dan menghapus plugin yang belum dirujuk data. Pengajar memilih plugin aktif pada editor bank soal, lalu menguji solusi acuan sebelum publikasi.

Sumber penilai berada di `plugin/`. Contoh siap dipasang: `plugin/examples/sandbox-delegate.zip`. Panduan kontrak, format paket, pembaruan, dan batas kepercayaan: [plugin/README.md](plugin/README.md). Penilai bawaan tetap tersedia. Plugin tambahan hanya boleh berasal dari kode yang dipercaya admin karena dijalankan pada worker server.
