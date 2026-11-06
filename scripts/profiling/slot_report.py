"""Compare measured slot runs, including admission rejection/retry time and all queue stages."""
import json
from pathlib import Path
import statistics
import sys


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def collect(history, entries):
    rows = []
    for entry in entries:
        directory = history/entry["directory"]
        raw, analysis = read(directory/"results.json"), read(directory/"stage-analysis.json")
        runtime, runner = read(directory/"runtime-config.json"), read(directory/"runner-runtime.json")
        summary = raw["summary"]
        resources = directory/"resources.jsonl"
        samples = [json.loads(line) for line in resources.read_text().splitlines() if line.strip()] if resources.exists() else []
        assert entry["status"] == summary["status"] == "completed"
        assert not summary["anomalies"] and not analysis["issues"]
        assert analysis["jobs_joined"] == analysis["jobs_requested"] == 64
        assert runner["runner_slots"] == entry["slots"]
        assert any(w["concurrency"] == entry["slots"] and "celery" in w["queues"] for w in runtime["workers"])
        assert runtime["dispatch_interval_seconds"] == 1
        assert summary["cleanup"]["class_deleted"] and summary["cleanup"]["test_accounts_disabled"] == 30
        assert all(j["verdict"] == j["expected_verdict"] for j in raw["jobs"])
        assert all(p["progress"] == p["score"] == 100 for p in summary["progress_after_submit"])
        row = {"slots": entry["slots"], "directory": entry["directory"], "run_id": summary["run_id"],
               "api_image": read(directory/"environment.json")["original_images"]["api"],
               "runner_image": read(directory/"environment.json")["original_images"]["runner"],
               "queue_peaks": summary["queue_peaks"], "deliveries": analysis["worker_deliveries"],
               "cleanup": summary["cleanup"], "phases": {}}
        for phase in ("run_30", "submit_30"):
            metrics = analysis["groups"][phase]["metrics_ms"]
            assert analysis["groups"][phase]["n"] == 30
            detail = next(p for p in summary["phases"] if p["name"] == phase)
            row["phases"][phase] = {"first_try": metrics["first_try_to_client_ms"],
                "accepted_request": metrics["request_to_client_ms"], "runner": metrics["runner_total_ms"],
                "outbox": metrics["outbox_wait_ms"], "worker_wait": metrics["broker_worker_wait_ms"],
                "api_lock": metrics["api_lock_ms"], "initial_http": detail["initial_http"],
                "duration_seconds": detail["duration_seconds"], "retries": detail["retries"]}
            start = summary["clock_origin_ns"]+detail["start_s"]*1e9
            end = start+detail["duration_seconds"]*1e9
            selected = [s for s in samples if start <= s["at_ns"] <= end and s["vm_cpu_percent"] is not None]
            if selected:
                row["phases"][phase]["vm_cpu_mean"] = statistics.mean(s["vm_cpu_percent"] for s in selected)
                row["phases"][phase]["vm_cpu_max"] = max(s["vm_cpu_percent"] for s in selected)
                row["phases"][phase]["vm_memory_available_min_gib"] = min(s["vm_memory_available_bytes"] for s in selected)/1024**3
        row["unprofiled_cpp_submit_ms"] = analysis["calibration_ms"]["unprofiled"]["cpp17_judge"]["mean"]
        row["equal_weight_p95_seconds"] = sum(row["phases"][phase]["first_try"]["p95"]/1000
                                                for phase in ("run_30", "submit_30"))
        rows.append(row)
    assert rows and len({r["slots"] for r in rows}) == len(rows)
    assert len({(r["api_image"], r["runner_image"]) for r in rows}) == 1, "Code images differ between new candidates"
    return rows


