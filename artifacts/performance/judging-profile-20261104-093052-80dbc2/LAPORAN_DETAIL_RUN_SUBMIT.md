# Profil waktu Run dan Submit — 4 November 2026

Antrean merupakan penyebab terbesar pengguna menunggu. Pada burst Submit, rata-rata **23,634 detik dari 31,040 detik sampai hasil tersimpan** dihabiskan sebelum worker mulai bekerja: sekitar **76%**. Pembuatan container saja bukan faktor terbesar; seluruh siklus create/start/remove tetap merupakan biaya penting di dalam runner.

## Lingkungan dan metode

- Docker lokal: 12 vCPU, RAM 15,52 GiB. Worker kiriman 2 proses, validator 1 proses, runner 3 slot. Batas pending kelas tetap 20; dispatcher periodik tetap 5 detik.
- Provider `custom` bawaan. Kelas privat sementara, satu learning path, satu materi dan soal penjumlahan dengan 5 test case. Sebanyak 30 siswa: 15 C17 dan 15 C++17.
- Empat pekerjaan tunggal sebagai baseline API, kemudian 30 Run serentak dan 30 Submit serentak: **64 pekerjaan API**. Run mengompilasi lalu menjalankan satu input; Submit mengompilasi lalu menjalankan 5 kasus secara berurutan.
- Sepuluh permintaan pada setiap burst awal ditolak HTTP 429. Alat uji mengirim ulang setelah gelombang sebelumnya selesai. Retry admission ini bukan retry eksekusi, dan bukan perilaku otomatis UI.
- Polling hasil dimulai segera setelah masing-masing respons diterima, setiap 1 detik, secara independen dari permintaan peserta lain.
- Instrumentasi sementara mencatat timestamp API, transaksi, publikasi Celery, worker, HTTP runner, Docker API, kompilasi, dan pemeriksaan output. Sebanyak **10.877 rekaman**, seluruh **64/64 pekerjaan berhasil dihubungkan**, tanpa masalah validasi analisis.
- Image/command layanan asli dipakai melalui override sementara; batas keamanan sandbox dipertahankan. Setelah pengujian, image, command, dan konfigurasi layanan semula dipulihkan. Kelas uji dihapus dan 30 akun uji dinonaktifkan.

Ini pengujian HTTP dan compiler nyata, bukan 30 browser. Nama fixture dan identitasnya tersedia pada `results.json`; data kelas pengguna sebelumnya tidak digunakan sebagai fixture.

## Waktu pada setiap tahap

Satuan **detik**. Rata-rata dan P95 berasal dari 30 pekerjaan pada setiap skenario. P95 berarti setidaknya 95% pengamatan tidak lebih lambat dari angka tersebut; P95 antartahap tidak boleh dijumlahkan.

| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container yang terlibat |
|---|---:|---:|---:|---:|---|
| Menunggu pemicu scheduler setelah commit | 2,873 | 3,558 | 2,410 | 4,935 | `api` → `db` (pekerjaan tersimpan); `scheduler` → `redis` saat jadwal tiba. Sandbox pekerjaan ini belum dibuat. |
| Dispatcher menunggu giliran worker setelah commit | 0,007 | 0,007 | **9,496** | **34,588** | Pesan dispatcher menunggu di jalur `redis` → `worker`, termasuk kemungkinan sudah diambil/reservasi Celery. Dua proses di container `worker` berbagi tugas dispatch dan eksekusi. Sandbox pekerjaan ini belum dibuat. |
| Dispatcher menyiapkan publikasi pekerjaan | 0,015 | 0,025 | 0,013 | 0,021 | Dispatcher berjalan di `worker` → membaca/memperbarui `db` dan mengirim pesan eksekusi ke `redis`. |
| Total commit API → publikasi pekerjaan (outbox) | **2,894** | 3,575 | **11,918** | 39,435 | Gabungan jalur `api` → `db`, lalu `scheduler` → `redis` → `worker` → `db`/`redis`. |
| Publikasi pekerjaan → worker mulai | **9,471** | 22,729 | **11,716** | 33,296 | Pesan eksekusi menunggu pada jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox pekerjaan ini belum dibuat. |
| Worker memanggil runner melalui HTTP | 2,464 | 2,928 | 6,085 | 7,056 | `worker` → `runner` → Docker Engine host → sandbox sementara. Proses worker tetap menunggu respons HTTP selama runner bekerja. |
| Di dalam runner, bagian dari HTTP di atas | **2,388** | 2,844 | **6,012** | 6,986 | `runner` mengendalikan sandbox kompilasi, lalu sandbox program melalui Docker Engine. Run: 2 container; Submit: 6 container, berurutan per pekerjaan. |
| Worker memvalidasi dan menyimpan hasil | 0,042 | 0,080 | 0,034 | 0,049 | `worker` memvalidasi hasil di prosesnya sendiri → `db` menyimpan verdict, nilai, dan progres. Sandbox sudah dibersihkan runner. |
| **Request diterima server → hasil tersimpan** | **15,883** | **29,300** | **31,040** | **63,690** | Seluruh jalur `api`, `db`, `scheduler`, `redis`, `worker`, `runner`, dan sandbox sementara. |
| Tambahan sampai polling klien melihat hasil | 0,575 | 0,997 | 0,501 | 0,977 | Klien uji → `api` → `db` → klien uji, termasuk jeda polling. Tidak memanggil sandbox kembali. |
| **Request diterima server → hasil terlihat klien uji** | **16,458** | **29,723** | **31,541** | **64,107** | Seluruh jalur di atas, termasuk pengambilan hasil oleh klien uji. |

