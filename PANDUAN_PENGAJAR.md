# Panduan API Pengajar

Antarmuka pengajar dan penyusun learning path sudah tersedia di <http://localhost:8000/>; gunakan [Panduan Web](PANDUAN_WEB.md) untuk alur tanpa menulis request API. Dokumen ini menjelaskan integrasi melalui Swagger di <http://localhost:8000/docs>. Materi/soal/path disimpan di MariaDB tanpa perubahan kode atau build image.

## 1. Login dan membuat akun

1. Buka `.env` secara lokal untuk mengetahui `BOOTSTRAP_ADMIN_USERNAME` dan `BOOTSTRAP_ADMIN_PASSWORD`.
2. Jalankan `POST /auth/login` dengan username/password tersebut.
3. Salin nilai `access_token` dari respons, klik **Authorize**, dan tempel token tanpa awalan `Bearer`.
4. Gunakan `POST /admin/users` untuk membuat akun pengajar dengan `role: "teacher"`. Buat akun peserta dengan `role: "student"`, atau gunakan `/auth/register` untuk registrasi mandiri peserta.
5. Login sebagai pengajar lalu ganti token pada **Authorize** agar tindakan authoring menggunakan identitas pengajar.

Username memakai 3-40 huruf kecil, angka, atau underscore, diawali huruf. Password minimal 15 dan maksimal 128 karakter. Gunakan password unik dan acak. Token/sesi berlaku maksimal 12 jam, kedaluwarsa setelah 30 menit tidak aktif, dan dapat dicabut melalui logout atau perubahan izin admin. Jangan membagikan token atau memasukkannya ke URL.

Jika menjalankan API memakai cookie tanpa Bearer, kirim header `X-CSRF-Token` pada operasi yang mengubah data. Respons login menyediakan token CSRF. Pengujian Swagger lebih mudah menggunakan Bearer melalui **Authorize**.

## 2. Kelas dan peserta

`POST /courses`:

```json
{
  "title": "Pemrograman Dasar C/C++",
  "is_public": false
}
```

Simpan `id` kelas sebagai `course_id`. Pengajar yang membuatnya menjadi pemilik kelas. `GET /courses` menampilkan kelas yang dapat diakses akun tersebut.

Untuk kelas privat, pemilik/admin menambahkan peserta menggunakan `POST /courses/{course_id}/members`:

```json
{
  "user_id": "ID_AKUN_PESERTA",
  "role": "student"
}
```

Admin dapat memperoleh ID akun melalui `GET /admin/users`. Peserta juga dapat melihat ID sendiri melalui `/auth/me`. Pengajar memakai `GET /courses/{course_id}/members` untuk melihat daftar anggota. Pemilik dapat menugaskan pengajar lain dengan `role: "teacher"`, asalkan akun tujuan memang memiliki peran teacher. Hanya pemilik/admin yang boleh mengubah penugasan anggota.

Pada kelas publik, akun yang sudah login dapat membaca konten terbit dan mendaftarkan diri melalui `POST /courses/{course_id}/enroll`. Enrollment diperlukan untuk mengirim program pada soal kelas. `DELETE /courses/{course_id}/members/{user_id}` mencabut keanggotaan; riwayat submission tetap dipertahankan.

## 3. Membuat dan menerbitkan materi

`POST /author/courses/{course_id}/lessons`:

```json
{
  "title": "Input dan Output",
  "body_markdown": "# Input dan Output\nGunakan `scanf` atau `std::cin` untuk membaca input."
}
```

Respons berisi `lesson_id`, ID versi pada field `id`, `revision`, dan `edit_revision`. Materi baru berstatus draft dan belum terlihat peserta.

- Preview: `GET /author/lesson-versions/{id}`; `body_html` telah melalui rendering tanpa HTML mentah dan sanitasi.
- Edit: `PUT /author/lesson-versions/{id}` dengan `title`, `body_markdown`, dan `edit_revision` terbaru.
- Publikasi: `POST /author/lesson-versions/{id}/publish` dengan `{"edit_revision": 1}` atau nomor terbaru.
- Baca sebagai peserta: `GET /courses/{course_id}/lessons`.

