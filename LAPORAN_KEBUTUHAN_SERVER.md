# Kebutuhan server untuk 10 dan 20 pengguna serentak

Perhitungan ini dibuat pada 10 November 2026. Angka dasarnya diukur langsung pada kode setelah perbaikan M1: batas waktu CPU, 6 worker / 7 slot, dan image `gcc12-v3`. Pengukuran dilakukan di laptop pengembangan.

## Ringkasan

"Waktu wajar" di sini artinya hasil **Run tampil ≤ 5 detik** dan hasil **Submit tampil ≤ 10 detik** sejak tombol ditekan, termasuk antrean dan polling. Kalau semua pengguna menekan tombol pada detik yang sama, waktu ini menjadi waktu tunggu terlama, yaitu yang dialami pengguna terakhir.

| Skenario | Core fisik | RAM | Worker / slot runner | Disk |
|---|---:|---:|---:|---:|
| **10 pengguna**, lab biasa (aksi tersebar) | 6 | 8 GB | 6 / 7 | 40 GB SSD |
| **10 pengguna**, semua menekan bersamaan | 14 | 12 GB | 10 / 11 | 40 GB SSD |
| **20 pengguna**, lab biasa (aksi tersebar) | 10 | 12 GB | 10 / 11 | 40 GB SSD |
| **20 pengguna**, semua menekan bersamaan | 28 | 16 GB | 20 / 21 | 40 GB SSD |

- **Satuan core:** "core fisik" setara dengan satu core i7-9750H yang menjalankan Docker Desktop. Di cloud, 1 vCPU biasanya sama dengan 1 hyperthread, jadi **kalikan dua untuk mendapatkan jumlah vCPU**. Contoh: 10 core fisik ≈ 20 vCPU.
- **Spesifikasi laptop pengembangan saat ini** (6 core fisik, 16 GB) sudah memenuhi baris pertama.
- **Pilihan skenario:** skenario "lab biasa" cukup bila siswa bekerja dengan ritme masing-masing. Skenario "menekan bersamaan" diperlukan bila ada momen seperti "semua kirim sekarang" di akhir sesi atau saat ujian.

## Data pengukuran

Diukur dengan [scripts/profiling/capacity.py](scripts/profiling/capacity.py), langsung ke runner, memakai soal penjumlahan C. Pada Submit ada 1 kompilasi dan 5 kasus uji. CPU dihitung dari `/proc/stat` VM Docker, sehingga seluruh overhead (Docker Engine, runner, dan sandbox) ikut terhitung.

**Mesin uji:** Intel i7-9750H (6 core / 12 thread), Docker Desktop dengan 12 vCPU dan 15,5 GB RAM, laptop tersambung ke listrik.

| Pekerjaan | Waktu runner saat sendirian | CPU per pekerjaan | Throughput maksimum host ini |
|---|---:|---:|---:|
| Run (kompilasi + 1 input) | 1,4–1,6 s | **3,8 detik-CPU** | ±1,7 per detik |
| Submit (kompilasi + 5 kasus) | 4,2–4,7 s | **10,5 detik-CPU** | ±0,65 per detik |

| Submit serentak | Waktu runner median / maks | vCPU sibuk |
|---:|---:|---:|
| 1 | 4,2 / 4,5 s | 1,9 dari 12 |
| 2 | 4,7 / 5,3 s | — |
| 4 | 7,6 / 8,4 s | — |
| 6 | 9,2 / 11,2 s | 6,7 dari 12 |
| 8 | 11,6 / 12,5 s | — |

Throughput berhenti naik di sekitar 6 job paralel, yaitu jumlah core fisik. Hyperthread hampir tidak menambah kapasitas.

**Memori**, diukur dengan `docker stats` dan `memory.peak` cgroup:

| Komponen | Pemakaian |
|---|---:|
| MariaDB (idle) | 120 MB |
| API | 70 MB |
| Worker | ±46 MB per proses |
| Validator / scheduler / runner / Redis | 90 / 65 / 50 / 10 MB |
| Kompilasi C++ dengan `<bits/stdc++.h>` | puncak 203 MB (batas sandbox 512 MB) |
| Image (aplikasi + sandbox + MariaDB + Redis) | ±1 GB |
| Data MariaDB saat ini | 190 MB |

## Cara menghitung

Biaya CPU per pekerjaan hampir tetap. Karena itu, kalau N pekerjaan datang bersamaan, pengguna terakhir menunggu kira-kira:

```text
waktu terlama ≈ overhead tetap + N × biaya_CPU / jumlah_core
overhead tetap ≈ 2 s (tick scheduler ≤ 1 s, polling browser 1,2 s, API dan DB)
```

**Pemeriksaan model:** di laptop ini (6 core), 24 Submit diprediksi selesai dalam 24 × 10,5 / 6 = 42 s, dan hasil ukurnya 37,7–38,8 s. 24 Run diprediksi 16 s, hasil ukurnya 14,7 s. Model ini sedikit konservatif.

**Semua menekan bersamaan:** jumlah core ≥ N × biaya / (target − 2 s).

| N | Run (target 5 s) | Submit (target 10 s) | Dipakai |
|---:|---:|---:|---:|
| 10 | 10 × 3,8 / 3 = 12,7 | 10 × 10,5 / 8 = 13,1 | **14 core** |
| 20 | 20 × 3,8 / 3 = 25,3 | 20 × 10,5 / 8 = 26,3 | **28 core** |

