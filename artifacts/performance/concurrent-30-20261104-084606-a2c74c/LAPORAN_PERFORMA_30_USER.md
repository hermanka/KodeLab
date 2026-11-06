# Laporan pengujian konkuren 30 pengguna — 4 November 2026

**Kesimpulan:** 30 pengguna dapat mengakses kelas/path yang sama dan semua 120 pekerjaan akhirnya selesai dengan verdict yang benar. Namun, konfigurasi saat ini tidak menerima semua kiriman serentak: burst 30 menolak 10 permintaan, dan burst campuran 60 menolak 38 permintaan pada gelombang awal. Antrean dan penolakan kapasitas adalah hambatan utama; tidak ditemukan salah nilai atau kegagalan compiler/eksekusi pada program uji ini.

## Lingkungan dan metode

- Waktu: 4 November 2026, 08:46:09–08:50:43 WIB; total 273.906 detik termasuk setup dan cleanup.
- Docker Desktop 29.1.2, 12 vCPU tersedia bagi Docker, 15.52 GiB RAM; bukan server produksi dengan jaringan pengguna sebenarnya.
- API/FastAPI, MariaDB, Redis, Celery worker concurrency 2, validator concurrency 1, runner 3 slot. Tidak ada perubahan kuota, konfigurasi layanan, atau kode aplikasi selama pengujian.
- Satu container pembangkit beban terpisah pada host Docker yang sama; koneksi HTTP nyata ke api:8000. Bukan 30 browser yang merender JavaScript/CSS.
- 30 akun siswa sementara, satu kelas privat, satu path dengan satu materi wajib dan satu latihan wajib. Seluruh akun memakai path dan versi soal yang sama.
- Penilai custom bawaan, 15 pengguna C17 dan 15 C++17. Lima test case per submit: positif, negatif, nol, pembatalan bilangan besar, dan jumlah besar. Run memakai input berbeda per akun agar pencampuran hasil bisa terdeteksi.
- Barrier asyncio melepaskan permintaan serentak. Rentang peluncuran aktual: run_30_wave_1 = 27.519 ms; submit_30_wave_1 = 18.814 ms; mixed_60_wave_1 = 41.057 ms. Ini waktu dispatch dari generator, bukan bukti seluruh paket tiba bersamaan di database.
- Setelah mencatat respons awal tanpa retry tersembunyi, harness menunggu pekerjaan diterima selesai lalu mengirim ulang yang ditolak 429. Angka selesai seluruh pengguna bergantung pada retry terkontrol ini.
- Poll status setiap 1 detik, sampling SQL setiap sekitar 250 ms; keduanya menambah beban pengukuran. Probe pembacaan learning path dijalankan sepanjang fase penilaian.
- Skenario 60 adalah stres API tambahan. UI satu tab menonaktifkan tombol Run dan Submit bersamaan saat satu pekerjaan diproses; satu tab normal tidak mengirim kedua tombol pada saat yang sama.

## Respons akses 30 pengguna

P95 memakai nearest-rank: 95% sampel berada di bawah atau sama dengan angka tersebut. Satuan tabel ini milidetik.

| Operasi | Sampel | HTTP berhasil | Median ms | P95 ms | Maksimum ms |
| --- | --- | --- | --- | --- | --- |
| Login serentak | 30 | 30 | 521.005 | 685.963 | 688.501 |
| HTML halaman utama | 30 | 30 | 98.784 | 119.090 | 120.294 |
| Daftar kelas | 30 | 30 | 671.158 | 763.021 | 763.377 |
| Learning path dalam kelas yang sama | 30 | 30 | 616.750 | 843.511 | 844.574 |
| Enrollment path yang sama | 30 | 30 | 603.544 | 928.973 | 929.837 |
| Membaca materi yang sama | 30 | 30 | 925.423 | 1207.259 | 1207.801 |
| Menyelesaikan materi wajib | 30 | 30 | 614.760 | 779.827 | 786.182 |
| Probe /my/learning selama penilaian | 225 | 225 | 51.045 | 426.804 | 1824.081 |

Seluruh akses, login, enrollment, dan penyelesaian materi berhasil. Sebanyak 225 probe /my/learning selama pemrosesan tetap HTTP 200; tidak ada HTTP 5xx yang tercatat pada keseluruhan uji.

## Penerimaan run dan submit

