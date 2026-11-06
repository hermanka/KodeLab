# Konfirmasi 8 versus 12 slot — 4 November 2026

**8 slot belum terbukti selalu lebih cepat.** Pada putaran pertama 8 unggul; setelah urutan dibalik menjadi 12 lalu 8, konfigurasi 12 unggul. Gabungan dua putaran masih mendukung 8 sebagai kandidat awal dengan penggunaan CPU lebih rendah, tetapi hasil tidak cukup untuk menyatakan satu kapasitas sebagai optimum tetap. Konfigurasi normal 50 proses worker / 50 slot telah dipulihkan; tidak ada perubahan kapasitas permanen.

## Skenario dan batas pengukuran

Setiap kapasitas diuji dengan 30 pengguna berbeda pada satu kelas dan learning path baru, 15 C17 dan 15 C++17, soal penjumlahan yang sama dengan 5 test case. Ada 30 Run serentak, dilanjutkan 30 Submit serentak, serta 4 pekerjaan pembanding lewat API. Jumlah proses worker dan slot runner diubah bersama. Scheduler 1 detik dan batas pekerjaan pending kelas 20 tetap sama. Image kelima layanan identik pada keempat pengujian lengkap yang dibandingkan.

Putaran terdahulu berurutan 4 → 8 (percobaan pertama mengalami satu ReadError, lalu diulang) → 12 → 16. Putaran konfirmasi ini berurutan **12 → 8**. Urutan bukan eksperimen acak penuh; variasi host, cache, dan pengaruh profiler belum dihilangkan. Percobaan awal yang mengalami ReadError tetap tersedia pada laporan lama, dan tidak dimasukkan ke statistik pengujian lengkap.

Waktu berikut dihitung sejak permintaan pertama sampai hasil teramati oleh alat uji. Termasuk HTTP 429 dan jeda pengiriman ulang terkontrol setelah gelombang sebelumnya selesai. Pengiriman ulang tersebut adalah perilaku alat uji, bukan otomatisasi UI. Poll hasil setiap 1 detik; waktu render browser tidak diukur. P95 berarti 95% pekerjaan teramati selesai dalam waktu tersebut.

## Hasil dua putaran

Semua angka detik; setiap baris memuat 30 Run dan 30 Submit.

| Putaran | Slot / proses worker | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 |
|---|---:|---:|---:|---:|---:|
| Pertama | 8 | 13,093 | 20,818 | 26,360 | 43,858 |
| Pertama | 12 | 17,261 | 25,574 | 35,981 | 54,257 |
| Konfirmasi, diuji pertama | 12 | 15,259 | 22,937 | 26,929 | 42,178 |
| Konfirmasi, diuji kedua | 8 | 16,219 | 24,534 | 27,989 | 46,195 |

Dengan kriteria jumlah P95 Run dan Submit yang sama seperti sebelumnya, putaran pertama memenangkan 8; putaran konfirmasi memenangkan 12 (65,115 detik versus 70,729 detik). Kemenangan berbalik, sehingga klaim bahwa 8 selalu paling cepat tidak didukung data.

Statistik gabungan dihitung ulang dari 60 pekerjaan per aksi per kapasitas, bukan merata-ratakan P95 kedua putaran:

| Slot / proses worker | Run rata-rata gabungan | Run P95 gabungan | Submit rata-rata gabungan | Submit P95 gabungan |
|---:|---:|---:|---:|---:|
| 8 | 14,656 | 23,558 | 27,174 | 43,858 |
| 12 | 16,260 | 25,275 | 31,455 | 53,905 |

Statistik gabungan bersifat deskriptif, tanpa pengujian signifikansi. Dua putaran lengkap per kapasitas belum cukup untuk menjamin kinerja pada beban berkelanjutan atau kelas dengan soal lebih berat.

## Mengapa putaran konfirmasi memenangkan 12?

Pada 8 slot, pekerjaan di dalam runner lebih cepat, tetapi antrean lebih panjang. Angka berikut adalah rata-rata detik pada putaran konfirmasi:

| Slot | Runner Run / Submit | Antre worker Run / Submit | Menunggu publikasi outbox Run / Submit |
|---:|---:|---:|---:|
| 8 | 3,999 / 8,996 | 1,616 / 3,148 | 2,480 / 3,156 |
| 12 | 4,507 / 11,797 | 1,107 / 2,267 | 1,390 / 1,239 |