Konflik edit mengembalikan 409; muat ulang draft sebelum menyimpan kembali. Materi terbit tidak dapat diedit langsung. Gunakan `POST /author/lessons/{lesson_id}/versions` untuk membuat revisi baru, lalu edit dan terbitkan revisi itu. Versi lama tetap tersimpan.

## 4. Membuat soal dan kunci

`POST /author/courses/{course_id}/problems`:

```json
{
  "title": "Jumlah Dua Bilangan",
  "statement": "Baca dua bilangan bulat antara -1000000 dan 1000000, lalu cetak jumlahnya tanpa prompt tambahan.",
  "languages": ["c17", "cpp17"],
  "provider": "custom",
  "cases": [
    {"input": "2 3\n", "expected": "5\n", "public": true},
    {"input": "-7 -8\n", "expected": "-15\n", "public": false}
  ],
  "reference_solutions": {
    "c17": "#include <stdio.h>\nint main(void){int a,b;scanf(\"%d%d\",&a,&b);printf(\"%d\",a+b);return 0;}",
    "cpp17": "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<std::endl;}"
  }
}
```

Simpan `problem_id` dan ID versi (`id`). Diperlukan tepat satu solusi acuan untuk setiap profil bahasa yang diizinkan, setidaknya satu contoh publik, dan 1-10 kasus uji. Solusi acuan maksimal 32 KiB UTF-8 per bahasa. Versi ini hanya mendukung checker token dan nilai biner; DOMjudge belum dapat digunakan.

Field `limits` opsional menggunakan default kompilasi 10 detik, eksekusi 2 detik per kasus, memori 128 MiB, dan output 65536 byte. Batas schema membatasi pilihan pengajar: kompilasi maksimal 15 detik, eksekusi maksimal 5 detik, memori maksimal 256 MiB, dan output maksimal 65536 byte.

Kasus `public: false` dan solusi acuan hanya tersedia pada API authoring bagi pengelola kelas. Peserta tidak menerima field kunci tersebut. Pengajar perlu memeriksa sendiri spesifikasi dan cakupan uji; lolosnya solusi acuan tidak membuktikan bahwa semua kemungkinan input sudah tercakup.

## 5. Validasi sebelum publikasi

1. Panggil `POST /author/problem-versions/{id}/validate` dengan `{"edit_revision": 1}` atau nomor terbaru.
2. Respons 202 memberikan ID pekerjaan validasi.
3. Poll `GET /author/validations/{job_id}` sampai `state` menjadi `completed` atau `system_error`.
4. Jika `valid: true`, panggil `POST /author/problem-versions/{id}/publish` dengan nomor edit yang sama.
5. Jika `valid: false`, baca hasil privat per bahasa, perbaiki draft beserta kuncinya, kemudian validasi ulang.

Batas waktu soal adalah waktu CPU. Validasi menjalankan solusi acuan dengan **separuh batas waktu** (dibulatkan ke bawah, minimal 1 detik). Contohnya, untuk soal dengan batas 2 detik, kunci harus selesai dalam 1 detik CPU. Ketika server ramai, program yang sama bisa berjalan hingga sekitar 2 kali lebih lambat. Ruang separuh batas ini mencegah jawaban siswa yang sama cepatnya dengan kunci divonis TLE. Jika kunci mendapat `TIME_LIMIT_EXCEEDED` saat validasi, naikkan batas waktu atau percepat kuncinya. Soal dengan batas 1 detik belum mendapat ruang ini, jadi pakai minimal 2 detik bila kunci membutuhkan waktu CPU yang berarti.

Kode acuan dikompilasi dan dijalankan di sandbox. Draft tidak dapat diedit selama validasi berlangsung. Gangguan infrastruktur dicoba ulang maksimal dua kali; setelah `system_error`, draft dibuka kembali untuk perbaikan/validasi baru. Gangguan ini tidak menghasilkan nilai peserta.

Setiap edit menaikkan `edit_revision` dan membatalkan hasil validasi sebelumnya. Publikasi ditolak apabila draft belum lolos validasi yang sesuai revisi/provider saat ini. Validasi tidak otomatis menerbitkan soal.

