import { ui, tr, localeControl, getLocale, setLocale } from "./i18n.js";
export const state = {
  user: null,
  route: 0,
  catalog: [],
  courses: [],
  editor: null,
};
export const $ = (selector, root = document) => root.querySelector(selector);
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  menu: "M4 6h16M4 12h16M4 18h16",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  book: "M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H4zM13 7a3 3 0 0 1 3-3h5v14h-4a4 4 0 0 0-4 3",
  code: "m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18",
  path: "M5 4h10a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h10M3 2v4m16 12v4",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  back: "M20 12H4m6-6-6 6 6 6",
  chevron: "m9 5 7 7-7 7",
  check: "m5 12 4 4L19 6",
  lock: "M6 10h12v11H6zM8 10V6a4 4 0 0 1 8 0v4",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  plus: "M12 5v14M5 12h14",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M20 21v-2a4 4 0 0 0-3-3.87M12 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M17 3a4 4 0 0 1 0 8",
  edit: "m16 3 5 5-12 12-6 1 1-6zM14 5l5 5",
  logout: "M9 21H3V3h6m6 5 4 4-4 4M8 12h11",
  play: "m8 4 12 8-12 8z",
  trophy:
    "M8 3h8v7a4 4 0 0 1-8 0zM8 5H3v3a5 5 0 0 0 5 5m8-8h5v3a5 5 0 0 1-5 5M12 14v7m-4 0h8",
  search: "M20 20l-5-5M17 9a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  file: "M5 2h9l5 5v15H5zM14 2v6h5M9 12h6m-6 4h6",
  shield: "m12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6zM8 12l3 3 5-6",
  close: "m6 6 12 12M6 18 18 6",
  copy: "M8 8h13v13H8zM16 8V3H3v13h5",
  up: "m6 14 6-6 6 6",
  down: "m6 10 6 6 6-6",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7",
  refresh: "M20 7a9 9 0 1 0 1 8M20 2v6h-6",
  archive: "M3 3h18v5H3zM5 8v13h14V8M10 12h4",
  globe:
    "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M2 12h20M12 2a20 20 0 0 1 0 20 20 20 0 0 1 0-20",
};
export const icon = (name) =>
  ui`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
export const badge = (text, cls = "") =>
  ui`<span class="badge ${cls}">${esc(text)}</span>`;
export const progress = (value) =>
  ui`<div class="progress-track"><progress value="${Math.max(0, Math.min(100, Number(value) || 0))}" max="100" aria-label="Progres belajar"></progress></div>`;
export const language = (value) => (value === "c17" ? "C17" : "C++17");
export const courseStatusTabs = (base, archived) =>
  ui`<nav class="tabs" aria-label="Status kelas"><a class="btn ghost ${archived ? "" : "active"}" href="#/${base}" ${archived ? "" : 'aria-current="page"'}>Kelas aktif</a><a class="btn ghost ${archived ? "active" : ""}" href="#/${base}/archive" ${archived ? 'aria-current="page"' : ""}>Arsip kelas</a></nav>`;
export function pagination(base, offset, count) {
  return ui`<nav class="row wrap" aria-label="Halaman laporan">${offset ? ui`<a class="btn" href="#${base}/${Math.max(0, offset - 100)}">Sebelumnya</a>` : ""}${count === 100 ? ui`<a class="btn" href="#${base}/${offset + 100}">Berikutnya</a>` : ""}</nav>`;
}
export function duration(seconds) {
  if (seconds == null) return tr("Belum selesai");
  let value = Math.max(0, Math.floor(seconds));
  const days = Math.floor(value / 86400);
  value %= 86400;
  const hours = Math.floor(value / 3600);
  value %= 3600;
  const minutes = Math.floor(value / 60);
  return ui`${days ? days + tr(" hari ") : ""}${hours ? hours + tr(" jam ") : ""}${minutes ? minutes + tr(" menit ") : ""}${value % 60} detik`;
}
export function learningTime(enrollment) {
  return ui`<span class="learning-duration" ${enrollment.completed_at ? "" : ui`data-elapsed-start="${esc(enrollment.started_at)}"`}>${duration(enrollment.elapsed_seconds)}</span>${enrollment.completed_at ? tr(" · selesai") : tr(" · berjalan")}`;
}
setInterval(() => {
  document.querySelectorAll("[data-elapsed-start]").forEach((el) => {
    el.textContent = duration(
      (Date.now() - Date.parse(el.dataset.elapsedStart)) / 1000,
    );
  });
}, 1000);
export const languages = (values) => (values || []).map(language).join(" / ");
export const roleLabel = (role) =>
  ({ admin: "Administrator", teacher: tr("Pengajar"), student: tr("Peserta") })[
    role
  ] || role;
export const date = (value) =>
  new Intl.DateTimeFormat(getLocale() === "en" ? "en-GB" : "id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jakarta",
  }).format(new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z"));
export const empty = (title, message, action = "", name = "book") =>
  ui`<div class="empty">${icon(name)}<h3>${esc(title)}</h3><p>${esc(message)}</p>${action}</div>`;
export const button = (text, action, extra = "", cls = "") =>
  ui`<button class="btn ${cls}" data-action="${action}" ${extra}>${esc(text)}</button>`;
export function go(path) {
  location.hash = path;
}
export function refresh() {
  window.dispatchEvent(new Event("kode:refresh"));
}
export function toast(text) {
  const box = $("#toast");
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    box.hidden = true;
  }, 5000);
}
export function closeModal() {
  const modal = $("#modal");
  if (modal.open) modal.close();
  modal.innerHTML = "";
}
export function modal(title, body) {
  const box = $("#modal");
  box.innerHTML = ui`<div class="row spread"><h2 id="modal-title">${esc(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="Tutup">${icon("close")}</button></div>${body}`;
  if (!box.open) box.showModal();
}
function csrf() {
  return (
    document.cookie
      .split("; ")
      .find((v) => v.startsWith("judgement_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") || ""
  );
}
export async function api(path, options = {}) {
  const { method = "GET", body, headers = {}, ...rest } = options;
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    ...rest,
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(["GET", "HEAD"].includes(method)
        ? {}
        : { "X-CSRF-Token": decodeURIComponent(csrf()) }),
      ...headers,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = response.headers
    .get("content-type")
    ?.includes("application/json")
    ? await response.json()
    : {};
  if (!response.ok) {
    let message = Array.isArray(data.detail)
      ? data.detail
          .map((x) => ui`${x.loc?.slice(1).join(".") || "Data"}: ${x.msg}`)
          .join("\n")
      : data.detail || tr("Layanan belum dapat memproses permintaan.");
    const translations = {
      "A published learning path requires at least one required step": tr("Learning path harus memiliki minimal satu langkah wajib sebelum diterbitkan."),
      "Current password is incorrect": tr("Password saat ini tidak sesuai."),
      "New password must differ from current password": tr(
        "Password baru harus berbeda.",
      ),
      "Email is already in use": tr("Email sudah digunakan."),
      "Course not found": tr(
        "Untuk kelas privat, masukkan kode undangan atau hubungi pengajar untuk penugasan.",
      ),
      "Invalid or expired invitation code": tr(
        "Kode undangan tidak valid, kedaluwarsa, atau sudah dinonaktifkan.",
      ),
      "Class settings changed; reload before saving": tr(
        "Pengaturan telah berubah. Muat ulang halaman sebelum menyimpan.",
      ),
      "Invitation codes are only available for private classes": tr(
        "Kode undangan hanya tersedia untuk kelas privat.",
      ),
      "Class archived; restore it before making changes": tr(
        "Kelas diarsipkan. Pulihkan kelas sebelum membuat perubahan.",
      ),
      "Class name confirmation does not match": tr(
        "Nama kelas belum sesuai. Ketik nama kelas persis seperti yang ditampilkan.",
      ),
      "Class has running judging jobs; wait for them to finish before deletion":
        tr(
          "Masih ada penilaian atau uji kunci berjalan. Tunggu hingga selesai, lalu hapus kelas kembali.",
        ),
      "Invalid username or password": tr(
        "Username atau kata sandi belum sesuai.",
      ),
      "Session invalid or expired": tr("Sesi berakhir. Silakan masuk kembali."),
      "Authentication required": tr("Silakan masuk untuk melanjutkan."),
      "Account cannot be created": tr(
        "Username tidak tersedia. Gunakan username lain.",
      ),
      "Rate limit exceeded": tr(
        "Terlalu banyak percobaan. Silakan tunggu sebelum mencoba lagi.",
      ),
      "Account submission/run quota exceeded": tr(
        "Batas pengiriman akun tercapai. Tunggu pekerjaan sebelumnya selesai atau coba lagi nanti.",
      ),
      "Current draft must pass reference validation before publication": tr(
        "Uji kunci untuk draft terbaru terlebih dahulu sebelum menerbitkan soal.",
      ),
      "Configured judging plugin unavailable": tr("Plugin penilaian tidak tersedia. Aktifkan kembali atau hubungi administrator."),
      "Configured provider unavailable": tr("Plugin penilaian tidak tersedia. Aktifkan kembali atau hubungi administrator."),
      "Plugin version already installed; use a new version number": tr("Versi plugin sudah terpasang. Gunakan nomor versi baru."),
      "Deactivate the plugin before uninstalling": tr("Nonaktifkan plugin sebelum menghapusnya."),
      "Plugin is referenced by problems or judging history; keep it installed": tr("Plugin masih digunakan oleh soal atau histori penilaian."),
      "Invalid plugin package: use API v1, plugin.json and plugin.py (maximum 256 KiB)": tr("Paket plugin tidak valid. Periksa format API v1, isi ZIP, dan batas 256 KiB."),
      "Select an active judging plugin": tr("Pilih plugin penilaian yang aktif."),
      "Draft changed; reload before continuing": tr(
        "Draft telah berubah. Muat ulang sebelum menyimpan.",
      ),
      "Complete the prerequisites before opening this step": tr(
        "Selesaikan langkah prasyarat terlebih dahulu.",
      ),
      "Exercise completion requires an accepted official submission": tr(
        "Latihan selesai setelah jawaban dinyatakan benar.",
      ),
    };
    message = translations[message] || message;
    if (
      response.status === 401 &&
      state.user &&
      !path.startsWith("/auth/login")
    ) {
      state.user = null;
      window.dispatchEvent(new Event("kode:expired"));
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}
export async function formTask(form, task) {
  if (form.dataset.busy) return;
  form.dataset.busy = "true";
  const controls = [
    ...form.querySelectorAll("button,input,textarea,select"),
  ].map((el) => [el, el.disabled]);
  controls.forEach(([el]) => {
    el.disabled = true;
  });
  const error = $(".form-error", form);
  if (error) error.textContent = "";
  try {
    await task();
  } catch (e) {
    if (error) error.textContent = e.message;
    else toast(e.message);
  } finally {
    delete form.dataset.busy;
    controls.forEach(([el, disabled]) => {
      el.disabled = disabled;
    });
  }
}
export function formFooter(text = tr("Simpan")) {
  return ui`<div class="form-error" role="alert"></div><div class="modal-footer"><button type="button" class="btn" data-action="close-modal">Batal</button><button class="btn primary" type="submit">${esc(text)}</button></div>`;
}
export const verdicts = {
  ACCEPTED: tr("Jawaban benar"),
  WRONG_ANSWER: tr("Hasil belum sesuai"),
  COMPILATION_ERROR: tr("Kesalahan kompilasi"),
  RUNTIME_ERROR: tr("Program berhenti dengan error"),
  TIME_LIMIT_EXCEEDED: tr("Batas waktu terlampaui"),
  MEMORY_LIMIT_EXCEEDED: tr("Batas memori terlampaui"),
  OUTPUT_LIMIT_EXCEEDED: tr("Keluaran terlalu banyak"),
  EXECUTED: tr("Program berhasil dijalankan"),
};
export function renderResult(row) {
  const compiler = ["c17", "cpp17"].includes(row.language)
    ? ui`<span class="badge" data-compiler="${row.language}">${language(row.language)} · ${row.language === "c17" ? "GCC" : "G++"}</span>`
    : "";
  if (row.state === "system_error")
    return ui`<div class="result-box"><div class="result-title">${icon("refresh")}Penilaian sedang bermasalah</div><p>Kode tersimpan. Gangguan layanan tidak diberi nilai nol.</p></div>`;
  if (row.state !== "completed")
    return ui`<div class="result-box"><div class="result-title"><span class="spinner"></span>${row.state === "running" ? tr("Mengompilasi dan menguji program…") : tr("Menunggu giliran penilaian…")}</div><small>Hasil akan muncul secara otomatis.</small></div>`;
  const success = ["ACCEPTED", "EXECUTED"].includes(row.verdict),
    result = row.result || {};
  return ui`<div class="result-box ${success ? "success" : ""}"><div class="row spread"><div class="result-title">${icon(success ? "check" : "code")}${esc(verdicts[row.verdict] || row.verdict)}</div>${row.score == null ? "" : badge(ui`${row.score} / 100`, success ? "active" : "")}</div>
    ${compiler}
    ${row.language === "c17" && row.verdict === "COMPILATION_ERROR" && /iostream|std::/.test(result.compile_log || "") ? tr('<p class="subtle-note compiler-hint">Kode ini menggunakan fitur C++. Pilih compiler C++17 (G++) di editor jika tersedia, lalu jalankan kembali.</p>') : ""}
    ${result.compile_log ? ui`<details ${row.verdict === "COMPILATION_ERROR" ? "open" : ""}><summary>Pesan compiler</summary><pre>${esc(result.compile_log)}</pre></details>` : ""}
    ${(result.cases || []).map((c, i) => ui`<div class="status-line">${icon(["ACCEPTED", "EXECUTED"].includes(c.verdict) ? "check" : "code")}<span>${row.mode === "run" ? tr("Input percobaan") : ui`Kasus uji ${i + 1}`}</span><span class="muted">${esc(verdicts[c.verdict] || c.verdict)}</span></div>${c.stdout !== undefined ? ui`<details ${row.mode === "run" || c.verdict === "WRONG_ANSWER" ? "open" : ""}><summary>${row.mode === "run" ? tr("Output program") : tr("Detail contoh terbuka")}</summary>${c.expected != null ? ui`<small>Output yang diharapkan</small><pre>${esc(c.expected)}</pre>` : ""}<small>Output program</small><pre>${esc(c.stdout || tr("(tidak ada output)"))}</pre>${c.stderr ? ui`<small>Pesan error</small><pre>${esc(c.stderr)}</pre>` : ""}</details>` : ""}`).join("")}
    ${row.verdict === "ACCEPTED" && row.enrollment_id ? tr('<p class="subtle-note">Progres langkah ini sudah tersimpan.</p>') : ""}</div>`;
}
