# Kebutuhan server untuk 11–12 pengguna serentak

Diperbarui 10 November 2026, setelah milestone M5 (satu start container per pekerjaan, kolam sandbox siap pakai, precompiled header C++, API 4 proses). Laporan sebelumnya untuk 10 dan 20 pengguna memakai angka sebelum M5 dan sudah tidak berlaku; isinya ada di riwayat git.

## Ringkasan

Target: hasil Run dan Submit tampil paling lama 5 detik, termasuk saat semua pengguna menekan tombol pada detik yang sama.

**Target ini sudah tercapai di laptop pengembangan** (6 core fisik / 12 thread, 16 GB), diukur lewat stack lengkap:

| Skenario | Run C | Submit C (5 kasus) | Submit C++ (5 kasus) |
|---|---:|---:|---:|
| 1 pengguna | 0,48 s | 0,47 s | 0,88 s |
| 12 pengguna menekan serentak, median | 1,25 s | 1,29 s | 1,77 s |
| 12 pengguna menekan serentak, terlama | 2,0 s | 2,0 s | 3,0 s |

Untuk deployment 11–12 pengguna:

| Pilihan | CPU | RAM | Disk | Perkiraan waktu terlama saat 12 orang serentak |
|---|---|---:|---|---|
| Minimum | 6 core fisik (12 vCPU) | 8 GB | 40 GB SSD | ±2 s (C), ±3 s (C++), sama dengan laptop |
| **Disarankan** | **8 core fisik (16 vCPU)** | **16 GB** | 40 GB SSD NVMe | ±1,5 s (C), ±2,5 s (C++) |
| Lebih longgar | 12 core fisik (24 vCPU) | 16 GB | 40 GB SSD NVMe | ±1,2 s (C), ±1,9 s (C++) |

"Core fisik" setara satu core i7-9750H. Di cloud, 1 vCPU biasanya satu hyperthread, jadi jumlah vCPU = 2 × core fisik. Di atas 12 core hampir tidak ada manfaat lagi untuk 12 pengguna: batas bawahnya adalah waktu satu pengguna (±0,5 s untuk C, ±0,9 s untuk C++).

Baris "Disarankan" dipilih karena memberi ruang untuk soal yang programnya lebih berat daripada soal uji, dan untuk Linux native yang belum diukur.

## Pengaturan yang mengikuti ukuran server

Semua ada di [compose.yaml](compose.yaml):

| Pengaturan | Aturan | 6 core | 8 core | 12 core |
|---|---|---:|---:|---:|
| Worker `--concurrency` | = core fisik, paling banyak jumlah pengguna serentak | 6 | 8 | 12 |
| `RUNNER_SLOTS` | worker + 1 (untuk validator) | 7 | 9 | 13 |
| `RUNNER_WARM` | pengguna serentak + 1, tidak bergantung pada core (lihat bagian berikut) | 13 | 13 | 13 |
| API `--workers` | 4 cukup untuk 12 pengguna | 4 | 4 | 4 |

Jumlah slot tidak boleh melebihi core fisik: saat core dipakai bersama lewat hyperthread, waktu CPU program yang sama naik hingga ±2,2 kali, dan margin validasi soal hanya 2 kali.

## Menyesuaikan jumlah kolam sandbox (`RUNNER_WARM`)

Runner menyiapkan sejumlah container sandbox lebih dulu. Container ini terlihat di `docker ps` dan Docker Desktop dengan nama `js-warm-<id>`, tetapi tidak muncul di `docker compose ps`, karena dibuat oleh runner lewat Docker API. Setiap Run atau Submit memakai satu container dari kolam **sekali saja**, lalu container itu dihapus dan runner membuat penggantinya. Tidak ada container yang dipakai oleh dua pekerjaan.

Jumlahnya **statis**: dibaca sekali saat runner start. Kalau jumlah pengguna serentak berubah, pengelola mengubahnya secara manual.

**Aturan:** `RUNNER_WARM` = jumlah terbesar pengguna yang mungkin menekan Run/Submit pada detik yang sama + 1. Kalau ragu, pilih angka yang lebih besar; kolam yang terlalu besar hampir tidak ada biayanya, sedangkan kolam yang terlalu kecil membuat pengguna terakhir menunggu container dibuat.

**Langkah:**

1. Ubah nilai di [compose.yaml](compose.yaml), bagian layanan `runner`:
   ```yaml
   RUNNER_WARM: '21'
   ```
2. Terapkan, cukup runner saja; layanan lain tidak terganggu:
   ```bash
   docker compose up -d runner
   ```
   Pekerjaan yang sedang berjalan di runner lama akan gagal sebagai kesalahan infrastruktur dan dicoba ulang otomatis. Sebaiknya lakukan di luar jam kelas.