Nama pada kolom jalur memakai nama service di `compose.yaml`; container layanan pada pengujian bernama `judgementsystem-<service>-1`. **Dispatcher bukan container terpisah:** `scheduler` hanya memublikasikan tugas periodik, sedangkan fungsi dispatcher dijalankan oleh container `worker` yang juga menangani kiriman. Container `validator` digunakan untuk validasi kunci pengajar, bukan jalur normal Run/Submit siswa pada tabel ini. Docker Engine berjalan pada host Docker, bukan di dalam container `runner`. Sandbox sementara bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run`; nama runtime dipakai lagi setelah container kasus sebelumnya dihapus.

Dengan demikian, dua tahap antrean panjang terjadi **sebelum sandbox pekerjaan tersebut dibuat**. Memakai kembali sandbox tidak langsung menghapus kedua antrean itu. Namun, eksekusi yang lebih singkat dapat membuat worker lebih cepat tersedia bagi pekerjaan berikutnya; besarnya dampak tidak langsung ini harus diukur ulang.

Baris outbox mencakup tiga baris sebelumnya, dan baris runner berada di dalam HTTP runner. Jangan menjumlahkan keduanya sebagai tahap terpisah.

Jalur yang dapat dijumlahkan tanpa tumpang tindih adalah: API sampai commit → outbox → antre worker → claim/load worker → HTTP runner → validasi/simpan. Rata-rata API sampai commit adalah 0,715 detik untuk Run dan 0,981 detik untuk Submit; claim/load masing-masing 0,016 dan 0,013 detik. Selisih request awal dengan awal handler mencakup pemrosesan HTTP/dependensi sebelum handler. CSV menyediakan seluruh interval dan pemeriksaan bahwa jumlah jalur sesuai totalnya.

Jika dihitung sejak percobaan pertama, termasuk HTTP 429 dan retry terkontrol, rata-rata sampai hasil tersimpan menjadi **25,916 detik untuk Run** dan **53,100 detik untuk Submit**. Waktu terlama sampai hasil terlihat sejak percobaan pertama masing-masing **47,290 dan 97,300 detik**. Angka ini berbeda dari durasi pekerjaan yang sudah diterima.

## Timeline pekerjaan terburuk yang benar-benar terjadi

Setiap timeline berikut memakai satu pekerjaan yang sama, bukan menjumlahkan maksimum dari pekerjaan berbeda. Satuan detik relatif terhadap awal permintaan pertama. Titik nol mewakili klik Run/Submit melalui pengiriman HTTP oleh alat uji; waktu event klik/render browser tidak diukur. Angka dibulatkan tiga desimal, sehingga durasi sangat singkat dapat tampak nol.

### Submit terlama yang langsung diterima: 66,188 detik

Peserta indeks 13, C++17, attempt `df7bfd25-fafd-4d26-82a2-cd3ad0d5b078`. Permintaan langsung memperoleh HTTP 202 pada t=2,311; tidak ada 429 atau retry admission pada pekerjaan ini.

| Urutan | Rentang sejak request pertama | Durasi | Proses dan jalur container |
|---|---:|---:|---|
| 1 | 0,000–0,463 | 0,463 | Pengiriman HTTP dan pemrosesan sebelum masuk handler `api`. |
| 2 | 0,463–2,283 | 1,820 | `api` memvalidasi/menerima pekerjaan dan commit ke `db`. |
| 3 | 2,283–6,581 | 4,297 | Menunggu jadwal; `scheduler` memublikasikan tugas dispatcher ke `redis`. |
| 4 | 6,581–41,169 | **34,588** | Dispatcher menunggu pada jalur `redis` → `worker` yang sibuk menangani eksekusi lain. Sandbox pekerjaan ini belum dibuat. |
| 5 | 41,169–41,190 | 0,021 | Dispatcher berjalan di `worker`, membaca `db` dan memublikasikan pesan eksekusi ke `redis`. |
| 6 | 41,190–59,748 | **18,557** | Pesan eksekusi menunggu giliran di jalur `redis` → `worker`. Sandbox pekerjaan ini belum dibuat. |
| 7 | 59,748–59,759 | 0,011 | `worker` mengklaim pekerjaan dan memuat source/test case dari `db`. |
| 8 | 59,759–65,334 | **5,575** | `worker` memanggil `runner` dan menunggu respons; runner mengelola sandbox kompilasi dan lima sandbox kasus melalui Docker Engine. |
| 9 | 65,334–65,358 | 0,024 | `worker` memvalidasi dan menyimpan Accepted/nilai/progres ke `db`. |
| 10 | 65,358–66,188 | 0,831 | Jeda polling serta pengambilan hasil oleh klien melalui `api` → `db`. |

Rincian langkah 8 di bawah merupakan interval di dalam pemanggilan HTTP, **bukan tambahan setelah langkah 8**. Setiap interval sandbox mencakup create/start, penyiapan input/output, menunggu kompilasi/program, dan cleanup; bukan CPU murni compiler/program.

| Rentang sejak request pertama | Aktivitas di runner/sandbox |
|---:|---|
| 59,759–59,800 | Pengiriman HTTP/persiapan sebelum fase sandbox kompilasi. |
| 59,800–61,518 | Sandbox kompilasi. |
| 61,518–62,342 | Sandbox program kasus 1. |
| 62,342–63,178 | Sandbox program kasus 2. |
| 63,179–64,011 | Sandbox program kasus 3. |
| 64,011–64,687 | Sandbox program kasus 4. |
| 64,687–65,323 | Sandbox program kasus 5. |
| 65,323–65,334 | Penyelesaian hasil runner dan pengembalian respons ke worker. |

Pada pekerjaan ini sandbox baru mulai diproses sekitar **detik ke-59,8**. Dua antrean dispatcher dan eksekusi berjumlah **53,146 detik**. Inilah contoh nyata bahwa menyingkat lifecycle sandbox saja tidak langsung menghapus penundaan sebelum worker mulai.

### Submit terlama termasuk 429 dan retry alat uji: 97,300 detik

Peserta indeks 25, C++17, attempt `a4e3188f-9178-4db3-8686-3359800976d0`. Jeda retry berasal dari kebijakan alat uji menunggu gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.

| Urutan | Rentang sejak request pertama | Durasi | Proses dan jalur container |
|---|---:|---:|---|
| 1 | 0,000–4,850 | 4,850 | Permintaan pertama ke `api`/`db` ditolak HTTP 429 karena batas pending kelas. |
| 2 | 4,850–66,171 | **61,320** | Alat uji menunggu sebelum mengirim ulang; belum ada pekerjaan yang diterima untuk permintaan ini. Ini bukan antrean sandbox/Celery pekerjaan tersebut. |
| 3 | 66,171–66,269 | 0,098 | Retry HTTP dan pemrosesan sebelum handler `api`. |
| 4 | 66,269–66,611 | 0,343 | `api` menerima pekerjaan dan commit ke `db`. Respons HTTP 202 tiba pada t=66,637. |
| 5 | 66,611–71,553 | 4,941 | Menunggu jadwal `scheduler` → `redis`. |
| 6 | 71,553–72,703 | 1,151 | Dispatcher menunggu giliran pada jalur `redis` → `worker`. |
| 7 | 72,703–72,716 | 0,013 | Dispatcher di `worker` memublikasikan pekerjaan ke `redis`. |
| 8 | 72,716–91,466 | **18,750** | Pekerjaan menunggu giliran worker eksekusi. |
| 9 | 91,466–91,478 | 0,012 | `worker` mengklaim dan memuat pekerjaan dari `db`. |
| 10 | 91,478–97,209 | **5,731** | `worker` → `runner` → sandbox kompilasi dan lima kasus, lalu respons kembali. |
| 11 | 97,209–97,250 | 0,041 | `worker` memvalidasi dan menyimpan hasil ke `db`. |
| 12 | 97,250–97,300 | 0,050 | Klien melihat hasil melalui polling `api` → `db`. |

Dari awal retry yang diterima sampai hasil terlihat, pekerjaan ini membutuhkan **31,129 detik**. Angka 97,300 detik menyertakan penolakan dan jeda retry alat uji; tidak boleh seluruhnya disebut waktu antrean eksekusi.

### Run terlama termasuk 429 dan retry alat uji: 47,290 detik

Peserta indeks 12, C17, attempt `f4a674d2-ff4c-4a7b-ae13-5111ba8518ee`.

| Urutan | Rentang sejak request pertama | Durasi | Proses dan jalur container |
|---|---:|---:|---|
| 1 | 0,000–2,406 | 2,406 | Permintaan pertama ke `api`/`db` ditolak HTTP 429. |
| 2 | 2,406–30,105 | **27,699** | Alat uji menunggu sebelum retry; belum ada pekerjaan yang diterima. |
| 3 | 30,105–30,220 | 0,115 | Retry HTTP dan pemrosesan sebelum handler `api`. |
| 4 | 30,220–30,509 | 0,289 | `api` menerima pekerjaan dan commit ke `db`. Respons HTTP 202 tiba pada t=30,528. |
| 5 | 30,509–33,906 | 3,397 | Menunggu jadwal `scheduler` → `redis`. |
| 6 | 33,906–33,913 | 0,007 | Dispatcher menunggu giliran `worker`. |
| 7 | 33,913–33,932 | 0,019 | Dispatcher di `worker` memublikasikan pekerjaan ke `redis`. |
| 8 | 33,932–43,951 | **10,019** | Menunggu worker eksekusi. |
| 9 | 43,951–43,961 | 0,011 | `worker` mengklaim dan memuat pekerjaan dari `db`. |
| 10 | 43,961–46,477 | **2,515** | `worker` → `runner` → satu sandbox kompilasi dan satu sandbox program, lalu respons kembali. |
| 11 | 46,477–46,493 | 0,016 | `worker` menyimpan hasil Executed ke `db`. |
| 12 | 46,493–47,290 | 0,797 | Klien melihat hasil melalui polling `api` → `db`. |

Dari awal retry yang diterima sampai hasil terlihat, pekerjaan ini membutuhkan **17,185 detik**. Ini pekerjaan dengan total sejak percobaan pertama paling lama; bukan berarti tiap komponennya juga paling lama dari semua Run. Identitas dan interval presisi dapat ditelusuri melalui `results.json`, `job-stages.csv`, dan trace JSONL.

## Biaya di dalam runner

Rata-rata dalam detik per pekerjaan; jumlah seluruh container, bukan per container.

| Bagian | Run: 2 container | Submit: 6 container | Jalur container yang terlibat |
|---|---:|---:|---|
| Membuat container (`create`) | 0,275 | **0,813** | `runner` → Docker Engine host: membuat sandbox kompilasi/program. |
| Menyalakan container (`start`) | 0,554 | **1,615** | `runner` → Docker Engine host → memulai proses di sandbox. |
| Menghapus container (`remove`) | 0,074 | **0,214** | `runner` → Docker Engine host: menghapus sandbox yang selesai/gagal. |
| **Subtotal create/start/remove** | **0,903** | **2,642** | Gabungan tiga operasi lifecycle sandbox di atas. |
| Menyiapkan koneksi stdin | 0,029 | 0,086 | `runner` → Docker Engine host → stdin sandbox. Angka ini mengukur penyiapan koneksi, bukan seluruh transfer input. |
| Menyiapkan koneksi output | 0,051 | 0,165 | `runner` → Docker Engine host → stream stdout/stderr sandbox. Angka ini mengukur penyiapan stream. |
| Inspeksi status Docker | 0,611 | **1,429** | `runner` → Docker Engine host: membaca status sandbox kompilasi/program. |
| Docker wait | 0,021 | 0,065 | `runner` → Docker Engine host: mengambil status akhir sandbox. |
| Kontrol Python, I/O, tidur polling, dan menunggu proses lainnya | 0,773 | 1,624 | Kode pengendali/thread I/O di `runner`, termasuk waktu menunggu compiler/program di sandbox. |
| **Total runner** | **2,388** | **6,012** | `runner` + Docker Engine host + sandbox kompilasi dan program; `worker` menunggu respons sepanjang pemanggilan ini. |

Subtotal create/start/remove menyumbang **43,9% waktu runner Submit**, tetapi hanya sekitar **8,5% waktu sampai hasil tersimpan**. Operasi create sendiri menyumbang 13,5% runner dan 2,6% total tersebut. Container yang sudah tersedia dapat mengurangi sebagian biaya ini, tetapi belum diuji pada arsitektur pool dan belum membuktikan target 5–7 detik untuk 30 pengguna.

Pengukuran diagnostik berikut **tumpang tindih** dengan tabel, sehingga tidak ditambahkan lagi:

- Kompilasi nyata, dari pemanggilan compiler sampai selesai: rata-rata **0,492 detik Run / 0,467 detik Submit**; CPU compiler masing-masing 0,484 / 0,459 detik. Perbedaan kecil dipengaruhi variasi lingkungan; kompilasi tetap dilakukan satu kali per pekerjaan.
- Perbandingan output lima kasus Submit: rata-rata **0,042 milidetik total**, sehingga bukan hambatan pada soal ini. Validasi kontrak hasil worker rata-rata 0,048 milidetik.
- Lifetime PID1 container kompilasi: 1,093 / 1,043 detik. Lifetime container program: 0,546 detik untuk satu kasus Run dan total 2,724 detik untuk lima kasus Submit. Lifetime ini mencakup bootstrap dan pengiriman stdin, **bukan waktu CPU murni program siswa**.
- Pemisahan perkiraan lifetime runtime: sebelum inspeksi pertama setelah stdin terkirim 0,243 / 1,205 detik; sesudahnya 0,302 / 1,518 detik. Bagian sesudah stdin masih dapat mencakup bootstrap, penjadwalan, dan penutupan proses. Tidak dapat disimpulkan bahwa program penjumlahan membutuhkan 0,3 detik CPU.
- Inspeksi Docker dan interval tidur/pengamatan exit ikut menyumbang biaya. Waktu tunggu compiler juga masuk interval kontrol yang belum dipecah; interval tersebut tidak seluruhnya dapat dianggap overhead yang bisa dihapus.

## Anomali dan penyebab antrean

1. **Dispatcher ikut mengantre di worker eksekusi.** Pada Submit, waktu dispatcher menunggu setelah commit rata-rata 9,496 detik, maksimum 34,588 detik. Pesan dispatcher periodik pada keseluruhan pengujian memiliki delay maksimum yang sama. Akibatnya, periode scheduler 5 detik tidak berarti pekerjaan pasti dipublikasikan dalam 5 detik: outbox mencapai **39,540 detik**. Ini bukti penundaan sebelum pekerjaan eksekusi masuk antreannya sendiri.
2. **Dua worker membatasi paralelisme aktual.** Maksimum pekerjaan running teramati 2 meskipun runner mempunyai 3 slot. Antrean setelah publikasi masih rata-rata 11,716 detik pada Submit, maksimum 33,312 detik. Menaikkan batas admission saja akan memungkinkan lebih banyak penunggu, tanpa menambah kapasitas eksekusi.
3. **Lock admission kelas menserialkan sebagian permintaan.** Rata-rata lock Run 0,614 detik dan Submit 0,836 detik; P95 Submit 2,019 detik, maksimum 2,307 detik. Ini memengaruhi penerimaan permintaan sebelum antrean, tetapi jauh lebih kecil daripada total antrean Submit.
4. **Biaya lifecycle Docker berulang pada setiap kasus.** Submit memakai satu container kompilasi dan lima container eksekusi. Pembuatan, start, inspeksi, dan cleanup terakumulasi walaupun program sederhana.
5. **Outlier penyimpanan pertama.** Baseline C17 Run membutuhkan sekitar 469 milidetik setelah runner selesai sampai commit hasil; pada burst Run maksimum sekitar 713 milidetik. Tidak terlihat sebagai biaya dominan berulang. Pengukuran ini belum memisahkan pemanasan koneksi, scheduler host, atau kontensi database sebagai penyebab outlier.

Tidak ditemukan salah output/nilai, kegagalan eksekusi, retry eksekusi, ataupun pemrosesan job ganda dalam 64 pekerjaan. Hasil: **32 Executed dan 32 Accepted**, seluruh 30 siswa mencapai progres/nilai 100. Sebanyak **20 penolakan HTTP 429** sesuai kuota dicatat sebagai `HTTPException` oleh profiler; ini bukan 20 kegagalan compiler. Tidak ada error span eksekusi. Pengamatan ini tidak membuktikan semua bentuk gangguan di luar fixture sudah tercakup.

## Kontrol pengaruh profiler

Delapan RPC langsung ke runner sebelum instrumentasi dan delapan setelahnya: dua pengulangan per bahasa/mode. Tidak melewati API, outbox, atau Celery.

| RPC | Tanpa profiler rata-rata | Dengan profiler rata-rata | Perubahan teramati |
|---|---:|---:|---:|
| C17 Run | 1,346 dtk | 1,515 dtk | +12,5% |
| C17 Submit | 4,137 dtk | 4,405 dtk | +6,5% |
| C++17 Run | 2,035 dtk | 2,262 dtk | +11,1% |
| C++17 Submit | 4,846 dtk | 5,119 dtk | +5,6% |

Sampel kontrol kecil dan dilakukan berurutan, sehingga perbedaan juga mencakup variasi host serta bootstrap image profiling. Angka tersebut bukan estimasi presisi overhead profiler. Hasil burst adalah hasil **dengan instrumentasi**, bukan waktu produksi tanpa profiler. Instrumentasi runtime tetap memakai `execve` asli, tanpa supervisor tambahan pada program siswa.

## Urutan perbaikan yang disarankan

Belum ada optimasi aplikasi yang diterapkan dalam pengujian ini.

1. Hilangkan kontensi dispatcher dengan pekerjaan eksekusi, misalnya jalur dispatch tersendiri atau publikasi segera setelah commit yang tetap memiliki pemulihan outbox. Uji kembali konsistensi/idempotensi dan crash recovery saat mengubahnya.
2. Kurangi biaya lifecycle dan pemantauan Docker, lalu ukur ulang. Pool sandbox memerlukan isolasi proses, workspace, limit sumber daya, reset, dan cleanup yang benar; berbagi thread dalam satu ruang proses tidak otomatis memberi isolasi antarkode siswa.
3. Sesuaikan jumlah worker/slot berdasarkan CPU, RAM, dan hasil uji beban. Mengurangi waktu per pekerjaan membantu throughput; menambah concurrency tanpa kalibrasi bisa memperlambat kompilasi dan memicu limit sumber daya.
4. Setelah antrean membaik, kurangi delay penyampaian hasil. Polling saat ini menambahkan rata-rata sekitar setengah detik. Mengubahnya tidak menyelesaikan antrean puluhan detik.

Target 5–7 detik yang terlihat seluruh 30 pengguna belum tercapai dan belum dapat dijamin hanya dengan menghapus operasi create container. Uji lanjutan perlu memakai burst yang sama setelah setiap perubahan, serta soal dengan kompilasi/input lebih berat dan kondisi kegagalan.

## Berkas dan pengulangan

- [Ringkasan serta HTTP/job mentah](results.json), [analisis semua tahap](stage-analysis.json).
- [CSV per pekerjaan](job-stages.csv), [CSV per container](container-stages.csv), [requests](requests.csv), [sampling antrean](queue.csv), dan folder [trace](traces/).
- [Kontrol tanpa profiler](calibration-unprofiled.json), [kontrol dengan profiler](calibration-profiled.json), [lingkungan/image](environment.json).
- Wrapper: [test-judging-profile.ps1](../../../../scripts/test-judging-profile.ps1); instrumentasi dan analisis: [scripts/profiling](../../../../scripts/profiling/).

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Jalankan saat lingkungan lokal boleh direstart dan tidak ada pekerjaan pengguna aktif. Wrapper membuat fixture baru, menjalankan kontrol, mengaktifkan instrumentasi sementara, menguji, menggabungkan trace, lalu memulihkan layanan di blok `finally`. Kredensial dibaca dari `.env` dan diteruskan lewat stdin, bukan disalin ke laporan. Uji tidak mencatat source/input/expected ke trace; data fixture memang ada dalam hasil uji. Jika proses PowerShell dihentikan paksa, periksa/pulihkan layanan sebelum penggunaan normal.
