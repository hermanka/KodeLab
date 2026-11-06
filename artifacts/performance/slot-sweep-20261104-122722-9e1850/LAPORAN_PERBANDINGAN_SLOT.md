# Perbandingan slot eksekusi — 30 pengguna

**Kandidat terbaik pada cohort lengkap: 8 slot dan 8 proses worker.** Rata-rata sejak percobaan pertama sampai hasil terlihat adalah 13,093 detik untuk Run dan 26,360 detik untuk Submit. Ini termasuk antrean, penolakan 429, dan retry alat uji; target 5–7 detik belum tercapai. Konfigurasi normal telah dipulihkan ke 50/50, bukan otomatis diubah ke kandidat.

Jumlah proses worker eksekusi dan slot runner diubah bersama, dengan nilai yang sama. Ini pengujian kapasitas paralel keseluruhan, bukan isolasi pengaruh semaphore runner saja. Source Compose dan kode aplikasi tidak diubah oleh sweep; konfigurasi normal dipulihkan setelah setiap skenario.

Setiap konfigurasi: 30 akun/kelas baru, satu learning path dan soal penjumlahan, 15 C17/15 C++17, 5 test case, 4 baseline API, 30 Run dan 30 Submit. Ada 8 kontrol RPC tanpa profiler dan 8 dengan profiler. Scheduler tetap 1 detik; dispatcher tetap berbagi worker dengan eksekusi. Batas pending kelas tetap 20.

Pengiriman burst HTTP serentak mewakili klik; waktu render browser tidak diukur. Poll hasil setiap 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; ini bukan retry otomatis UI. Waktu sejak percobaan pertama memasukkan penolakan dan jeda retry tersebut.

## Waktu sejak percobaan pertama sampai hasil terlihat

Semua angka detik. Ini ukuran utama pengalaman 30 peserta, termasuk antrean dan retry admission.

| Slot / proses worker | Run rata-rata | Run P95 | Run maksimum | Submit rata-rata | Submit P95 | Submit maksimum |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 18.872 | 30.147 | 30.178 | 35.545 | 61.496 | 61.727 |
| 8 | 13.093 | 20.818 | 20.820 | 26.360 | 43.858 | 43.890 |
| 12 | 17.261 | 25.574 | 25.584 | 35.981 | 54.257 | 54.319 |
| 16 | 16.714 | 23.287 | 23.635 | 31.120 | 45.182 | 45.194 |

## Waktu setelah request yang diterima dan di dalam runner

Kolom request dimulai dari pengiriman HTTP yang akhirnya diterima, mencakup waktu penerimaan API. Kolom runner hanya bagian eksekusi sehingga tidak boleh dipakai sendiri untuk menilai waktu pengguna.

| Slot | Run request rata-rata / P95 | Run runner rata-rata | Submit request rata-rata / P95 | Submit runner rata-rata |
|---:|---:|---:|---:|---:|
| 4 | 13.838 / 23.878 | 2.981 | 22.158 / 40.105 | 6.963 |
| 8 | 9.454 / 15.572 | 3.295 | 16.818 / 28.593 | 8.382 |
| 12 | 13.850 / 20.246 | 5.595 | 24.025 / 35.800 | 15.721 |
| 16 | 13.621 / 18.265 | 5.566 | 21.132 / 29.862 | 14.953 |

## Antrean, admission, dan kapasitas yang teramati

| Slot | Run outbox / antre worker | Submit outbox / antre worker | Run / Submit lock admission rata-rata | Puncak running |
|---:|---:|---:|---:|---:|
| 4 | 3.126 / 4.197 | 2.511 / 9.989 | 1.338 / 0.722 | 4 |
| 8 | 1.765 / 0.911 | 2.213 / 3.635 | 1.165 / 0.714 | 8 |
| 12 | 1.946 / 0.656 | 2.656 / 2.176 | 2.203 / 0.918 | 12 |
| 16 | 1.063 / 0.370 | 2.059 / 0.657 | 2.322 / 0.919 | 16 |