Pada putaran ini, tambahan kapasitas 12 mengurangi waktu antre yang cukup besar untuk mengimbangi runner yang lebih lambat. Dispatcher masih berbagi proses worker dengan eksekusi. Jumlah Submit yang langsung diterima juga sedikit berbeda: 21 pada 12 slot versus 20 pada 8 slot; sisanya HTTP 429 lalu dikirim ulang. Karena itu, hasil mengukur sistem dengan admission dan antreannya, bukan kecepatan runner saja.

CPU VM rata-rata pada 8 slot adalah 56,9% untuk Run dan 60,1% untuk Submit; pada 12 slot 61,4% dan 69,4%. Kontrol Submit C++17 tanpa profiler sebelum masing-masing konfigurasi aktif juga berbeda (3,715 versus 4,461 detik), menunjukkan variasi host yang harus diperhitungkan. Tidak semua perubahan waktu bisa diatribusikan ke slot.

## Kebenaran hasil, masalah alat analisis, dan pemulihan

- Seluruh **128/128 pekerjaan API** putaran konfirmasi selesai dengan verdict yang diharapkan, tanpa retry eksekusi. Semua 30 peserta per kapasitas mencapai progres dan nilai 100. Tidak ada anomali pada hasil alat uji pengguna.
- Analisis pertama 8 slot mendeteksi 7 durasi simpan negatif. Ini kesalahan penggabungan trace: `end_ns` span dihitung dari durasi monotonic, sedangkan event commit memakai jam dinding. Pada contoh yang diperiksa, event commit terakhir berada sekitar 11 ms di luar batas akhir sintetis, sehingga analyzer salah mengambil commit awal sebelum runner dipanggil. Ini bukan waktu simpan negatif yang terjadi di aplikasi.
- `analyze.py` sekarang menghubungkan catatan dengan induk span dan prosesnya, bukan menyaring timestamp di dalam batas span. Self-check mencakup event commit di luar batas waktu sintetis dan penolakan catatan milik span/proses lain. Tidak ada kode inti aplikasi yang diubah.
- Data mentah yang sama dianalisis ulang, tanpa mengulang beban pengguna. Kedua konfigurasi sekarang memiliki 64/64 pekerjaan tergabung, tanpa issue critical path. Analisis/laporan sebelum perbaikan disimpan dalam `before-reanalysis/`; manifest sebelumnya juga disimpan. Pemulihan status tercatat pada manifest baru.
- Verifikasi database: 60 akun fixture dinonaktifkan, kelas fixture tersisa 0, pekerjaan pending 0. Proses worker terverifikasi 50 untuk eksekusi dan 1 untuk validasi; runner kembali 50 slot, sandbox normal `gcc12-v2`, profiler API/runner nonaktif. Scheduler tetap 1 detik.
- Image layanan identik dengan putaran pertama. Tidak ditemukan pesan `Sandbox cleanup error`, `Judging failed`, atau `PROFILE_WRITE_FAILED` pada keempat log pengujian lengkap yang dibandingkan. Pemeriksaan artefak baru terhadap nilai rahasia yang dikonfigurasi lulus.

## Rekomendasi

**8 proses worker / 8 slot runner tetap masuk akal sebagai konfigurasi awal pada host ini**, berdasarkan waktu gabungan dan CPU yang lebih rendah. Namun, rekomendasi itu merupakan pilihan operasional awal yang harus dipantau, bukan kapasitas optimal yang sudah terbukti. 12 juga layak bila prioritasnya mengurangi antrean saat burst. Tidak ada kapasitas yang menjamin target 5–7 detik untuk 30 pengguna pada hasil ini.

Konfigurasi permanen belum diubah karena tugas ini adalah pengujian. Belum dilakukan uji beban berkelanjutan, lebih dari 30 pengguna, banyak kelas bersamaan, atau soal yang lebih berat.

## Data dan laporan

- [Tabel lengkap putaran konfirmasi](LAPORAN_PERBANDINGAN_SLOT.md), [data perbandingan](comparison.json), dan [verifikasi/statistik gabungan](verification.json).
- [12 slot: waktu setiap tahap, antar-container, dan timeline terburuk](../slot-sweep-20261104-142709-e053a4-slots-12/LAPORAN_DETAIL_RUN_SUBMIT.md).
- [8 slot: waktu setiap tahap, antar-container, dan timeline terburuk](../slot-sweep-20261104-142709-e053a4-slots-8/LAPORAN_DETAIL_RUN_SUBMIT.md).
- [Putaran pertama, tetap utuh](../slot-sweep-20261104-122722-9e1850/LAPORAN_PERBANDINGAN_SLOT.md).

Menjalankan kembali skenario urutan terbalik dengan PowerShell 7 dari root project:

```powershell
./scripts/test-slot-sweep.ps1 -Slots 12,8
```