def write_report(directory, history=None):
    history = history or directory.parent
    attempts = read(directory/"manifest.json")["runs"]
    entries = [entry for entry in attempts if entry["status"] == "completed"]
    excluded = [entry for entry in attempts if entry["status"] != "completed"]
    rows = collect(history, entries)
    candidate = min(rows, key=lambda r: r["equal_weight_p95_seconds"])
    lines = ["# Perbandingan slot eksekusi — 30 pengguna", "",
        "Jumlah proses worker eksekusi dan slot runner diubah bersama, dengan nilai yang sama. Ini pengujian kapasitas paralel keseluruhan, bukan isolasi pengaruh semaphore runner saja. Source Compose dan kode aplikasi tidak diubah oleh sweep; konfigurasi normal dipulihkan setelah setiap skenario.", "",
        "Setiap konfigurasi: 30 akun/kelas baru, satu learning path dan soal penjumlahan, 15 C17/15 C++17, 5 test case, 4 baseline API, 30 Run dan 30 Submit. Ada 8 kontrol RPC tanpa profiler dan 8 dengan profiler. Scheduler tetap 1 detik; dispatcher tetap berbagi worker dengan eksekusi. Batas pending kelas tetap 20.", "",
        "Pengiriman burst HTTP serentak mewakili klik; waktu render browser tidak diukur. Poll hasil setiap 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; ini bukan retry otomatis UI. Waktu sejak percobaan pertama memasukkan penolakan dan jeda retry tersebut.", "",
        "## Waktu sejak percobaan pertama sampai hasil terlihat", "",
        "Semua angka detik. Ini ukuran utama pengalaman 30 peserta, termasuk antrean dan retry admission.", "",
        "| Slot / proses worker | Run rata-rata | Run P95 | Run maksimum | Submit rata-rata | Submit P95 | Submit maksimum |",
        "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        values = [row["phases"][p]["first_try"][k]/1000 for p in ("run_30", "submit_30") for k in ("mean", "p95", "max")]
        lines.append(f"| {row['slots']} | "+" | ".join(f"{v:.3f}" for v in values)+" |")
    lines += ["", "## Waktu setelah request yang diterima dan di dalam runner", "",
        "Kolom request dimulai dari pengiriman HTTP yang akhirnya diterima, mencakup waktu penerimaan API. Kolom runner hanya bagian eksekusi sehingga tidak boleh dipakai sendiri untuk menilai waktu pengguna.", "",
        "| Slot | Run request rata-rata / P95 | Run runner rata-rata | Submit request rata-rata / P95 | Submit runner rata-rata |",
        "|---:|---:|---:|---:|---:|"]
    for row in rows:
        a, b = row["phases"]["run_30"], row["phases"]["submit_30"]
        lines.append(f"| {row['slots']} | {a['accepted_request']['mean']/1000:.3f} / {a['accepted_request']['p95']/1000:.3f} | {a['runner']['mean']/1000:.3f} | {b['accepted_request']['mean']/1000:.3f} / {b['accepted_request']['p95']/1000:.3f} | {b['runner']['mean']/1000:.3f} |")
    lines += ["", "## Antrean, admission, dan kapasitas yang teramati", "",
        "| Slot | Run outbox / antre worker | Submit outbox / antre worker | Run / Submit lock admission rata-rata | Puncak running |",
        "|---:|---:|---:|---:|---:|"]
    for row in rows:
        a, b = row["phases"]["run_30"], row["phases"]["submit_30"]
        lines.append(f"| {row['slots']} | {a['outbox']['mean']/1000:.3f} / {a['worker_wait']['mean']/1000:.3f} | {b['outbox']['mean']/1000:.3f} / {b['worker_wait']['mean']/1000:.3f} | {a['api_lock']['mean']/1000:.3f} / {b['api_lock']['mean']/1000:.3f} | {row['queue_peaks']['running']} |")
    lines += ["", "| Slot | Run awal diterima / 429 | Submit awal diterima / 429 | Durasi fase Run / Submit | Retry eksekusi |",
              "|---:|---:|---:|---:|---:|"]
    for row in rows:
        a, b = row["phases"]["run_30"], row["phases"]["submit_30"]
        lines.append(f"| {row['slots']} | {a['initial_http'].get('202',0)} / {a['initial_http'].get('429',0)} | {b['initial_http'].get('202',0)} / {b['initial_http'].get('429',0)} | {a['duration_seconds']:.3f} / {b['duration_seconds']:.3f} | {a['retries']+b['retries']} |")
    lines += ["", "## Sumber daya dan variasi kontrol", "",
        "CPU adalah penggunaan VM Docker keseluruhan, bukan satu sandbox. Kontrol Submit C++17 tanpa profiler adalah RPC tunggal pada konfigurasi normal, sebelum kapasitas kandidat diaktifkan; perubahan kontrol tersebut menunjukkan variasi host yang tidak boleh seluruhnya dikaitkan dengan jumlah slot.", "",
        "| Slot | CPU Run rata-rata / maksimum | CPU Submit rata-rata / maksimum | RAM available minimum Submit | Kontrol Submit C++17 tanpa profiler |",
        "|---:|---:|---:|---:|---:|"]
    for row in rows:
        a, b = row["phases"]["run_30"], row["phases"]["submit_30"]
        if "vm_cpu_mean" in a and "vm_cpu_mean" in b:
            lines.append(f"| {row['slots']} | {a['vm_cpu_mean']:.1f}% / {a['vm_cpu_max']:.1f}% | {b['vm_cpu_mean']:.1f}% / {b['vm_cpu_max']:.1f}% | {b['vm_memory_available_min_gib']:.2f} GiB | {row['unprofiled_cpp_submit_ms']/1000:.3f} dtk |")
    lines += ["", "## Kandidat konfigurasi", "",
        f"Di antara konfigurasi baru yang diuji, **{candidate['slots']} slot / {candidate['slots']} proses worker** memiliki jumlah P95 Run dan Submit sejak percobaan pertama paling rendah ({candidate['equal_weight_p95_seconds']:.3f} detik). Kriteria ini memberi bobot sama pada kedua aksi. Ini kandidat untuk pengujian lanjutan, bukan bukti optimum produksi.", "",
        "Jumlah slot lebih sedikit dapat mempercepat pekerjaan yang sedang berjalan sambil menambah antrean. Baca kedua tabel waktu bersama; jumlah worker rendah juga dapat menunda dispatcher yang berbagi antrean. Kandidat belum diterapkan sebagai konfigurasi normal.", "",
        "## Kebenaran hasil dan keterbatasan", "",
        f"Seluruh {64*len(rows)} pekerjaan API pada konfigurasi baru tervalidasi dengan verdict yang diharapkan; setiap konfigurasi lengkap 64/64 trace dan seluruh peserta mencapai progres/nilai 100. Kelas fixture dihapus, masing-masing 30 akun dinonaktifkan. Delivery Celery bisa lebih banyak daripada eksekusi jika pesan duplikat dijadwalkan; lihat data setiap konfigurasi.", "",
        "Setiap kapasitas memakai satu cohort lengkap untuk peringkat. Percobaan ulang, bila ada, dicatat pada manifest dan bagian percobaan yang tidak masuk peringkat. Belum mengendalikan efek urutan, variasi host, cache, atau beban berkelanjutan. Rekomendasi yang berdekatan perlu diuji ulang dalam urutan berbeda. Data memakai profiler; kontrol pengaruh profiler dan sumber daya VM tersedia pada laporan setiap konfigurasi.", "",
        "## Laporan per konfigurasi dan pengulangan", ""]
    for row in rows:
        lines.append(f"- [{row['slots']} slot / worker](../{row['directory']}/LAPORAN_DETAIL_RUN_SUBMIT.md): fixture `{row['run_id']}`, delivery worker {row['deliveries']}, cleanup `{row['cleanup']}`.")
    if excluded:
        lines += ["", "## Percobaan yang tidak masuk peringkat", "",
                  "Percobaan tidak lengkap/gagal tetap disimpan dan harus dibaca sebagai temuan stabilitas. Peringkat hanya memakai cohort lengkap yang lolos validasi, sehingga tidak mewakili tingkat keberhasilan seluruh percobaan."]
        for entry in excluded:
            raw = read(history/entry['directory']/"results.json")
            lines.append(f"\n- [{entry['slots']} slot, status {entry['status']}](../{entry['directory']}/results.json): {json.dumps(raw['summary']['anomalies'], ensure_ascii=False)}")
    lines += ["", "Pembanding 50 slot terdahulu dengan API admission yang sama: [laporan](../judging-profile-20261104-115413-6490f7/LAPORAN_DETAIL_RUN_SUBMIT.md). Run pertama → hasil rata-rata 15,354 detik/P95 21,887 detik; Submit 30,541 detik/P95 44,194 detik. Pengukuran 50 slot itu dilakukan pada waktu berbeda dan bukan bagian urutan sweep ini.", "",
        "```powershell", "./scripts/test-slot-sweep.ps1", "# Satu konfigurasi saja:", "./scripts/test-judging-profile.ps1 -Slots 8", "```", "",
        "[Data perbandingan](comparison.json) dan [manifest urutan/status](manifest.json). Laporan per konfigurasi berisi timeline terburuk dan waktu antar-container; laporan lama tidak ditimpa."]
    target = directory/"LAPORAN_PERBANDINGAN_SLOT.md"
    assert not target.exists(), "Refusing to overwrite an existing comparison"
    target.write_text("\n".join(lines)+"\n", encoding="utf-8")
    (directory/"comparison.json").write_text(json.dumps({"runs": rows, "excluded_attempts": excluded, "candidate_slots": candidate["slots"],
        "criterion": "minimum sum of Run and Submit first-try-to-client P95"}, indent=2), encoding="utf-8")
    print(f"Comparison created: {target}")


if __name__ == "__main__":
    write_report(Path(sys.argv[1]))
