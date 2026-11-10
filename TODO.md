# Daftar tugas berikutnya

Dicatat pada 31 Oktober 2026. Butir yang dicentang sudah diimplementasikan; butir lainnya merupakan rencana pekerjaan berikutnya.

## Manajemen profil pengguna

- [x] Sediakan halaman pengelolaan profil pengguna.
- [x] Tambahkan fitur ubah nama pengguna. Tentukan apakah nama tampilan dipisahkan dari username untuk login.
- [x] Tambahkan fitur ubah password oleh pemilik akun, dengan verifikasi password saat ini.

## Alur belajar siswa melalui kelas

- [x] Ubah alur navigasi menjadi **Siswa → Kelas → Learning path → Materi/latihan**.
- [x] Sediakan daftar kelas yang dapat diakses siswa dan halaman detail kelas yang menampilkan learning path di dalamnya.
- [x] Pertahankan pemeriksaan akses kelas, enrollment, dan prasyarat pada alur baru.

## Leaderboard kelas

- [x] Hapus leaderboard learning path menjadi leaderboard kelas. Tampilkan pada laman masing-masing kelas.
- [x] Tentukan agregasi nilai learning path dalam satu kelas dan aturan pembanding waktu ketika nilainya sama.
- [x] Tampilkan leaderboard kelas bagi admin, pengajar, dan siswa sesuai izin akses kelas.
- [x] Leaderboard keseluruhan tidak perlu menampilkan pilihan untuk leaderboard kelas atau learning path, cukup satu leaderboard keseluruhan saja, dan hilangkan kolom "Latihan wajib".

## Pemisahan kelas aktif dan arsip

- [x] Pisahkan tampilan kelas aktif dari kelas yang diarsipkan, menggunakan halaman arsip tersendiri atau filter status.
- [x] Sembunyikan kelas arsip dari daftar kelas aktif secara default.
- [x] Pertahankan akses tinjau, pemulihan, dan penghapusan kelas arsip bagi pengguna yang berwenang.

## Platform multi bahasa

- [x] buat file konfigurasi multi bahasa, mungkin menggunakan json atau format lain yang lebih standar, cth: id.json, en.json, dll. file konfigurasi ini hanya untuk elemen web nya, tidak sampai ke konten-nya.
- [x] ada tombol pilihan bahasa.

## Visibilitas kelas

- [x] perlu mekanisme kelas privat dan publik, untuk privat, mungkin selain dengan menambahkan anggota kelas, bisa dengan kode invite. jangan terlalu panjang, cukup 6 digit kode.
- [x] ada menu pengaturan untuk merubah informasi kelas, mulai dari nama kelas, deskripsi, hingga perubahan akses kelas (publik/privat)
- [x] kode undangan sebaiknya muncul di halaman
- [x] deskripsi sebaiknya muncul pada halaman kelas. tag <p> setelah nama kelas, sebaiknya diganti dengan deskripsi kelas
- [x] arsip kelas sebaiknya hanya bisa diakses oleh admin atau pengajar.
- [x] kode undangan tidak bekerja dengan baik, dengan akun siswa, kelas privat tetap bisa diakses tanpa kode undangan.

## Laporan progres dan peninjauan pekerjaan

- [x] Hapus tab Kiriman kode dari pengelolaan kelas.
- [x] Ringkas progres kelas menjadi satu baris per peserta; rata-rata progres semua path terbit aktif, termasuk path belum dimulai dan pengerjaan parsial.
- [x] Tambahkan Hasil peserta per learning path, status, versi saat mulai, dan detail langkah/riwayat kode berdasarkan identitas peserta.
- [x] Pengajar/pemilik/admin dapat menjalankan ulang kode asli dengan input sendiri melalui sandbox tanpa mengubah hasil siswa.

## Perbaikan audit dan review Ponytail

- [x] Samakan urutan lock admission dan kelas untuk replay pengajar.
- [x] Simpan run pengajar dan audit dalam satu transaksi, termasuk idempotensi.
- [x] Terapkan batas body pada DELETE sebelum autentikasi/validasi.
- [x] Pisahkan keberhasilan undangan dari kuota tebakan salah per IP.
- [x] Abaikan respons editor lama sebelum mengubah state form aktif.
- [x] Ambil detail kelas berdasarkan ID; paginasi Kelas, Studio, anggota, materi/soal, dan path.
- [x] Wajibkan langkah wajib saat publikasi path baru; pertahankan path referensi lama tanpa mengurangi progres kelas.
- [x] Hitung statistik latihan berhasil dari semua hasil Accepted, bukan 100 kiriman terakhir.
- [x] Ambil data laporan progres kelas dan path secara batch.
- [x] Hapus cabang filter siswa yang tidak pernah dijalankan.

## Integrasi DOMJudge (ditunda)

- [ ] integrasi DOMJudge — ditunda sesuai permintaan pengguna.

## Form Pendaftaran

- [x] Form pendaftaran sebaiknya lebih lengkap, paling tidak ada nama lengkap dan email. untuk foto belum perlu.

## Plugin penilaian installable

- [x] Pisahkan implementasi penilai dalam folder plugin/.
- [x] Instalasi ZIP, registry dinamis, aktivasi/nonaktif, pembaruan versi, dan uninstall khusus admin.
- [x] Pilihan plugin pada editor soal dan penguncian revisi pada validasi/soal/attempt.
- [x] Pertahankan sandbox, retry, sanitasi hasil, progres, dan histori.
- [x] Sediakan SDK v1, paket contoh, panduan pengembangan, dan pengujian plugin.

## Milestone perbaikan audit Ponytail (6 November 2026)

Rincian, file, dan kriteria selesai ada di [MILESTONE_PERBAIKAN.md](MILESTONE_PERBAIKAN.md).

- [x] M1 — Penilaian tetap benar saat ramai (health runner, batas waktu CPU, margin acuan, 6 worker/7 slot). Uji beban stack penuh masih tertunda.
- [ ] M2 — Siap dibuka untuk satu kelas (IP di belakang proxy, kuota login, pemasangan plugin).
- [ ] M3 — Perampingan kode.
- [ ] M4 — Performa dan kerapian.
- [ ] M5 — Run dan Submit lebih cepat. Selesai: kirim langsung ke worker (M5.1) dan polling 0,4 detik (M5.2). Belum: semua kasus uji dalam satu start container (M5.3).