| Skenario | Permintaan awal | 202 awal | 429 awal | Ditolak awal | Hasil akhir setelah retry | Durasi fase s |
| --- | --- | --- | --- | --- | --- | --- |
| 30 run | 30 | 20 | 10 | 33.3% | {"EXECUTED":30} | 36.333 |
| 30 submit benar | 30 | 20 | 10 | 33.3% | {"ACCEPTED":30} | 85.402 |
| 60 campuran (30 run + 30 submit) | 60 | 22 | 38 | 63.3% | {"EXECUTED":30,"WRONG_ANSWER":10,"ACCEPTED":20} | 129.328 |

- Run 30: gelombang 20 + 10 pekerjaan.
- Submit 30: gelombang 20 + 10 pekerjaan.
- Campuran 60: gelombang 22 + 20 + 18 pekerjaan. Dari 38 yang ditolak awal, 18 masih ditolak pada retry pertama; seluruhnya diterima pada retry berikutnya.
- Ada 76 respons 429 keseluruhan, termasuk percobaan ulang. Seluruhnya berpesan Class submission/run quota exceeded. Ini penolakan admission, bukan job yang sudah masuk antrean.
- Pada burst campuran, 22 pekerjaan diterima selama jendela HTTP sekitar 5.727 detik. Ini tidak melanggar cap 20 pending: beberapa pekerjaan selesai ketika permintaan berikutnya masih diproses. Sampling maksimum pending tetap 20.

## Pending, waktu antre, dan waktu proses

Waktu antre diambil dari created_at submission sampai waktu claim yang direkonstruksi dari lease_until dikurangi lease 180 detik. Waktu proses adalah claim sampai finished_at. Timestamps database saat ini beresolusi detik, sehingga angka antre/proses dibulatkan secara alami oleh penyimpanan. Seluruh 120 job berhasil tertangkap saat running.

| Skenario | Antre median s | Antre P95 s | Antre maks s | Proses median s | Proses P95 s | Proses maks s |
| --- | --- | --- | --- | --- | --- | --- |
| 30 run | 8 | 19 | 19 | 2 | 3 | 3 |
| 30 submit benar | 19 | 50 | 53 | 5 | 6 | 6 |
| 60 campuran (30 run + 30 submit) | 17 | 46 | 53 | 3 | 7 | 7 |

Waktu terlihat selesai di generator berikut mencakup HTTP, polling, dan retry admission. Polling mulai setelah gelombang admission selesai; karena itu ini pengukuran konservatif dari harness, bukan pengukuran waktu render UI. Nilai accepted-to-result tidak memasukkan penolakan admission sebelumnya; user-wait menghitung sejak percobaan pertama.

| Skenario | Accepted→terlihat selesai P95 s | Sejak percobaan pertama median s | Sejak percobaan pertama P95 s | Sejak percobaan pertama maks s |
| --- | --- | --- | --- | --- |
| 30 run | 20.502 | 18.014 | 34.947 | 36.309 |
| 30 submit benar | 55.652 | 46.564 | 84.742 | 85.393 |
| 60 campuran (30 run + 30 submit) | 52.594 | 62.809 | 125.996 | 129.292 |

- Maksimum job running teramati: 2. Maksimum queued: 20. Maksimum pending (queued + running + retry_pending pada waktu yang sama): 20. Puncak queued dan running dapat terjadi pada waktu berbeda; jangan menjumlahkan kedua puncak.
- Semua fase mencapai antrean kosong pada akhir fase. Tidak ada job hilang atau tertinggal, dan tidak ada retry eksekusi oleh worker.
- Ketika run diterima, job melewati antrean seperti submit. Submit menjalankan lima kasus pada container terpisah sehingga memerlukan waktu lebih lama dibanding run satu input.

## Ketepatan hasil dan progres

- 60 run menghasilkan EXECUTED, output sesuai input unik tiap akun, score null.
- 50 submit benar menghasilkan ACCEPTED dan nilai 100.
- 10 submit kontrol dengan program yang tidak mencetak jawaban menghasilkan WRONG_ANSWER dan nilai 0. Wrong Answer ini memang diharapkan, bukan kegagalan sistem.
- Salah verdict/nilai/output: 0; COMPILATION_ERROR/RUNTIME_ERROR/TLE/MLE/OUTPUT_LIMIT/system_error pada program uji: 0; retry eksekusi: 0.
- Test case tersembunyi tidak membocorkan input/expected/stdout/stderr melalui hasil siswa.
- Setelah run, progres seluruh peserta tetap 50% (materi selesai, latihan belum selesai) dan nilai coding 0. Setelah submit benar, 30/30 peserta mencapai progres 100% dan nilai 100.
- Submit ulang dan jawaban salah sesudah Accepted tidak mengubah skor, progres, atau waktu penyelesaian final yang sudah tercatat. Leaderboard kelas memuat 30 peserta, semua bernilai 100.