| Slot | Run awal diterima / 429 | Submit awal diterima / 429 | Durasi fase Run / Submit | Retry eksekusi |
|---:|---:|---:|---:|---:|
| 4 | 24 / 6 | 20 / 10 | 30.229 / 61.761 | 0 |
| 8 | 23 / 7 | 20 / 10 | 20.863 / 43.896 | 0 |
| 12 | 25 / 5 | 20 / 10 | 25.625 / 54.365 | 0 |
| 16 | 25 / 5 | 20 / 10 | 23.642 / 45.298 | 0 |

## Sumber daya dan variasi kontrol

CPU adalah penggunaan VM Docker keseluruhan, bukan satu sandbox. Kontrol Submit C++17 tanpa profiler adalah RPC tunggal pada konfigurasi normal, sebelum kapasitas kandidat diaktifkan; perubahan kontrol tersebut menunjukkan variasi host yang tidak boleh seluruhnya dikaitkan dengan jumlah slot.

| Slot | CPU Run rata-rata / maksimum | CPU Submit rata-rata / maksimum | RAM available minimum Submit | Kontrol Submit C++17 tanpa profiler |
|---:|---:|---:|---:|---:|
| 4 | 48.0% / 64.2% | 48.4% / 62.5% | 13.04 GiB | 3.841 dtk |
| 8 | 57.3% / 81.2% | 60.1% / 78.3% | 12.83 GiB | 3.759 dtk |
| 12 | 62.9% / 89.5% | 67.6% / 89.4% | 12.47 GiB | 3.995 dtk |
| 16 | 64.2% / 96.6% | 68.0% / 92.6% | 12.24 GiB | 4.629 dtk |

## Kandidat konfigurasi

Di antara konfigurasi baru yang diuji, **8 slot / 8 proses worker** memiliki jumlah P95 Run dan Submit sejak percobaan pertama paling rendah (64.676 detik). Kriteria ini memberi bobot sama pada kedua aksi. Ini kandidat untuk pengujian lanjutan, bukan bukti optimum produksi.

Jumlah slot lebih sedikit dapat mempercepat pekerjaan yang sedang berjalan sambil menambah antrean. Baca kedua tabel waktu bersama; jumlah worker rendah juga dapat menunda dispatcher yang berbagi antrean. Kandidat belum diterapkan sebagai konfigurasi normal.

## Kebenaran hasil dan keterbatasan

Seluruh 256 pekerjaan API pada konfigurasi baru tervalidasi dengan verdict yang diharapkan; setiap konfigurasi lengkap 64/64 trace dan seluruh peserta mencapai progres/nilai 100. Kelas fixture dihapus, masing-masing 30 akun dinonaktifkan. Delivery Celery bisa lebih banyak daripada eksekusi jika pesan duplikat dijadwalkan; lihat data setiap konfigurasi.

Setiap kapasitas memakai satu cohort lengkap untuk peringkat. Delapan slot memiliki satu percobaan pertama yang tidak lengkap, kemudian diulang dengan data fixture baru. Belum mengendalikan efek urutan, variasi host, cache, atau beban berkelanjutan. Rekomendasi yang berdekatan perlu diuji ulang dalam urutan berbeda. Data memakai profiler; kontrol pengaruh profiler dan sumber daya VM tersedia pada laporan setiap konfigurasi.

### Interpretasi hasil

- Empat slot membuat pekerjaan aktif lebih singkat: runner rata-rata 2,981 detik untuk Run dan 6,963 detik untuk Submit. Namun rata-rata outbox + antre worker Submit mencapai 12,499 detik, dan maksimum outbox 30,465 detik. Dispatcher masih berbagi worker dengan eksekusi, sehingga kapasitas rendah menimbulkan kembali penundaan pengiriman. Durasi seluruh fase Submit menjadi 61,761 detik.
- Delapan slot memberi keseimbangan terbaik pada cohort lengkap: runner Submit rata-rata 8,382 detik dan durasi fase 43,896 detik. P95 pertama → hasil 20,818/43,858 detik juga paling rendah di antara empat kandidat.
- Pada 12 dan 16 slot, antre worker rata-rata berkurang, tetapi runner Submit menjadi sekitar 15–16 detik. Pekerjaan yang lebih lambat mengimbangi manfaat paralelisme tambahan. CPU VM juga lebih tinggi, tetapi variasi kontrol tunggal menunjukkan bahwa tidak seluruh perbedaan dapat dianggap disebabkan jumlah slot saja.
- Terdapat satu kegagalan transport pada percobaan 8 slot pertama: `ReadError` setelah 45,163 ms ketika mengirim Submit. Percobaan itu selesai dengan 63/64 pekerjaan yang diterima/ditelusuri: 32 Executed dan 31 Accepted. Tiga flag harness merupakan transport error, admission failure, serta progres yang belum selesai dari peserta yang sama; bukan tiga eksekusi salah nilai. Pengulangan 8 slot lengkap tanpa anomali. Penyebab transport belum dipastikan dan perlu ditindaklanjuti sebagai masalah stabilitas.