## 6. Peserta mengerjakan dan pengajar melihat hasil

Peserta yang memiliki akses memakai `GET /problems` atau `/problems/{version_id}` untuk membaca soal terbit dan contoh terbuka. Kirim kode melalui `/submissions` dengan ID versi tersebut; `/runs` dipakai untuk mencoba input sendiri tanpa nilai. Provider penilaian resmi ditentukan server.

Ketika soal digunakan dalam learning path, akses peserta harus memakai konteks enrollment/step. Pembukaan langsung via endpoint soal generik ditolak untuk mencegah bypass prasyarat. Baca bagian learning path berikut untuk endpoint yang sesuai.

`GET /submissions` menampilkan pekerjaan sendiri. Pengajar memakai `GET /submissions?course_id={course_id}` untuk daftar submission kelas yang ditugaskan dan `/submissions/{id}` untuk kode serta hasilnya. Peserta tidak dapat membaca pekerjaan orang lain; pengajar di luar kelas tidak mendapat akses.

Untuk revisi soal, gunakan `POST /author/problems/{problem_id}/versions`. Revisi baru berupa draft dengan salinan kasus/solusi yang dapat diedit, lalu harus divalidasi dan diterbitkan kembali. Riwayat submission tetap menunjuk versi lama; submission baru memakai versi terbit yang aktif.

`GET /author/courses/{course_id}/content` membantu menemukan materi, soal, dan versi yang pernah dibuat. `POST /author/lessons/{lesson_id}/archive` atau `/author/problems/{problem_id}/archive` menyembunyikan konten dari penggunaan baru tanpa menghapus riwayat. Konten arsip tetap dapat ditinjau melalui API authoring oleh pengelola yang berwenang.

Administrator dapat meninjau audit melalui `/admin/audit`. Pembuatan akun, perubahan izin/anggota, akses kunci, validasi, publikasi, arsip, dan pembacaan submission oleh pengelola dicatat tanpa menyalin password atau isi kunci ke rincian audit.

## 7. API learning path

- `POST /author/courses/{course_id}/paths`: buat draft path berisi judul, deskripsi, bahasa, `sequential`, dan `steps`.
- Setiap step memiliki `key` unik, `title`, `module`, `kind` (`reading`/`exercise`), `required`, `prerequisites`, serta tepat satu dari `lesson_version_id`/`problem_version_id`.
- `GET/PUT /author/path-versions/{id}`: tinjau/edit draft, dengan `edit_revision` untuk update.
- `POST /author/path-versions/{id}/publish`: validasi rujukan/ketersediaan konten serta terbitkan versi.
- `POST /author/paths/{path_id}/versions`: buat revisi path; `/archive` mengarsipkan.
- `GET /author/courses/{course_id}/paths` dan `/progress`: daftar versi serta laporan progres kelas.
- `GET /paths`: katalog jalur terbit yang dapat diakses; `POST /paths/{path_id}/enroll` mengikuti versi terbit saat itu secara idempoten.
- `GET /my/learning` dan `/enrollments/{id}`: progres milik peserta.
- `GET /enrollments/{id}/steps/{step_id}`: isi langkah setelah pemeriksaan kepemilikan, akses kelas, dan prasyarat.
- `POST /enrollments/{id}/steps/{step_id}/complete`: konfirmasi membaca saja. Latihan selesai melalui Accepted dari worker resmi.

Request `/submissions` dan `/runs` pada jalur menyertakan `enrollment_id` serta `path_step_id`; keduanya wajib dipasangkan dan harus cocok dengan soal serta pemilik. Run dan jawaban gagal tidak menambah completion. Versi enrollment tetap dipatok ketika revisi path baru terbit. Daftar materi generik juga menyaring materi yang terikat jalur bagi peserta.

## 8. Batas versi ini

Pemulihan password, MFA, migrasi enrollment, rejudge, unggahan, dan integrasi DOMjudge belum tersedia. Sesi lokal menggunakan HTTP loopback; deployment publik tetap memerlukan kontrol tambahan pada [KEBUTUHAN_KEAMANAN.md](KEBUTUHAN_KEAMANAN.md).
