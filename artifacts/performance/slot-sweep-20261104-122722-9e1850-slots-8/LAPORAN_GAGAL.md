# Percobaan 8 slot pertama — cohort tidak lengkap

Percobaan ini dipertahankan sebagai temuan stabilitas dan tidak dipakai untuk peringkat kapasitas. Konfigurasi: 8 proses worker eksekusi, 8 slot runner, 30 peserta pada satu learning path, scheduler 1 detik, batas pending kelas 20.

Satu permintaan Submit peserta indeks 25 (C++17) mengalami **HTTP transport `ReadError` setelah 45,163 milidetik**, pada t=61,959701 detik dari awal generator. Alat uji tidak menerima HTTP 202 atau ID pekerjaan untuk permintaan tersebut. Dengan demikian, hanya 63 dari 64 pekerjaan yang dapat dihubungkan dengan trace. Generator juga menandai admission failure dan progres peserta tersebut tetap 50/nilai 0; tiga penanda ini berasal dari satu permintaan yang gagal, bukan tiga kegagalan eksekusi yang terpisah.

Tidak ditemukan error aplikasi/SQL atau peringatan cleanup pada log yang diperiksa. Penyebab jaringan/penutupan koneksi belum dipastikan. Tidak ada dasar untuk menyebutnya kesalahan compiler atau jawaban siswa. Hasil cohort lengkap tidak boleh dihitung dengan menganggap peserta yang gagal sebagai waktu tunggu nol.

Sebanyak 63 ID kiriman yang diterima tercatat pada sampling SQL, semuanya cocok dengan ID kiriman yang diketahui generator; tidak ditemukan kiriman tambahan tanpa pasangan pada sampling itu. Hasil yang selesai: 32 Executed dan 31 Accepted. Ini pengamatan dari sampling/trace, bukan bukti formal bahwa setiap kemungkinan kegagalan koneksi sudah tertangani.

Kelas uji dihapus dan 30 akun uji dinonaktifkan. Worker/runner normal 50/50 dipulihkan oleh wrapper. Konfigurasi 8 slot diulang dengan akun/kelas baru pada direktori lain; hasil percobaan ini tidak ditimpa.

[Data mentah/anomali](results.json), [trace dan masalah join](stage-analysis.json), [log layanan](service-profile.log), [permintaan HTTP](requests.csv), [catatan antrean](queue.csv), [konfigurasi aktual](runtime-config.json).