Secara keseluruhan ada lima percobaan dengan 320 pekerjaan yang direncanakan: 319 selesai dengan hasil yang diharapkan dan satu permintaan tidak memperoleh penerimaan. Peringkat hanya memakai 256 pekerjaan dari empat cohort lengkap. [Laporan khusus percobaan gagal](../slot-sweep-20261104-122722-9e1850-slots-8/LAPORAN_GAGAL.md) dan seluruh data mentah tetap disimpan. Tidak ditemukan retry eksekusi atau salah penilaian pada pekerjaan yang selesai.

## Laporan per konfigurasi dan pengulangan

- [4 slot / worker](../slot-sweep-20261104-122722-9e1850-slots-4/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `perf_f38cf8679d`, delivery worker 64, cleanup `{'class_deleted': True, 'test_accounts_disabled': 30}`.
- [8 slot / worker](../slot-sweep-20261104-122722-9e1850-slots-8-retry-0ca325/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `perf_17edfe4605`, delivery worker 64, cleanup `{'class_deleted': True, 'test_accounts_disabled': 30}`.
- [12 slot / worker](../slot-sweep-20261104-122722-9e1850-slots-12/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `perf_40391ddce1`, delivery worker 64, cleanup `{'class_deleted': True, 'test_accounts_disabled': 30}`.
- [16 slot / worker](../slot-sweep-20261104-122722-9e1850-slots-16/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `perf_845f516d79`, delivery worker 64, cleanup `{'class_deleted': True, 'test_accounts_disabled': 30}`.

## Percobaan yang tidak masuk peringkat

Percobaan tidak lengkap/gagal tetap disimpan dan harus dibaca sebagai temuan stabilitas. Peringkat hanya memakai cohort lengkap yang lolos validasi, sehingga tidak mewakili tingkat keberhasilan seluruh percobaan.

- [8 slot, status failed](../slot-sweep-20261104-122722-9e1850-slots-8/results.json): [{"type": "transport_error", "label": "submit_30_admission_wave_1", "user": 25, "method": "POST", "start_s": 61.959701, "status": 0, "latency_ms": 45.163, "detail": "ReadError"}, {"type": "admission_failure", "phase": "submit_30", "user": 25, "status": 0}, {"type": "progress_mismatch", "user": 25, "progress": 50, "score": 0.0}]

Pembanding 50 slot terdahulu dengan API admission yang sama: [laporan](../judging-profile-20261104-115413-6490f7/LAPORAN_DETAIL_RUN_SUBMIT.md). Run pertama → hasil rata-rata 15,354 detik/P95 21,887 detik; Submit 30,541 detik/P95 44,194 detik. Pengukuran 50 slot itu dilakukan pada waktu berbeda dan bukan bagian urutan sweep ini.

```powershell
./scripts/test-slot-sweep.ps1
# Satu konfigurasi saja:
./scripts/test-judging-profile.ps1 -Slots 8
```

[Data perbandingan](comparison.json) dan [manifest urutan/status](manifest.json). Laporan per konfigurasi berisi timeline terburuk dan waktu antar-container; laporan lama tidak ditimpa.

[Verifikasi pemulihan dan cleanup](verification.json) serta [hash source](source-hashes.json) mencatat konfigurasi akhir, fixture, dan pemeriksaan artefak. Kontrol tanpa profiler bersifat sekuensial, sehingga tidak membuktikan kapasitas konkuren tanpa pengaruh instrumentasi.