3. Periksa setelah ±30 detik. Jumlahnya harus sama dengan `RUNNER_WARM` saat tidak ada pekerjaan berjalan:
   ```bash
   docker ps -q --filter label=judgementsystem.sandbox=1 | wc -l
   ```
   Di PowerShell: `(docker ps -q --filter label=judgementsystem.sandbox=1).Count`

**Biaya:** setiap container yang menunggu memakai sekitar 7 MB RAM dan hampir nol CPU. Batas 512 MB per container hanya berlaku saat mengompilasi, bukan memori yang dipesan. Contoh: kolam 30 ≈ 210 MB RAM.

| `RUNNER_WARM` | RAM saat menunggu | Waktu mengisi penuh setelah restart | Cukup untuk pengguna serentak |
|---:|---:|---:|---:|
| 13 | ±90 MB | ±10 s | 12 |
| 21 | ±150 MB | ±15 s | 20 |
| 30 | ±210 MB | ±20 s | 29 |

**Hasil ukur 20 pengguna serentak** (laptop 6 core, 6 worker, 3 putaran × 2 ulangan, 11 November 2026), waktu terlama sampai hasil tampil:

| | Kolam 13 | Kolam 21 |
|---|---:|---:|
| Run C | 5,4–6,1 s | 2,1–3,5 s |
| Submit C | 4,9–7,0 s | 2,6–2,8 s |
| Submit C++ | 4,7–6,0 s | 4,2–4,5 s |

Median hampir sama di kedua konfigurasi (±1,4–2,5 s); yang berubah adalah pengguna terakhir.

**Yang tidak bisa diselesaikan oleh kolam:**
- **Antrean karena CPU.** Kolam menghapus waktu menyiapkan container, bukan waktu mengompilasi dan menjalankan program. Dengan worker tetap, waktu terlama naik kira-kira 0,2 detik per pengguna tambahan untuk C++. Di laptop 6 core, Submit C++ diperkirakan melewati 5 detik sekitar 23–25 pengguna serentak (belum diukur). Untuk mengatasinya, tambah core fisik lalu naikkan worker `--concurrency` dan `RUNNER_SLOTS` sesuai tabel di atas.
- **Lock admission di API.** Mulai sekitar 20 pengguna serentak, permintaan paling lambat baru diterima server setelah 1,7–2,7 detik, karena setiap pengiriman menghitung kuota secara bergiliran. Ini perlu perubahan kode bila targetnya jauh di atas 20.
- **Burst berturut-turut.** Setelah burst besar, kolam diisi ulang satu per satu, sekitar 1,5 container per detik. Burst kedua yang datang kurang dari ±15 detik kemudian sebagian akan memakai container baru.

## Data pengukuran

Mesin: Intel i7-9750H (6 core / 12 thread), Docker Desktop dengan 12 vCPU dan 15,5 GB, konfigurasi 6 worker / 7 slot / 13 sandbox siap pakai / 4 proses API. Soal uji: penjumlahan dua bilangan, 5 kasus uji.

**Lewat stack lengkap** ([scripts/profiling/concurrent_users.py](scripts/profiling/concurrent_users.py); waktu dari tombol ditekan sampai hasil terbaca dengan polling 0,4 detik; 12 pengguna × 3 putaran) adalah tabel di Ringkasan. Burst pertama setelah stack dinyalakan lebih lambat (terlama 4,0 s) karena proses API dan worker masih dingin.

**Runner saja** ([scripts/profiling/capacity.py](scripts/profiling/capacity.py); CPU dari `/proc/stat` VM Docker, sudah termasuk Docker Engine dan pengisian kolam):

| Pengukuran | C | C++ (`<iostream>`) |
|---|---:|---:|
| 1 Submit, sandbox siap pakai | 0,25–0,40 s | 0,63–1,0 s |
| 12 Submit serentak (6 paralel): selesai semua dalam | 1,3 s | 2,6 s |
| Biaya di jalur kritis saat burst | 0,66 detik-CPU | 1,37 detik-CPU |
| Biaya total per Submit saat beban terus-menerus (kolam habis) | 1,70 detik-CPU | 2,24 detik-CPU |
| Throughput terus-menerus | 3,5 Submit/detik | 2,5 Submit/detik |

Sebelum M5, satu Submit C memakai ±10,5 detik-CPU dan ±4,2 detik di runner.

**Kompilasi C++ di sandbox** (1 CPU): `<iostream>` 1,6 → 0,4 s dan `<bits/stdc++.h>` 5,6–9,6 → 1,5–1,9 s berkat precompiled header. Header lain sebagai include pertama (misalnya `<vector>`) tetap ±1,3–1,7 s.

**Memori** (`docker stats`, stack menganggur setelah pengujian):