**Lab biasa:** asumsi beban berat untuk setiap siswa adalah 1 Run per 30 detik dan 1 Submit per 2 menit. Kebutuhan rata-rata per siswa = 3,8/30 + 10,5/120 ≈ **0,22 core**. Utilisasi dijaga ≤ 50% agar antrean akibat kebetulan tetap pendek:

| N | Rata-rata | ×2 ruang aman | Dipakai |
|---:|---:|---:|---:|
| 10 | 2,2 core | 4,4 | **6 core** |
| 20 | 4,4 core | 8,8 | **10 core** |

**Worker dan slot:** jumlah worker = min(N, core fisik), dan `RUNNER_SLOTS` = worker + 1 (satu untuk validator). Jangan melebihi jumlah core fisik, karena hyperthread membuat program siswa melambat hingga ±1,8 kali dan bisa divonis TLE (lihat [MILESTONE_PERBAIKAN.md](MILESTONE_PERBAIKAN.md#m12-tle-palsu-saat-ramai)).

**RAM:** layanan ±0,6 GB + worker 46 MB × worker + sandbox 0,5 GB × slot + OS dan Docker ±1,5 GB. Sandbox dihitung memakai batasnya (512 MB), bukan pemakaian umumnya (≤ 203 MB), supaya host tidak pernah kehabisan memori. Hasilnya: 7 slot → 5,9 GB, 11 slot → 8,1 GB, 21 slot → 13,5 GB. Angka ini dibulatkan ke ukuran RAM standar.

**Disk:** image ±1 GB. Setiap Submit menyimpan source (≤ 32 KB) dan hasilnya. 20 siswa × 300 aksi per hari menambah sekitar 30 MB per hari, atau ±1 GB per semester. Disk 40 GB SSD sudah cukup longgar untuk log dan backup lokal. Pakai SSD karena setiap fase menjalankan ulang container.

## Yang terjadi di laptop ini bila semua menekan bersamaan

| N | Run terakhir tampil | Submit terakhir tampil |
|---:|---:|---:|
| 10 | ±8,5 s | ±19,5 s |
| 20 | ±15 s | ±37 s |

Untuk 10 siswa, hasilnya masih bisa diterima: menunggu maksimal ±20 detik terjadi hanya pada momen serentak. Untuk 20 siswa, waktu tunggu Submit terlalu lama.

## Cara terhemat: kurangi biaya per Submit, bukan tambah server

Dari 10,5 detik-CPU per Submit, kompilasinya hanya ±0,7 detik-CPU, dan program penjumlahan berjalan dalam hitungan milidetik. Sisanya, sekitar 1,5 detik-CPU per fase × 6 fase, habis untuk memulai ulang container dan bootstrap Python pada setiap kasus uji.

Bila semua kasus uji dijalankan dalam **satu kali start** (bootstrap menjalankan program per kasus sebagai proses anak), biaya Submit diperkirakan turun ke ±4 detik-CPU, kira-kira sama dengan Run. Kebutuhan core skenario serentak pun turun hampir 2,5 kali: 20 pengguna cukup dengan ±12 core, bukan 28. Isolasi antar-kasus tetap bisa dijaga, karena setiap kasus tetap memakai proses dan direktori kerja baru. Namun ini mengubah protokol sandbox dan perlu dirancang serta diuji tersendiri. Perkiraan ini belum diukur.

## Batasan dan risiko

- **Angka ini berasal dari satu laptop dengan Docker Desktop.** Linux native di server tidak memakai lapisan VM, sehingga kemungkinan lebih hemat. CPU server juga bisa lebih cepat atau lebih lambat per core. **Ukur ulang di server tujuan** dengan perintah di bawah, lalu masukkan biaya CPU hasil ukur ke rumus di atas.
- **Soal yang diukur hanyalah soal paling ringan** (program berjalan dalam milidetik). Soal yang programnya memakai 1 detik CPU per kasus menambah ±5 detik-CPU per Submit (5 kasus).
- **Kemungkinan TLE palsu dari batas CPU baru (M1):** pada tiga pengukuran pertama, saat laptop **memakai baterai**, sekitar 20% Submit penjumlahan mendapat TLE palsu pada kasus pertama setelah kompilasi, dan hanya terjadi dengan image `gcc12-v3`. Masalah ini tidak terulang pada 128 job berikutnya setelah laptop tersambung ke listrik. Penyebabnya belum dipastikan. Jalankan server dengan daya AC dan profil performa tinggi, dan lihat catatan di [MILESTONE_PERBAIKAN.md](MILESTONE_PERBAIKAN.md).
- **Kuota admission tidak menghambat 20 pengguna:** 20 pending per kelas dan 50 global. Untuk lebih dari 20 siswa dalam satu kelas, kuota kelas akan menolak dengan 429.

## Mengukur ulang di server tujuan

```bash
docker compose up -d --no-deps runner
docker compose run --rm --no-deps -v ./scripts/profiling/capacity.py:/tmp/capacity.py:ro api python /tmp/capacity.py judge 24 6
docker compose run --rm --no-deps -v ./scripts/profiling/capacity.py:/tmp/capacity.py:ro api python /tmp/capacity.py run 24 6
docker compose down
```

Isi `RUNNER_SLOTS` minimal sama dengan nilai paralel yang diuji. Skrip tidak menulis ke database.
