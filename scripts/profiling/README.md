# Pengukuran tahap penilaian

Alat ini khusus pengujian lokal; kode inti aplikasi tidak diubah. Dari root project, gunakan PowerShell 7:

```powershell
./scripts/test-judging-profile.ps1 -SelfCheck
./scripts/test-judging-profile.ps1
```

Docker harus aktif dan akun bootstrap di `.env` harus tersedia. Pastikan tidak ada pekerjaan pengguna aktif karena lima layanan akan direstart sementara. Batas/concurrency asli dipertahankan. Wrapper menyimpan image asli dan memulihkannya di `finally`; penghentian paksa proses tetap memerlukan pemeriksaan manual.

Alur: kontrol runner tanpa profiler → instrumentasi sementara → kontrol dengan profiler → 4 baseline API → 30 Run → 30 Submit → analisis → pemulihan layanan. Fixture menggunakan kelas/path baru dan 30 akun baru. Kelas dihapus, akun dinonaktifkan. Permintaan yang ditolak 429 dikirim ulang terkontrol oleh alat uji.

Hasil disimpan di `artifacts/performance/judging-profile-*/`: laporan Markdown baru, `results.json`, trace JSONL, `stage-analysis.json`, `job-stages.csv`, dan `container-stages.csv`. Laporan mencakup jalur antar-container, timeline pekerjaan terburuk yang nyata, serta pembanding konfigurasi lama jika tersedia. `runtime-config.json` memverifikasi concurrency/jumlah proses Celery dan interval scheduler; `runner-runtime.json` memverifikasi slot runner. `resources.jsonl` mencatat CPU/memori VM Docker keseluruhan setiap detik, bukan penggunaan per sandbox.

Command Celery mengikuti Compose, bukan angka concurrency yang ditanam di profiler. Build dan aktifkan konfigurasi yang hendak diuji sebelum menjalankan wrapper. Wrapper tidak menaikkan kuota pending kelas. Saat ini kuota 20 dapat membuat burst 30 ditolak sebagian, walaupun worker/runner disetel 50.

`analyze.py` memeriksa kelengkapan join, jumlah container/compiler, dan penjumlahan critical path. Untuk analisis ulang dengan Python 3.10+:

Catatan API/worker dihubungkan berdasarkan induk span dan proses, sehingga event commit tidak hilang saat jam dinding bergeser terhadap durasi monotonic. Self-check mencakup kasus tersebut; data mentah tetap diperlukan untuk analisis ulang.

```powershell
python scripts/profiling/analyze.py artifacts/performance/<direktori-hasil>
python scripts/profiling/report.py artifacts/performance/<direktori-hasil> artifacts/performance/judging-profile-20261104-093052-80dbc2
```

Pastikan `python` menunjuk Python 3, bukan instalasi Python 2 lama. `check.py` memeriksa nesting span, propagasi error, dan pengecualian metadata sensitif. Trace tidak merekam source, input, password, atau token. Pengukuran dapat menambah overhead; bandingkan kontrol sebelum menafsirkan hasil. Durasi nested dan lifetime PID1 saling tumpang tindih, sehingga bukan komponen yang dapat dijumlahkan ke total runner.

Generator laporan menolak menimpa laporan yang sudah ada. Analisis ulang dapat mengganti JSON/CSV hasil turunan pada direktori yang diberikan; gunakan hanya direktori pengujian yang hendak dianalisis.

Runner terbaru memakai satu container fisik per Run/Submit. `container_count` menghitung operasi create, sedangkan `execution_phase_count` menghitung kompilasi dan setiap input. Container di-start kembali di antara fase agar proses/file sementara bersih. Trace merekam ID container per fase dan analisis memeriksa ID yang sama sepanjang pekerjaan. Image profiling mengikuti `SANDBOX_IMAGE` Compose, termasuk versi `gcc12-v2`; laporan lama tidak ditulis ulang.

Pengawasan runner terbaru memakai wait pemberitahuan Docker dan timer, sehingga normalnya hanya satu `runner.inspect` per fase (di akhir, untuk exit code/OOM). `runner.container_wait` sekarang mencakup waktu menunggu compiler/program; kenaikan interval wait tidak boleh langsung ditafsirkan sebagai kenaikan overhead Docker. `check_reuse.py` juga memeriksa tepat tiga wait/inspeksi untuk kompilasi dan dua input tanpa error. Timer/penanganan output hanya melakukan inspeksi tambahan jika kill beradu dengan program yang sudah selesai. Pembersihan orphan berkala tetap independen.

## Membandingkan kapasitas paralel

```powershell
./scripts/test-slot-sweep.ps1
# Satu kapasitas, worker dan slot runner sama-sama 8:
./scripts/test-judging-profile.ps1 -Slots 8
# Melanjutkan sweep yang terputus tanpa mengulang konfigurasi yang sudah selesai:
./scripts/test-slot-sweep.ps1 -ResumeDirectory artifacts/performance/<direktori-slot-sweep>
```

Sweep default membandingkan 4, 8, 12, dan 16 proses worker/slot runner secara berurutan. Override hanya aktif selama profiling; `compose.yaml` tidak diedit, dan setiap child benchmark memulihkan image serta command normal melalui `finally`. Kontrol tanpa profiler mengirim RPC langsung satu per satu pada konfigurasi normal, sehingga tidak menguji concurrency kontrol. Preflight menolak restart bila ada pekerjaan database yang aktif.

Setiap kapasitas mempunyai direktori hasil sendiri. Direktori sweep menyimpan `manifest.json`, `comparison.json`, dan `LAPORAN_PERBANDINGAN_SLOT.md`; laporan per kapasitas tetap memuat timeline dan jalur antar-container. Kriteria kandidat adalah jumlah P95 Run dan Submit sejak percobaan pertama, termasuk penolakan 429 dan jeda retry alat uji. Waktu setelah request diterima dan waktu runner juga ditampilkan terpisah.

Jika cohort gagal/tidak lengkap, sweep berhenti setelah pemulihan layanan. `-ResumeDirectory` mempertahankan percobaan gagal dan menulis percobaan pengganti ke direktori baru. Peringkat memakai cohort lengkap; kegagalan tetap dicantumkan sebagai temuan stabilitas dan tidak boleh disembunyikan. Akun/kelas fixture baru dipakai pada setiap pengulangan. Satu pengulangan berurutan belum menghilangkan efek urutan/cache/variasi host; kandidat perlu dikonfirmasi sebelum mengubah konfigurasi normal.

## Kapasitas host

`capacity.py` mengukur detik-CPU per Run atau Submit dan throughput runner, langsung ke runner tanpa database. Cara pakai dan cara memakai hasilnya untuk menghitung kebutuhan server ada di [LAPORAN_KEBUTUHAN_SERVER.md](../../LAPORAN_KEBUTUHAN_SERVER.md).