## Anomali dan analisis

### 1. Kapasitas admission belum memenuhi seluruh kelas 30 orang tanpa penolakan

Ini batas konfigurasi yang bekerja sesuai kode, tetapi menjadi masalah operasional untuk skenario pengguna: 33,3% permintaan awal ditolak pada burst 30; 63,3% pada burst 60. Kode app/main.py membatasi pending kelas 20, pending global 50, pending akun 10, dan pekerjaan kelas 200 per jam. Run dan submit memakai kuota yang sama.

UI web saat ini menampilkan error dan mengaktifkan tombol kembali jika POST mendapat 429; tidak otomatis menunggu lalu mengirim ulang. Jadi keberhasilan 30/30 setelah retry dalam benchmark tidak berarti semua siswa otomatis selesai tanpa tindakan. Permintaan 429 belum dibuatkan job dan tidak akan selesai sendiri jika hanya dibiarkan menunggu.

### 2. Antrean puluhan detik walaupun program sederhana

Antre maksimum 53 detik, sementara proses submit median sekitar 5 detik. Dua slot worker membatasi jumlah pekerjaan siswa yang benar-benar berjalan; slot ketiga runner tidak otomatis dipakai oleh antrean submission. Dispatch juga dipicu lewat Celery setiap 5 detik dan task dispatch berbagi antrean dengan job submission, sehingga berpotensi ikut tertunda ketika worker penuh. Kontribusi pasti dispatch terhadap setiap job belum diprofilkan terpisah.

### 3. Satu RemoteProtocolError saat polling hasil

Pada +147,827 detik (sekitar 08:48:37 WIB), GET status hasil pengguna uji 1 gagal dengan RemoteProtocolError setelah 77,425 ms. Frekuensi 1 dari 2.213 poll (0.0452%). Poll berikutnya berhasil, pekerjaan selesai dengan hasil benar, dan tidak ada retry eksekusi. Seluruh permintaan admission memiliki respons HTTP, tidak ada 5xx.

Log API/worker pada rentang uji tidak menunjukkan traceback atau kegagalan proses. Penyebab transport belum dapat dipastikan; penutupan koneksi/keepalive adalah hipotesis, bukan temuan yang sudah terbukti. Harness toleran terhadap satu GET gagal. UI sendCode saat ini justru keluar dari loop ketika fetch status melempar error, sehingga gangguan serupa di browser berpotensi menampilkan error meskipun job tetap berjalan; siswa dapat meninjau Riwayat kode.

### 4. Dua peringatan cleanup sandbox NotFound

Log runner merekam Sandbox cleanup error: NotFound pada 08:49:38 dan 08:50:19 WIB. Tidak ada kegagalan penilaian yang berkorelasi; pemeriksaan setelah uji menemukan 0 sandbox tertinggal.

Pemeriksaan runner/engine.py dan Docker SDK 7.1 menunjukkan jalur race yang mungkin: containers.list() melakukan inspect masing-masing container dengan ignore_removed=False; execute() dapat menghapus container sebelum inspect selesai. NotFound dari list terjadi sebelum try/except di dalam loop cleanup_expired. Kandidat perbaikan adalah ignore_removed=True atau perlindungan NotFound pada listing, lalu diuji khusus. Ini penjelasan berdasarkan kode; traceback penuh kejadian tidak tersedia untuk membuktikan jalur persisnya.

### 5. Artefak sampling external_pending, bukan bukti antrean pengguna lain

Raw JSON menampilkan puncak external_pending=1 pada lima sampel. Sampler awal mengurangi hitungan own dari hitungan global melalui dua SELECT pada READ COMMITTED; job uji baru yang masuk di antaranya dapat terhitung seolah pekerjaan luar. Pemeriksaan independen terhadap histori job yang overlap rentang uji menemukan 0 pekerjaan lain. Nilai external_pending mentah tidak dipakai untuk menyimpulkan adanya beban pengguna lain. Sampler untuk pengujian berikutnya sudah diperbaiki menghitung owner di luar 30 akun secara langsung; data mentah pertama tetap dipertahankan.

## Sumber daya teramati

