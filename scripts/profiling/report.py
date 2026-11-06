"""Render a new report from measured jobs; never fabricate a timeline by summing stage maxima."""
import json
from pathlib import Path
import sys

from analyze import stats


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def report(directory, baseline=None):
    data, analysis = read(directory/"results.json"), read(directory/"stage-analysis.json")
    environment, runtime = read(directory/"environment.json"), read(directory/"runtime-config.json")
    runner = read(directory/"runner-runtime.json")
    summary = data["summary"]
    execution_concurrency = sum(w["concurrency"] for w in runtime["workers"] if "celery" in w["queues"])
    lines = [f"# Profil waktu Run dan Submit — konfigurasi {execution_concurrency} worker / {runner['runner_slots']} slot runner", "",
        f"Pengujian baru: `{summary['run_id']}`. Mulai UTC: {summary['started_utc']}. Laporan/data pengujian lama dipertahankan.", "",
        "## Lingkungan dan metode", "",
        f"- Docker: {environment['docker_cpus']} vCPU, {environment['docker_memory_bytes']/1024**3:.2f} GiB RAM.",
        f"- Worker eksekusi aktual: {[(w['concurrency'], w['process_count']) for w in runtime['workers'] if 'celery' in w['queues']]} (concurrency, jumlah proses). Runner: **{runner['runner_slots']} slot** dalam satu container pengendali.",
        f"- Scheduler: **{runtime['dispatch_interval_seconds']} detik**. Dispatcher dan eksekusi tetap berbagi antrean `celery`. Validator tetap terpisah.",
        "- Batas pending kelas tetap **20** dan batas per jam tetap 200. Concurrency terkonfigurasi bukan bukti jumlah eksekusi aktif; uji memakai 30 siswa pada satu kelas.",
        "- Fixture baru: kelas privat, satu learning path, materi dan soal penjumlahan dengan 5 kasus; 15 C17 dan 15 C++17. Empat baseline API, lalu 30 Run dan 30 Submit serentak. Delapan kontrol RPC runner tanpa profiler dan delapan dengan profiler.",
        f"- Kode kompilasi/eksekusi nyata. Jumlah container fisik per pekerjaan terukur: {sorted({j['container_count'] for j in analysis['job_rows']})}. Fase kompilasi/input terukur: {sorted({j.get('execution_phase_count', j['container_count']) for j in analysis['job_rows']})}. Jika satu container dipakai ulang, proses dimulai ulang antar-fase; belum menerapkan sandbox persisten per pengguna.",
        "- Polling dimulai segera untuk setiap pekerjaan yang diterima, interval 1 detik. HTTP 429 dikirim ulang oleh alat uji setelah gelombang sebelumnya selesai; UI tidak otomatis melakukan retry tersebut.",
        f"- Fixture: `{summary['run_id']}`. Nama kelas: `Performance 30 users {summary['run_id']}`. Identitas peserta/pekerjaan tersimpan di hasil mentah.", "",
        "## Hasil dan waktu pengguna", "",
        "| Fase | Diterima / 429 pada burst awal | Hasil akhir | Durasi fase | Retry eksekusi |",
        "|---|---|---|---:|---:|"]
    for phase in summary["phases"]:
        lines.append(f"| {phase['name']} | {phase['initial_http']} | {phase['verdicts']} | {phase['duration_seconds']:.3f} dtk | {phase['retries']} |")
    lines += ["", f"Status harness: **{summary['status']}**. Anomali: **{len(summary['anomalies'])}**. Puncak sampling: `{summary['queue_peaks']}`.",
        f"Trace: {analysis['trace_records']} rekaman; {analysis['jobs_joined']}/{analysis['jobs_requested']} pekerjaan berhasil dihubungkan. Masalah analisis: `{analysis['issues']}`. Error span: `{analysis['profile_errors']}`.", "",
        f"Catatan timestamp: `{analysis.get('measurement_notes', [])}`. Hook Python `after_commit` dapat terjadwal setelah transaksi sudah terlihat oleh dispatcher. Jika publikasi lebih dulu daripada observasi hook, batas API/outbox memakai waktu publikasi (outbox 0); selisih dicatat sebagai ketidakpastian batas antar-tahap, bukan antrean negatif. Total request sampai hasil tidak berubah.", "",
        "## Waktu pada setiap tahap dan jalur container", "",
        "Satuan detik. Baris utama berurutan sejak pengiriman HTTP yang diterima. Rata-rata/P95 per skenario berisi 30 pekerjaan. P95 antartahap tidak dijumlahkan. Pemicu scheduler adalah pesan tugas; fungsi dispatcher berjalan di container `worker`, bukan di `scheduler`.", "",
        "| Tahap | Run rata-rata | Run P95 | Submit rata-rata | Submit P95 | Jalur container |",
        "|---|---:|---:|---:|---:|---|"]
    stages = [
        ("Request → awal handler API", "request_pre_handler_ms", "Klien uji → `api`; termasuk autentikasi/dependensi sebelum handler."),
        ("API → commit pekerjaan", "api_until_commit_ms", "`api` → `db`; termasuk lock admission dan pemeriksaan provider ke `runner`."),
        ("Menunggu pemicu scheduler", "scheduler_trigger_gap_ms", "Pekerjaan sudah di `db`; `scheduler` → `redis` ketika jadwal tiba."),
        ("Dispatcher menunggu worker", "dispatcher_wait_after_commit_ms", "Tugas dispatcher di jalur `redis` → `worker`, termasuk kemungkinan reservasi Celery. Sandbox belum dibuat."),
        ("Dispatcher memublikasikan pekerjaan", "dispatcher_prepare_publish_ms", "Dispatcher di `worker` → `db` dan `redis`."),
        ("Pekerjaan menunggu worker eksekusi", "broker_worker_wait_ms", "Pesan eksekusi pada jalur `redis` → `worker`. Sandbox belum dibuat."),
        ("Worker claim/load", "worker_claim_load_ms", "`worker` → `db`: klaim lease, muat source/test case."),
        ("Worker memanggil runner", "worker_runner_http_ms", "`worker` → `runner` → Docker Engine host → sandbox. Proses worker menunggu respons HTTP."),
        ("Worker validasi/simpan hasil", "worker_validate_save_ms", "`worker` → `db`; sandbox telah dibersihkan oleh runner."),
        ("Polling melihat hasil", "result_poll_lag_ms", "Jeda polling + klien uji → `api` → `db` → klien."),
        ("**Total request diterima server → hasil tersimpan**", "request_to_db_ready_ms", "Total sebelum polling; bukan tahap tambahan."),
        ("**Total request → hasil terlihat klien**", "request_to_client_ms", "Total seluruh jalur di atas; bukan tahap tambahan."),
        ("Subtotal outbox", "outbox_wait_ms", "Gabungan menunggu scheduler, antre dispatcher, dan publikasi; jangan dijumlahkan lagi."),
        ("Di dalam runner", "runner_total_ms", "Bagian dari HTTP runner; bukan tambahan. Docker Engine berada pada host Docker, bukan container runner.")]
    for label, key, route in stages:
        values = []
        for phase in ("run_30", "submit_30"):
            metric = analysis["groups"].get(phase, {}).get("metrics_ms", {}).get(key, {})
            values += [f"{metric[k]/1000:.3f}" if k in metric else "tidak tersedia" for k in ("mean", "p95")]
        lines.append("| "+" | ".join([label, *values, route])+" |")
    lines += ["", "Nama container layanan: `judgementsystem-<service>-1`. Sandbox baru: `js-<attempt_id>`, dipakai ulang sepanjang satu pekerjaan. Versi lama memakai container terpisah bernama `js-<attempt_id>-compile` dan `js-<attempt_id>-run` per fase. `validator` hanya menangani validasi kunci pengajar pada setup, bukan Run/Submit siswa.", "",
        "## Biaya di dalam runner", "", "Detik rata-rata per pekerjaan; jumlah container fisik dibedakan dari jumlah fase/start proses. Baris subtotal dan diagnostik saling tumpang tindih.", "",
        "| Bagian | Run | Submit | Jalur container / arti pengukuran |", "|---|---:|---:|---|"]
    for label, key, route in [
        ("Create", "container_create_ms", "`runner` → Docker Engine: membuat sandbox."),
        ("Start", "container_start_ms", "`runner` → Docker Engine → proses sandbox."),
        ("Remove", "container_remove_ms", "`runner` → Docker Engine: menghapus sandbox."),
        ("Subtotal create/start/remove", "lifecycle_create_start_remove_ms", "Gabungan tiga baris di atas."),
        ("Siapkan stdin", "attach_stdin_ms", "`runner` → Docker Engine → stdin sandbox; hanya penyiapan koneksi."),
        ("Siapkan output", "attach_output_ms", "`runner` → Docker Engine → stream sandbox; hanya penyiapan stream."),
        ("Inspect", "inspect_ms", "`runner` → Docker Engine: memeriksa status sandbox."),
        ("Wait", "container_wait_ms", "`runner` → Docker Engine: menunggu status akhir. Pada runner terbaru mencakup waktu menunggu compiler/program selesai, bukan seluruhnya overhead Docker."),
        ("Atur batas memori", "update_limits_ms", "`runner` → Docker Engine: limit kompilasi/runtime pada container yang dipakai ulang."),
        ("Kontrol/I/O/tidur/waktu lain", "execute_other_ms", "Di `runner`, termasuk menunggu compiler/program; bukan seluruhnya overhead yang dapat dihapus."),
        ("Total runner", "runner_total_ms", "Seluruh pemrosesan pengendali dan sandbox."),
        ("Compiler wall (diagnostik)", "compiler_wall_ms", "Compiler di sandbox; tumpang tindih dengan total, bukan tambahan."),
        ("Compiler CPU (diagnostik)", "compiler_cpu_ms", "CPU child compiler di sandbox."),
        ("PID1 runtime (diagnostik)", "run_pid1_ms", "Lifetime sandbox program, termasuk bootstrap/stdin; bukan CPU murni program."),
        ("Pemeriksaan output", "check_output_ms", "Perbandingan token di `runner`, di luar sandbox.")]:
        values = [analysis["groups"][p]["metrics_ms"].get(key, {"mean": 0})["mean"]/1000 for p in ("run_30", "submit_30")]
        lines.append(f"| {label} | {values[0]:.6f} | {values[1]:.6f} | {route} |")

    lines += ["", "## Timeline terburuk dari pekerjaan nyata", "",
        "Titik nol adalah pengiriman request pertama sebagai pengganti klik; waktu klik/render browser tidak diukur. Tiap timeline berasal dari satu pekerjaan, bukan gabungan maksimum berbagai peserta. Termasuk retry terkontrol untuk timeline sejak percobaan pertama."]
    def timeline(phase, accepted_only):
        rows = [row for row in analysis["job_rows"] if row["phase"] == phase]
        if not rows:
            return
        worst = max(rows, key=lambda row: row["request_to_client_ms"] if accepted_only else row["first_try_to_client_ms"])
        job = next(j for j in data["jobs"] if j["attempt_id"] == worst["attempt_id"])
        requests = sorted([q for q in data["requests"] if q["user"] == job["user"] and q["label"].startswith(phase+"_admission_wave_")], key=lambda q: q["start_s"])
        accepted = next(q for q in requests if q["status"] == 202)
        offset = accepted["start_s"]-job["submitted_s"]
        lines.extend(["", f"### {phase}: {'terlama sejak request yang diterima' if accepted_only else 'terlama sejak percobaan pertama'}", "",
            f"Peserta indeks {job['user']}, {job['language']}, attempt `{job['attempt_id']}`. HTTP: `{job['http_attempts']}`. Hasil `{job['verdict']}`. Waktu sejak request diterima: {worst['request_to_client_ms']/1000:.3f} detik; sejak percobaan pertama: {worst['first_try_to_client_ms']/1000:.3f} detik.", "",
            "| Rentang sejak request pertama (dtk) | Durasi (dtk) | Tahap dan jalur |", "|---:|---:|---|"])
        for index, q in enumerate(requests):
            if q["status"] == 202:
                continue
            start = q["start_s"]-job["submitted_s"]
            end = start+q["latency_ms"]/1000
            lines.append(f"| {start:.3f}–{end:.3f} | {end-start:.3f} | HTTP {q['status']} pada `api`/`db`. |")
            next_start = requests[index+1]["start_s"]-job["submitted_s"]
            lines.append(f"| {end:.3f}–{next_start:.3f} | {next_start-end:.3f} | Jeda retry alat uji; bukan antrean eksekusi pekerjaan yang sudah diterima. |")
        t = offset
        for label, key, route in stages[:10]:
            duration = worst[key]/1000
            lines.append(f"| {t:.3f}–{t+duration:.3f} | {duration:.3f} | {label}: {route} |")
            t += duration
        assert abs(t-worst["first_try_to_client_ms"]/1000) < .002
        lines.append(f"\nRespons HTTP 202 tiba pada t={offset+accepted['latency_ms']/1000:.3f} detik. Runner internal memerlukan {worst['runner_total_ms']/1000:.3f} detik, termasuk lifecycle {worst['lifecycle_create_start_remove_ms']/1000:.3f} detik; angka ini berada di dalam langkah HTTP runner.")
        origin = summary["clock_origin_ns"]+job["submitted_s"]*1e9
        executions = [json.loads(line) for file in (directory/"traces").glob("runner-*.jsonl")
                      for line in file.read_text().splitlines() if line.strip()]
        executions = sorted([r for r in executions if r["trace"] == job["attempt_id"] and r["kind"] == "span"
                             and r["name"] == "runner.execute"], key=lambda r: r["start_ns"])
        lines.extend(["", "Rincian sandbox di dalam langkah HTTP runner (bukan tahap tambahan atau CPU murni program). Timestamp wall clock dan durasi monotonic dapat menghasilkan ketidakselarasan beberapa ms pada batas span; urutan kasus mengikuti eksekusi serial dalam kode:", "",
                      "| Rentang sejak request pertama (dtk) | Durasi (dtk) | Fase sandbox |", "|---:|---:|---|"])
        for execution in executions:
            lines.append(f"| {(execution['start_ns']-origin)/1e9:.3f}–{(execution['end_ns']-origin)/1e9:.3f} | {execution['duration_ns']/1e9:.3f} | {execution['phase']}, input {execution['case_index']}: penyiapan/start, input/output, menunggu proses. ID container: {execution.get('container_id', 'tidak direkam versi lama')}. |")
    for phase in ("run_30", "submit_30"):
        timeline(phase, True)
        if any(len(j["http_attempts"]) > 1 for j in data["jobs"] if j["phase"] == phase):
            timeline(phase, False)

    if baseline and (baseline/"stage-analysis.json").exists():
        old = read(baseline/"stage-analysis.json")
        lines += ["", "## Perbandingan dengan konfigurasi lama", "",
            f"Pembanding: [{baseline.name}](../{baseline.name}/LAPORAN_DETAIL_RUN_SUBMIT.md). Rincian konfigurasi ada pada laporan pembanding. Dua hasil sama-sama memakai profiler; tidak berjalan bersamaan, sehingga variasi host juga dapat memengaruhi selisih.", "",
            "| Tahap rata-rata (detik) | Run lama | Run baru | Submit lama | Submit baru |", "|---|---:|---:|---:|---:|"]
        for label, key in (("Outbox", "outbox_wait_ms"), ("Dispatcher menunggu worker", "dispatcher_wait_after_commit_ms"),
                          ("Pekerjaan menunggu worker", "broker_worker_wait_ms"), ("Lock admission API", "api_lock_ms"),
                          ("Create container", "container_create_ms"), ("Start proses container", "container_start_ms"),
                          ("Remove container", "container_remove_ms"), ("Inspeksi Docker", "inspect_ms"),
                          ("Total runner", "runner_total_ms"), ("Request → hasil tersimpan", "request_to_db_ready_ms"),
                          ("Request → hasil terlihat", "client_observed_ms")):
            values = [source["groups"][phase]["metrics_ms"][key]["mean"]/1000 for phase in ("run_30", "submit_30") for source in (old, analysis)]
            lines.append("| "+label+" | "+" | ".join(f"{v:.3f}" for v in values)+" |")

    lines += ["", "## Kontrol pengaruh profiler", "",
        "RPC langsung ke runner, dua sampel per bahasa/mode per kondisi; selisih mencakup variasi host dan bootstrap profiling, bukan estimasi overhead presisi.", "",
        "| RPC | Tanpa profiler (dtk) | Dengan profiler (dtk) | Selisih |", "|---|---:|---:|---:|"]
    for key, old in analysis["calibration_ms"]["unprofiled"].items():
        new = analysis["calibration_ms"]["profiled"][key]
        lines.append(f"| {key} | {old['mean']/1000:.3f} | {new['mean']/1000:.3f} | {(new['mean']/old['mean']-1)*100:+.1f}% |")
    resources = directory/"resources.jsonl"
    if resources.exists():
        samples = [json.loads(line) for line in resources.read_text().splitlines() if line.strip()]
        lines += ["", "## Sumber daya host Docker", "",
            "Sampling `/proc` dari container pemantau: CPU dan memori VM Linux Docker keseluruhan, bukan per sandbox. Beban lain di VM dapat ikut terhitung. Memori available berbeda dari penjumlahan batas memori container."]
        for phase in summary["phases"]:
            start = summary["clock_origin_ns"]+phase["start_s"]*1e9
            end = start+phase["duration_seconds"]*1e9
            selected = [s for s in samples if start <= s["at_ns"] <= end and s["vm_cpu_percent"] is not None]
            if selected:
                lines.append(f"\n- {phase['name']}: {len(selected)} sampel; CPU rata-rata {stats([s['vm_cpu_percent'] for s in selected])['mean']:.1f}%, maksimum {max(s['vm_cpu_percent'] for s in selected):.1f}%; memori available minimum {min(s['vm_memory_available_bytes'] for s in selected)/1024**3:.2f} GiB.")
    lines += ["", "## Analisis hambatan", ""]
    for phase in ("run_30", "submit_30"):
        metrics = analysis["groups"][phase]["metrics_ms"]
        lines.append(f"- {phase}: antre worker rata-rata {metrics['broker_worker_wait_ms']['mean']/1000:.3f} detik; runner {metrics['runner_total_ms']['mean']/1000:.3f} detik; menunggu lock admission rata-rata {metrics['api_lock_ms']['mean']/1000:.3f} detik, maksimum {metrics['api_lock_ms']['max']/1000:.3f} detik. Lifecycle create/start/remove {metrics['lifecycle_create_start_remove_ms']['mean']/1000:.3f} detik berada di dalam runner.")
        if 'api_lock_held_ms' in metrics:
            lines.append(f"  Waktu lock dipegang sampai observasi commit: rata-rata {metrics['api_lock_held_ms']['mean']/1000:.3f} detik, P95 {metrics['api_lock_held_ms']['p95']/1000:.3f} detik; health check total {metrics['api_health_ms']['mean']/1000:.3f} detik per request.")
    lines += ["", "Angka tersebut perlu dibaca bersama kontrol tanpa profiler, sumber daya VM, dan batas admission. Concurrency lebih besar dapat mengurangi antrean sekaligus memperlambat setiap pekerjaan. Tidak ada optimasi lanjutan yang otomatis diterapkan oleh alat uji.",
        "", "## Anomali, validasi, dan batas kesimpulan", "",
        f"- Anomali harness: `{summary['anomalies']}`.",
        f"- Pemulihan fixture: `{summary['cleanup']}`. Akun dinonaktifkan, bukan dihapus; akun/kelas lama tidak dihapus.",
        f"- Jumlah delivery worker teramati {analysis['worker_deliveries']} untuk {len(data['jobs'])} pekerjaan API; cek retry dan trace sebelum menafsirkan delivery tambahan sebagai eksekusi ganda.",
        "- Self-check profiler dijalankan sebelum burst; regresi kapasitas runner tercatat pada VERIFIKASI.md. Trace memakai metadata eksplisit dan tidak mencatat source, input, password, atau token.",
        "- Pengujian hanya satu host, satu soal sederhana, burst 30 pengguna dan kuota pending 20; belum membuktikan kapasitas 50 program aktif, beban berkelanjutan, fault injection, atau target 5–7 detik pada soal lain.",
        "- Selesainya seluruh pekerjaan setelah retry admission tidak berarti seluruh burst awal diterima. Waktu sejak percobaan pertama mencakup jeda retry alat uji.", "",
        "## Berkas dan pengulangan", "",
        "[Hasil HTTP/jobs](results.json), [analisis tahap](stage-analysis.json), [CSV pekerjaan](job-stages.csv), [CSV container](container-stages.csv), [requests](requests.csv), [antrean](queue.csv), [trace](traces/), [konfigurasi aktual worker](runtime-config.json), [slot runner](runner-runtime.json), [lingkungan/image](environment.json).", "",
        "```powershell", "./scripts/test-judging-profile.ps1 -SelfCheck", "./scripts/test-judging-profile.ps1", "```", "",
        "Wrapper membaca command worker dari Compose, sehingga tidak memaksa concurrency lama. Build dan aktifkan konfigurasi yang hendak diuji terlebih dahulu. Wrapper memverifikasi kapasitas aktual, memasang profiling sementara, lalu mengembalikan command/image tanpa profiling di `finally`. Proses PowerShell yang dihentikan paksa tetap perlu pemulihan manual. Setiap pengulangan menghasilkan direktori baru."]
    target = directory/"LAPORAN_DETAIL_RUN_SUBMIT.md"
    assert not target.exists(), "Refusing to overwrite an existing report"
    target.write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Report created: {target}")


if __name__ == "__main__":
    report(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