| Komponen | Pemakaian |
|---|---:|
| API (4 proses) | ±545 MB |
| MariaDB | ±110 MB |
| Worker (6 proses) / validator / scheduler / runner / Redis | ±280 / 100 / 65 / 60 / 4 MB |
| 13 sandbox siap pakai | 13 × 7 MB |
| Sandbox yang sedang mengompilasi | puncak ±200 MB, plafon 512 MB |
| Image (aplikasi 217 MB + sandbox 505 MB + MariaDB + Redis) | ±1,1 GB di disk |

## Model untuk menghitung server lain

Dua rumus ini cocok dengan pengukuran di atas:

```text
waktu terlama saat N orang menekan serentak ≈ 0,5 s + N × biaya_jalur_kritis / core_fisik
kapasitas terus-menerus (pekerjaan/detik)   ≈ core_fisik / biaya_total
```

Pemeriksaan di laptop (6 core, N = 12): C diprediksi 0,5 + 12 × 0,66 / 6 = 1,8 s, terukur 2,0 s. C++ diprediksi 0,5 + 12 × 1,37 / 6 = 3,2 s, terukur 3,0 s. Kapasitas C diprediksi 6 / 1,70 = 3,5 per detik, terukur 3,54.

**Penggunaan untuk 12 pengguna:**

- *Semua menekan serentak*, C++: 6 core → 3,2 s; 8 core → 2,6 s; 12 core → 1,9 s.
- *Lab biasa*: bila tiap siswa menekan Run atau Submit setiap 10 detik (sangat aktif), bebannya 1,2 pekerjaan per detik. Itu sepertiga kapasitas laptop untuk C dan separuhnya untuk C++, dan hampir semua pekerjaan mendapat sandbox siap pakai (kolam diisi ulang satu per satu; membuat satu sandbox butuh ±0,6 detik, jadi perkiraannya ±1,5 per detik).

**RAM:** layanan ±1,2 GB + worker 46 MB × jumlah worker + sandbox 512 MB × slot (plafon, bukan pemakaian umum) + OS dan Docker ±1,5 GB. Hasilnya 7 slot → 6,6 GB, 9 slot → 7,7 GB, 13 slot → 9,9 GB; dibulatkan ke 8 GB dan 16 GB.

**Disk:** image ±1,1 GB. Setiap kiriman menyimpan source (≤ 32 KB) dan hasilnya; 12 siswa × 300 aksi per hari menambah kurang dari 20 MB per hari. SSD diperlukan karena setiap pekerjaan membuat container baru.

## Batasan

- **Soal uji adalah soal paling ringan.** Program siswa di sini berjalan dalam milidetik. Soal yang programnya memakai t detik CPU per kasus menambah t × jumlah kasus ke biaya tiap Submit. Contoh: 0,5 detik × 5 kasus = 2,5 detik-CPU; 12 Submit serentak pada 8 core menambah ±3,8 detik. Untuk soal seperti itu, 5 detik saat semua menekan serentak tidak selalu tercapai, berapa pun cepatnya sistem ini.
- **Semua angka berasal dari satu laptop dengan Docker Desktop.** Linux native tidak memakai lapisan VM dan kemungkinan lebih cepat, tetapi belum diukur. Angka untuk 8 dan 12 core adalah hasil model, bukan pengukuran.
- **Dalam uji serentak, 12 pengguna mengirim kode yang sama.** Tidak ada cache kompilasi, jadi ini tidak menguntungkan hasil, tetapi kode siswa yang lebih panjang akan dikompilasi lebih lama.
- **Kuota admission tidak menghambat 12 pengguna:** 10 pekerjaan tertunda per akun, 20 per kelas, 50 global.
- Uji beban 30 pengguna belum diulang setelah M5.

## Mengukur ulang di server tujuan

```bash
docker compose --profile tools build && docker compose up -d

# Lewat stack lengkap: 12 pengguna, 3 putaran (kredensial admin lewat stdin, lihat scripts/test-integration.ps1)
echo '{"username":"<admin>","password":"<password>"}' | docker compose exec -T api python scripts/profiling/concurrent_users.py 12 3

# Runner saja: biaya CPU per pekerjaan. Nilai paralel tidak boleh melebihi RUNNER_SLOTS.
docker compose run --rm --no-deps -v ./scripts/profiling/capacity.py:/tmp/capacity.py:ro api python /tmp/capacity.py judge 60 6 c17
docker compose run --rm --no-deps -v ./scripts/profiling/capacity.py:/tmp/capacity.py:ro api python /tmp/capacity.py judge 60 6 cpp17
```

`concurrent_users.py` membuat akun pengajar uji lalu menonaktifkannya, dan menulis kiriman uji pada soal `sum-v1`. `capacity.py` tidak menulis ke database. Masukkan `cpu_seconds_per_job` hasil ukur ke rumus di atas.