| Container | Sampel | Puncak CPU % Docker | Puncak RAM MiB |
| --- | --- | --- | --- |
| judgementsystem-api-1 | 64 | 262.21 | 679.60 |
| judgementsystem-scheduler-1 | 64 | 2.04 | 68.98 |
| judgementsystem-validator-1 | 64 | 12.01 | 116.20 |
| judgementsystem-worker-1 | 64 | 83.02 | 182.10 |
| judgementsystem-runner-1 | 64 | 79.45 | 73.32 |
| judgementsystem-redis-1 | 64 | 8.00 | 9.99 |
| judgementsystem-db-1 | 64 | 21.28 | 149.00 |
| judgementsystem-api-run-2ee1eba2e0c1 | 64 | 104.65 | 87.73 |

CPU 100% Docker berarti kira-kira satu inti, bukan seluruh 12 vCPU. Sampling hanya mencakup layanan dengan nama judgementsystem dan container generator, bukan semua sandbox js-* yang sangat singkat. Angka ini tidak cukup untuk menyimpulkan CPU total longgar atau kapasitas maksimum compiler. Tidak ada restart/OOM yang teramati; layanan utama sehat setelah uji.

## Rekomendasi, belum diterapkan ke aplikasi

1. Tetapkan target: 30 job bersamaan diterima atau 60 jika run+submit multi-tab/API diizinkan. Sesuaikan cap kelas dan global dengan cadangan untuk kelas lain. Menaikkan cap hanya memperpanjang ruang antrean; tidak mempercepat eksekusi.
2. Ukur ulang dengan jumlah worker/runner yang selaras dengan CPU/RAM, sambil menjaga kapasitas validasi. Jangan menaikkan concurrency worker tanpa menyesuaikan kapasitas runner karena dapat menghasilkan busy/503 dan retry.
3. Pertimbangkan retry/backoff admission 429 dengan pesan antrean yang jelas dan idempotensi; bedakan pekerjaan yang ditolak dengan yang sudah queued.
4. Tambahkan retry terbatas untuk GET status yang gagal sementara, sehingga error transport tidak langsung memutus pemantauan job.
5. Perbaiki race cleanup listing NotFound dan tambahkan uji regresi; pertimbangkan isolasi antrean dispatch agar tidak tertahan kompilasi.

## Batas kesimpulan dan cleanup

- Ini satu run dengan satu burst awal per skenario, program penjumlahan sederhana, dan retry gelombang. Belum mengukur beban berkelanjutan berjam-jam, program berat/malicious, lintas banyak kelas, atau jaringan browser nyata.
- Penilaian memakai custom bawaan. Performa plugin lain, AST pedagogis, dan DOMjudge tidak diukur.
- Kelas uji beserta histori akademiknya dihapus setelah hasil diekspor. Semua 30 akun uji dinonaktifkan; akun dan auditnya tetap tersimpan untuk keterlacakan. Verifikasi independen: 0 kelas uji tertinggal, 0 akun uji aktif, 0 sandbox tertinggal. Akun/kelas yang sudah ada tidak dihapus.
- Kode aplikasi dan konfigurasi kapasitas tidak diubah. Yang ditambahkan adalah generator uji, wrapper pengukuran, dan laporan. Perbaikan sampler external_pending hanya memengaruhi alat uji untuk run selanjutnya.

## Berkas dan pengulangan

- [results.json](results.json): data mentah seluruh job, request, burst, status SQL, dan summary.
- [requests.csv](requests.csv), [jobs.csv](jobs.csv), [queue.csv](queue.csv): data untuk analisis ulang.
- [environment.json](environment.json), [resources.jsonl](resources.jsonl), [run.log](run.log), [service-errors.log](service-errors.log).
- [Generator Python](../../../scripts/load-concurrent.py) dan [wrapper PowerShell](../../../scripts/test-concurrent-users.ps1).

Jalankan dari root proyek menggunakan PowerShell 7 dan Docker yang sudah aktif. Kredensial bootstrap dibaca di memori dari .env dan diteruskan melalui stdin; tidak ditulis ke laporan.

```powershell
./scripts/test-concurrent-users.ps1 -SelfCheck
./scripts/test-concurrent-users.ps1
```

Pengulangan membuat 30 akun sementara baru dan kelas privat baru, lalu menghapus kelas serta menonaktifkan akun itu. Setiap run menghasilkan folder artifacts/performance/concurrent-30-<waktu>-<id> baru. Ulangi saat server tidak digunakan kelas lain karena beban kompilasi memang akan memakai sumber daya yang sama.
