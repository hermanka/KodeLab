import { ui, tr, localeControl, getLocale, setLocale } from "./i18n.js";
import {
  state,
  $,
  esc,
  icon,
  badge,
  progress,
  courseStatusTabs,
  pagination,
  duration,
  learningTime,
  languages,
  language,
  roleLabel,
  date,
  empty,
  go,
  refresh,
  toast,
  modal,
  closeModal,
  api,
  formTask,
  formFooter,
  renderResult,
  verdicts,
} from "./core.js";
import {
  renderStudio,
  studioAction,
  studioSubmit,
  studioChange,
} from "./studio.js";

const root = $("#app");
const brand = ui`<a class="brand" href="#/dashboard" aria-label="KodeLab beranda"><img src="/assets/logo.svg" alt=""><span><strong>KodeLab</strong><small>C / C++ LEARNING SPACE</small></span></a>`;
const navLinks = () => [
  ["dashboard", "grid", tr("Ringkasan")],
  ["classes", "users", tr("Kelas")],
  ["leaderboard", "trophy", "Leaderboard"],
  ["history", "clock", tr("Riwayat kode")],
  ["profile", "users", tr("Profil")],
];
const isTeacher = () => ["teacher", "admin"].includes(state.user?.role);
function navLink([route, name, text], current) {
  return ui`<a href="#/${route}" class="${current === route ? "active" : ""}">${icon(name)}${text}</a>`;
}
function shell(content, section = "dashboard") {
  const user = state.user,
    teacherLinks = isTeacher()
      ? [["studio", "edit", tr("Studio pengajar")]]
      : [];
  const adminLinks =
    user.role === "admin" ? [["admin", "shield", tr("Administrasi")], ["admin/plugins", "code", tr("Plugin penilaian")]] : [];
  return ui`<header class="topbar"><div class="row"><button class="icon-button mobile-menu-toggle" data-action="open-sidebar" aria-label="Buka menu" aria-controls="main-sidebar" aria-expanded="false">${icon("menu")}</button>${brand}</div><div class="row">${localeControl()}<div class="user-info"><strong>${esc(user.full_name || user.username)}</strong><br><small>${roleLabel(user.role)}</small></div><button class="avatar" data-action="profile" aria-label="Akun ${esc(user.username)}">${esc(user.username.slice(0, 2).toUpperCase())}</button><button class="icon-button" data-action="logout" aria-label="Keluar">${icon("logout")}</button></div></header>
    <button class="sidebar-backdrop" data-action="close-sidebar" aria-label="Tutup menu" tabindex="-1" hidden></button>
    <div class="layout"><aside id="main-sidebar" class="sidebar" aria-label="Navigasi belajar"><div class="sidebar-mobile-heading"><strong>Menu</strong><button class="icon-button" data-action="close-sidebar" aria-label="Tutup menu">${icon("close")}</button></div><div class="nav-group"><small>RUANG BELAJAR</small>${navLinks()
      .map((x) => navLink(x, section))
      .join(
        "",
      )}</div>${teacherLinks.length ? ui`<div class="nav-group"><small>PENGELOLAAN</small>${[...teacherLinks, ...adminLinks].map((x) => navLink(x, section)).join("")}</div>` : ""}<div class="sidebar-note"><div class="mono">&lt;belajar /&gt;</div>Satu konsep, satu latihan.<br>Bangun pemahaman lewat kode.</div></aside><main id="main" class="page">${content}<footer class="footer-meta"><span>KodeLab · Ruang belajar C & C++</span><span>Baca. Tulis. Pahami.</span></footer></main></div>`;
}
function toggleSidebar(open) {
  const sidebar = $("#main-sidebar");
  if (!sidebar) return;
  sidebar.classList.toggle("is-open", open);
  $(".sidebar-backdrop").hidden = !open;
  $("[data-action='open-sidebar']").setAttribute("aria-expanded", String(open));
  $(".topbar").inert = open;
  $("#main").inert = open;
  if (open) $("button", sidebar).focus();
  else $("[data-action='open-sidebar']").focus();
}
document.addEventListener("keydown", (event) => {
  const sidebar = $("#main-sidebar.is-open");
  if (!sidebar) return;
  if (event.key === "Escape") {
    event.preventDefault();
    toggleSidebar(false);
  } else if (event.key === "Tab") {
    const controls = [...sidebar.querySelectorAll("button, a[href]")];
    const first = controls[0],
      last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
});
window.matchMedia("(max-width: 900px)").addEventListener("change", () => {
  if ($("#main-sidebar.is-open")) toggleSidebar(false);
});
function authPage(mode = "login") {
  const register = mode === "register";
  document.title = ui`${register ? tr("Daftar") : tr("Masuk")} — KodeLab`;
  root.innerHTML = ui`<header class="auth-top">${brand}${localeControl()}${badge(tr("BELAJAR DENGAN MENCOBA"))}</header><main id="main" class="auth-layout"><section class="auth-copy"><div class="eyebrow row">${icon("code")}RUANG BELAJAR UNTUK RASA INGIN TAHU</div><h1>Mulai dari logika.<br>Wujudkan<br>dengan kode.</h1><p>Pelajari C dan C++ selangkah demi selangkah. Baca konsepnya, tulis programnya, dan temukan jawaban lewat percobaan.</p><div class="row wrap">${badge("C17", "solid")}${badge("C++17", "solid")}<span class="inline-note">${icon("check")}Langsung di browser</span></div><div class="terminal"><div class="terminal-head"><div class="terminal-dots"><i></i><i></i><i></i></div><span>langkah_pertama.cpp</span>${icon("code")}</div><pre>#include &lt;iostream&gt;

int main() {
  std::cout &lt;&lt; <span class="highlight">"Halo, dunia!"</span>;
  return 0;
}</pre></div><div class="meta"><span>01 / Pahami konsep</span><span>02 / Coba sendiri</span><span>03 / Lanjutkan</span></div></section><section class="auth-form"><div class="eyebrow">${register ? tr("LANGKAH PERTAMAMU") : tr("SELAMAT DATANG KEMBALI")}</div><h2>${register ? tr("Buat ruang belajarmu.") : tr("Lanjutkan langkahmu.")}</h2><p>${register ? tr("Daftar sebagai peserta dan mulai jalur belajarmu.") : tr("Masuk untuk melanjutkan jalur dan kode yang kamu kerjakan.")}</p><form data-form="${register ? "register" : "login"}">${register ? tr('<div class="field"><label for="full-name">Nama lengkap</label><input id="full-name" name="full_name" required maxlength="120" autocomplete="name"></div><div class="field"><label for="registration-email">Email</label><input id="registration-email" type="email" name="email" required maxlength="254" autocomplete="email"></div>') : ""}<div class="field"><label for="username">Username</label><input id="username" name="username" autocomplete="username" required minlength="3" maxlength="40" pattern="[a-zA-Z][a-zA-Z0-9_]{2,39}" placeholder="username_kamu">${register ? tr('<span class="help">3–40 huruf, angka, atau underscore. Diawali huruf.</span>') : ""}</div><div class="field"><label for="password">Kata sandi</label><input id="password" name="password" type="password" autocomplete="${register ? "new-password" : "current-password"}" required minlength="15" maxlength="128" placeholder="${register ? tr("Minimal 15 karakter") : tr("Masukkan kata sandi")}"></div><div class="form-error" role="alert"></div><button class="btn primary full" type="submit">${register ? tr("Buat akun peserta") : tr("Masuk ke KodeLab")}${icon("arrow")}</button></form><div class="auth-switch">${register ? tr("Sudah punya akun?") : tr("Baru mulai belajar?")} <a class="text-button" href="#/${register ? "login" : "register"}">${register ? tr("Masuk") : tr("Buat akun")}</a></div></section></main><footer class="auth-footer"><span class="mono">// setiap langkah dimulai dari satu baris kode.</span><span>C & C++ · Belajar interaktif berbahasa Indonesia</span></footer>`;
}
function pageHead(eyebrow, title, subtitle, action = "") {
  return ui`<div class="page-head"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div>${action}</div>`;
}
function pathCard(path, enrolled = false) {
  const e = enrolled ? path : path.enrollment;
  return ui`<article class="path-card"><div class="row spread">${badge(languages(path.languages), "solid")}${badge(enrolled ? ui`VERSI ${path.revision}` : tr("JALUR BELAJAR"))}</div><div class="card-symbol">${path.languages?.length === 1 ? (path.languages[0] === "c17" ? "{ C }" : "{ C++ }") : "{ C / C++ }"}</div><h3>${esc(path.title)}</h3><p>${esc(path.description || tr("Bangun pemahaman pemrograman melalui materi dan latihan bertahap."))}</p><div class="meta"><span class="row">${icon("book")}${path.step_count ?? path.steps?.length ?? 0} langkah</span><span class="row">${icon("code")}${path.exercise_count ?? path.steps?.filter((s) => s.kind === "exercise").length ?? 0} latihan</span></div><div class="card-bottom">${e ? ui`<div class="row spread"><small>${e.completed_count}/${e.required_count} langkah wajib</small><small>${e.progress ?? 0}%</small></div>${progress(e.progress)}<p class="subtle-note">Lama pengerjaan: ${learningTime(e)}</p><a class="btn full ${e.complete ? "" : "primary"}" href="#/learning/${e.id}">${e.complete ? tr("Tinjau kembali") : tr("Lanjutkan belajar")}${icon("arrow")}</a>` : ui`<button class="btn full primary" data-action="enroll-path" data-id="${esc(path.id)}">Mulai belajar${icon("arrow")}</button>`}</div></article>`;
}
async function dashboard(ticket) {
  const [learning, courses, stats] = await Promise.all([
    api("/my/learning"),
    api("/courses"),
    api("/my/stats"),
  ]);
  if (ticket !== state.route) return;
  const complete = learning.filter((x) => x.complete).length;
  const accepted = stats.accepted_exercises;
  const active = learning.filter((x) => !x.complete && !x.course_archived);
  const followedIds = new Set(learning.map((x) => x.course_id));
  const followed = courses.filter((c) => !c.archived && followedIds.has(c.id));
  const available = courses.filter((c) => !c.archived);
  document.title = tr("Ringkasan belajar — KodeLab");
  root.innerHTML =
    shell(ui`${pageHead(tr("RUANG BELAJARMU"), ui`Halo, ${state.user.full_name || state.user.username}.`, tr("Setiap baris kode adalah satu langkah menuju pemahaman baru."), isTeacher() ? '<a class="btn" href="#/studio">' + icon("edit") + "Buka studio</a>" : "")}
    <section class="welcome-panel"><div><div class="eyebrow">${active.length ? tr("LANJUTKAN DARI SINI") : tr("BANGUN FONDASI YANG KUAT")}</div><h2>${esc(active[0]?.course_title || tr("Pemahaman dimulai dari mencoba."))}</h2><p>${active.length ? ui`${active[0].completed_count} dari ${active[0].required_count} langkah wajib sudah kamu selesaikan. Luangkan waktu untuk langkah berikutnya.` : tr("Temukan kelas, pilih jalur belajar di dalamnya, lalu pelajari C dan C++ selangkah demi selangkah.")}</p><a class="btn primary" href="${active.length ? ui`#/classes/${active[0].course_id}` : "#/classes"}">${active.length ? tr("Lanjutkan kelas") : tr("Jelajahi kelas")}${icon("arrow")}</a></div><div class="terminal"><div class="terminal-head"><span class="mono">progress.cpp</span>${icon("code")}</div><pre>while (ingin_belajar) {
  <span class="highlight">pahami</span>(konsep);
  <span class="highlight">coba</span>(kode);
  lanjutkan();
}</pre></div></section><section class="stats" aria-label="Statistik belajar"><div class="stat"><span>${icon("path")}</span><div><strong>${learning.length}</strong><small>Jalur diikuti</small></div></div><div class="stat"><span>${icon("code")}</span><div><strong>${accepted}</strong><small>Latihan berhasil</small></div></div><div class="stat"><span>${icon("trophy")}</span><div><strong>${complete}</strong><small>Jalur selesai</small></div></div></section><div class="section-head"><h2>${followed.length ? tr("Kelas yang kamu ikuti") : tr("Temukan kelas pertamamu")}</h2><a class="btn small ghost" href="#/classes">Lihat semua ${icon("arrow")}</a></div>${
      followed.length
        ? ui`<div class="cards">${followed.map(courseCard).join("")}</div>`
        : available.length
          ? ui`<div class="cards">${available.slice(0, 3).map(courseCard).join("")}</div>`
          : empty(
              tr("Kelas sedang disiapkan"),
              tr("Pengajar akan menyediakan kelas dan jalur belajar di sini."),
              isTeacher()
                ? tr(
                    '<a class="btn primary" href="#/studio">Buat kelas pertama</a>',
                  )
                : "",
            )
    }`);
}
function courseCard(course) {
  return ui`<article class="path-card course-card" data-course-id="${esc(course.id)}"><div class="row spread">${badge(course.archived ? tr("KELAS DIARSIPKAN") : course.is_public ? tr("KELAS PUBLIK") : tr("KELAS PRIVAT"), "solid")}${icon("users")}</div><div class="card-symbol">${icon("book")}</div><h3>${esc(course.title)}</h3><p>${esc(course.description || (course.archived ? tr("Tinjau kembali materi dan progres yang tersimpan.") : tr("Temukan learning path, pelajari materi, dan kerjakan latihan di dalam kelas ini.")))}</p><div class="card-bottom"><a class="btn primary full" href="#/classes/${esc(course.id)}">${course.archived ? tr("Tinjau kelas") : tr("Buka kelas")}${icon("arrow")}</a></div></article>`;
}
async function classesPage(ticket, archived = false, offset = 0) {
  const courses = await api(
    ui`/courses?status=${archived ? "archived" : "active"}&offset=${offset}`,
  );
  if (ticket !== state.route) return;
  state.courseCatalog = courses;
  document.title = ui`${archived ? tr("Arsip kelas") : tr("Kelas")} — KodeLab`;
  root.innerHTML = shell(
    ui`${pageHead(tr("TEMUKAN RUANG BELAJARMU"), tr("Mulai dari sebuah kelas."), tr("Buka kelas, pilih learning path, lalu pelajari materi dan kerjakan latihan secara bertahap."), archived ? "" : tr('<button class="btn" data-action="join-class">Gabung dengan kode</button>'))}${state.user.role === "student" ? "" : courseStatusTabs("classes", archived)}<div class="toolbar"><div class="row">${badge(ui`${courses.length} KELAS`)}<small>${archived ? tr("Kelas arsip yang dapat kamu tinjau.") : tr("Kelas publik dan kelas yang dapat kamu akses.")}</small></div><label class="search-wrap">${icon("search")}<span class="visually-hidden">Cari kelas</span><input id="class-search" placeholder="Cari kelas…" type="search"></label></div><div id="class-cards" class="cards">${courses.map(courseCard).join("")}</div>${courses.length ? "" : archived ? empty(tr("Belum ada kelas arsip"), tr("Kelas arsip yang dapat kamu akses akan muncul di sini.")) : empty(tr("Belum ada kelas tersedia"), tr("Kelas publik atau kelas yang ditugaskan kepadamu akan muncul di sini."))}`,
    "classes",
  );
  $("#main .footer-meta").insertAdjacentHTML("beforebegin", pagination(archived ? "/classes/archive" : "/classes/page", offset, courses.length));
}
async function classPage(id, ticket) {
  const data = await api(ui`/courses/${encodeURIComponent(id)}/learning`);
  let board;
  try {
    board = await api(ui`/courses/${encodeURIComponent(id)}/leaderboard`);
  } catch {}
  if (ticket !== state.route) return;
  const course = data.course,
    own = new Map(data.enrollments.map((e) => [e.path_id, e]));
  const paths = data.paths.map((p) =>
    own.has(p.id) ? { ...own.get(p.id), enrolled: true } : p,
  );
  const listed = new Set(data.paths.map((p) => p.id));
  paths.push(
    ...data.enrollments
      .filter((e) => !listed.has(e.path_id))
      .map((e) => ({ ...e, enrolled: true })),
  );
  document.title = ui`${course.title} — KodeLab`;
  root.innerHTML = shell(
    ui`<div class="breadcrumb"><a href="#/classes">Kelas</a>${icon("chevron")}<span>${esc(course.title)}</span></div>${pageHead(tr("RUANG BELAJAR"), course.title, course.description || tr("Pilih learning path di kelas ini untuk mulai belajar atau melanjutkan progresmu."), course.can_manage ? ui`<a class="btn" href="#/course/${course.id}/materials">${icon("edit")}Kelola kelas</a>` : "")}<div class="row wrap">${badge(course.archived ? tr("KELAS DIARSIPKAN") : course.is_public ? tr("KELAS PUBLIK") : tr("KELAS PRIVAT"), "solid")}${badge(ui`${paths.length} JALUR`)}</div>${course.archived ? tr('<p class="inline-note">Kelas diarsipkan. Materi dan progres yang sudah diikuti tetap dapat ditinjau.</p>') : ""}<div class="section-head"><h2>Learning path di kelas ini</h2></div><div class="cards">${paths.map((p) => pathCard(p, !!p.enrolled)).join("")}</div>${paths.length ? "" : empty(tr("Belum ada learning path"), tr("Pengajar belum menerbitkan jalur belajar di kelas ini."))}<section class="embedded-leaderboard" aria-labelledby="class-leaderboard-title"><div class="section-head"><h2 id="class-leaderboard-title">Leaderboard kelas</h2></div><p class="subtle-note">${leaderboardRules(true)}</p>${board ? leaderboardTable(board) : empty(tr("Leaderboard belum dapat dimuat"), tr("Muat ulang halaman untuk mencoba kembali."))}</section>`,
    "classes",
  );
}
function stepRows(enrollment, compact = false, current = "") {
  let module = "",
    number = 0,
    html = "";
  for (const step of enrollment.steps) {
    if (!compact && step.module !== module) {
      if (module) html += "</div>";
      module = step.module;
      number++;
      html += ui`<div class="module-head"><span class="module-number">${String(number).padStart(2, "0")}</span><h3>${esc(module)}</h3></div><div class="step-list">`;
    }
    html += ui`<button class="step-row ${step.completed ? "done" : ""} ${step.id === current ? "active" : ""}" data-action="open-step" data-enrollment="${enrollment.id}" data-id="${step.id}" ${step.locked ? "disabled" : ""}><span class="step-marker">${icon(step.completed ? "check" : step.locked ? "lock" : step.kind === "reading" ? "book" : "code")}</span><span class="grow"><strong>${esc(step.title)}</strong>${compact ? "" : ui`<small>${step.kind === "reading" ? tr("Materi") : tr("Latihan kode")} · ${step.required ? tr("Wajib") : tr("Opsional")}${step.locked ? tr(" · Selesaikan prasyarat") : ""}</small>`}</span>${compact ? "" : step.completed ? badge(tr("SELESAI"), "active") : icon(step.locked ? "lock" : "chevron")}</button>`;
  }
  return html + (!compact && module ? "</div>" : "");
}
async function learningPage(id, ticket) {
  const e = await api(ui`/enrollments/${id}`);
  if (ticket !== state.route) return;
  document.title = ui`${e.title} — KodeLab`;
  root.innerHTML = shell(
    ui`<div class="breadcrumb"><a href="#/classes">Kelas</a>${icon("chevron")}<a href="#/classes/${e.course_id}">${esc(e.course_title)}</a>${icon("chevron")}<span>${esc(e.title)}</span></div>${pageHead(tr("PERJALANAN BELAJAR"), e.title, e.description)}${e.course_archived ? tr('<p class="inline-note">Kelas diarsipkan. Konten dan progres tetap dapat ditinjau; pengerjaan baru dinonaktifkan.</p>') : ""}${e.complete ? ui`<div class="success-banner">${icon("trophy")}<div><h3>Jalur belajar selesai.</h3><p class="muted">Seluruh langkah wajib sudah kamu tuntaskan. Kamu dapat meninjau kembali materi dan latihan kapan saja.</p></div></div>` : ""}<div class="two-col"><section>${stepRows(e)}</section><aside class="panel"><div class="eyebrow">PROGRES BELAJARMU</div><div class="row spread"><h2>${e.progress ?? 0}%</h2>${badge(languages(e.languages), "solid")}</div>${progress(e.progress)}<p class="muted">${e.completed_count} dari ${e.required_count} langkah wajib selesai.</p><p class="subtle-note">Lama pengerjaan: ${learningTime(e)}</p><p class="subtle-note">Nilai latihan: ${e.score} / 100</p>${e.next_step_id ? ui`<a class="btn primary full" href="#/learn/${e.id}/${e.next_step_id}">Lanjutkan langkah ${icon("arrow")}</a>` : badge(e.complete ? tr("JALUR SELESAI") : tr("MATERI REFERENSI"), e.complete ? "active" : "")}<p class="subtle-note">Kamu mengikuti versi ${e.revision}. Progres tersimpan di akunmu.</p><div class="inline-note">${icon("shield")}Hanya jawaban benar yang menyelesaikan latihan.</div></aside></div>`,
    "classes",
  );
}
const starters = {
  c17: "#include <stdio.h>\n\nint main(void) {\n  // Tulis programmu di sini.\n\n  return 0;\n}\n",
  cpp17:
    "#include <iostream>\n\nint main() {\n  // Tulis programmu di sini.\n\n  return 0;\n}\n",
};
function draftKey(editor, lang) {
  return ui`kodelab:code:${state.user.id}:${editor.enrollment?.id || "practice"}:${editor.stepId || editor.problem.id}:${lang}`;
}
function storedCode(editor, lang) {
  try {
    return sessionStorage.getItem(draftKey(editor, lang)) ?? starters[lang];
  } catch {
    return starters[lang];
  }
}
function compilerKey(editor) {
  return draftKey(editor, "compiler");
}
function syncCompiler(loadDraft = false) {
  const editor = state.editor,
    selector = $("#code-language");
  if (!editor || !selector || !editor.permitted.includes(selector.value))
    return;
  editor.lang = selector.value;
  try {
    sessionStorage.setItem(compilerKey(editor), editor.lang);
  } catch {}
  $("#editor-filename").textContent =
    editor.lang === "c17" ? "main.c" : "main.cpp";
  if (loadDraft) $("#code-editor").value = storedCode(editor, editor.lang);
}
function persistCode() {
  const e = state.editor,
    el = $("#code-editor");
  if (!e || !el) return;
  syncCompiler();
  try {
    sessionStorage.setItem(draftKey(e, e.lang), el.value);
  } catch {}
  updateLines();
}
function updateLines() {
  const el = $("#code-editor"),
    gutter = $("#line-numbers");
  if (el && gutter) {
    gutter.textContent = Array.from(
      { length: el.value.split("\n").length },
      (_, i) => i + 1,
    ).join("\n");
    gutter.scrollTop = el.scrollTop;
  }
}
function codeWorkspace(problem, enrollment = null, stepId = null) {
  const permitted = enrollment
    ? problem.languages.filter((x) => enrollment.languages.includes(x))
    : problem.languages;
  state.editor = { problem, enrollment, stepId, permitted };
  let lang = permitted[0];
  try {
    const saved = sessionStorage.getItem(compilerKey(state.editor));
    if (permitted.includes(saved)) lang = saved;
  } catch {}
  state.editor.lang = lang;
  const source = storedCode(state.editor, lang);
  return ui`<section class="workspace" aria-label="Editor kode"><div class="editor-toolbar"><span class="row">${icon("code")}<span id="editor-filename">${lang === "c17" ? "main.c" : "main.cpp"}</span></span><div class="row"><label for="code-language">Compiler</label><select id="code-language">${permitted.map((x) => ui`<option value="${x}" ${x === lang ? "selected" : ""}>${language(x)} · ${x === "c17" ? "GCC" : "G++"}</option>`).join("")}</select><button class="icon-button" data-action="reset-code" aria-label="Kembalikan kode awal">${icon("refresh")}</button></div></div><div class="editor-wrap"><div id="line-numbers" class="line-numbers" aria-hidden="true">${source
    .split("\n")
    .map((_, i) => i + 1)
    .join(
      "\n",
    )}</div><label class="visually-hidden" for="code-editor">Kode program</label><textarea id="code-editor" class="code-editor" spellcheck="false" autocapitalize="off" autocomplete="off" wrap="off">${esc(source)}</textarea></div><div class="io-panel"><label for="custom-input">Input percobaan</label><textarea id="custom-input" rows="2" spellcheck="false" placeholder="Masukkan input untuk mencoba program…">${esc(problem.samples[0]?.input || "")}</textarea></div><div class="editor-footer"><small>Tab untuk indentasi · Ctrl / ⌘ + Enter untuk menjalankan<br>Draft kode tersimpan sementara di tab ini.</small><div class="row"><button class="btn" ${enrollment?.course_archived ? "disabled" : ""} data-action="run-code">${icon("play")}Jalankan</button><button class="btn primary" ${enrollment?.course_archived ? "disabled" : ""} data-action="submit-code">${icon("check")}Kirim jawaban</button></div></div></section><div id="judge-result" aria-live="polite"></div>`;
}
async function stepPage(enrollmentId, stepId, ticket) {
  const data = await api(ui`/enrollments/${enrollmentId}/steps/${stepId}`);
  if (ticket !== state.route) return;
  const e = data.enrollment,
    step = e.steps.find((s) => s.id === stepId),
    index = e.steps.indexOf(step),
    content = data.content;
  document.title = ui`${step.title} — KodeLab`;
  const next = e.steps.slice(index + 1).find((s) => !s.locked);
  root.innerHTML = shell(
    ui`<div class="breadcrumb"><a href="#/classes">Kelas</a>${icon("chevron")}<a href="#/classes/${e.course_id}">${esc(e.course_title)}</a>${icon("chevron")}<a href="#/learning/${e.id}">${esc(e.title)}</a>${icon("chevron")}<span>Langkah ${index + 1}</span></div><div class="learn-layout"><aside class="learn-outline"><div class="eyebrow">JALUR BELAJARMU</div><h3>${esc(e.title)}</h3>${progress(e.progress)}<p class="subtle-note">Lama pengerjaan: ${learningTime(e)}</p><div>${stepRows(e, true, stepId)}</div></aside><section class="learn-content"><div class="lesson-heading"><div class="row spread"><div class="row">${badge(ui`LANGKAH ${String(index + 1).padStart(2, "0")}`)}${badge(step.kind === "reading" ? tr("MATERI") : tr("LATIHAN KODE"), "solid")}</div>${step.completed ? badge(tr("SELESAI"), "active") : ""}</div><h1>${esc(step.title)}</h1></div>${step.kind === "reading" ? ui`<article class="prose">${content.body_html}</article><div class="lesson-footer"><small>Konfirmasi setelah kamu selesai membaca.<br>Pemahamanmu akan diuji pada latihan berikutnya.</small><button class="btn primary" ${e.course_archived ? "disabled" : ""} data-action="complete-reading" data-enrollment="${e.id}" data-id="${stepId}">${icon("check")}${step.completed ? tr("Lanjutkan belajar") : tr("Selesai membaca")}</button></div>` : ui`<article class="prose">${content.statement_html}</article><div class="row wrap">${badge(languages(content.languages), "solid")}<small>${content.limits.time_seconds} detik / kasus · ${content.limits.memory_mb} MiB</small></div>${content.samples.map((sample) => ui`<div class="sample-grid"><div class="sample"><small>CONTOH INPUT</small><pre>${esc(sample.input)}</pre></div><div class="sample"><small>CONTOH OUTPUT</small><pre>${esc(sample.expected)}</pre></div></div>`).join("")}${codeWorkspace(content, e, stepId)}<div class="lesson-footer"><a class="btn" href="#/learning/${e.id}">${icon("back")}Lihat jalur</a><a id="next-step" class="btn ${next ? "" : "visually-hidden"}" href="${next ? ui`#/learn/${e.id}/${next.id}` : "#"}">Langkah berikutnya ${icon("arrow")}</a></div>`}</section></div>`,
    "classes",
  );
}
function leaderboardRules(inClass = false) {
  return ui`${inClass ? tr("Nilai kelas adalah jumlah nilai learning path dalam kelas ini.") : tr("Nilai keseluruhan adalah jumlah nilai learning path pada kelas yang dapat kamu akses.")} Setiap jalur menyumbang maksimal 100 poin dari latihan wajib Accepted dan dihitung sekali sesuai versi enrollment. Jalur arsip dan jalur tanpa latihan wajib tidak menambah nilai. Nilai sama diurutkan berdasarkan total waktu penyelesaian tercepat. Durasi final tersedia setelah seluruh jalur yang menyumbang nilai selesai; peserta yang belum selesai berada setelah peserta dengan durasi final pada nilai yang sama. Nilai dan durasi identik berbagi peringkat. Waktu termasuk jeda sejak enrollment.`;
}
function leaderboardTable(board) {
  return board.rows.length
    ? ui`<div class="table-wrap"><table aria-label="Leaderboard"><thead><tr><th scope="col">Peringkat</th><th scope="col">Peserta</th><th scope="col">Nilai total</th><th scope="col">Jalur selesai</th><th scope="col">Waktu penyelesaian</th></tr></thead><tbody>${board.rows.map((r) => ui`<tr ${r.user_id === state.user.id ? 'class="leaderboard-self" aria-current="true"' : ""}><td><strong class="mono">#${r.rank}</strong></td><td><strong>${esc(r.full_name || r.username)}</strong> ${r.user_id === state.user.id ? badge(tr("KAMU"), "active") : ""}</td><td class="mono">${r.score}</td><td>${r.completed_paths}</td><td title="${r.completion_seconds == null ? tr("Belum selesai") : r.completion_seconds + tr(" detik")}">${esc(duration(r.completion_seconds))}</td></tr>`).join("")}</tbody></table></div>`
    : empty(
        tr("Belum ada peringkat"),
        tr(
          "Peringkat muncul setelah peserta mengikuti jalur dengan latihan wajib.",
        ),
        "",
        "trophy",
      );
}
async function leaderboardPage(ticket) {
  const board = await api("/leaderboards");
  if (ticket !== state.route) return;
  document.title = "Leaderboard — KodeLab";
  root.innerHTML = shell(
    ui`${pageHead(tr("KEMAJUAN BERSAMA"), tr("Leaderboard keseluruhan"), tr("Akumulasi nilai dari kelas yang dapat kamu akses."))}<div class="toolbar">${badge(ui`${board.rows.length} PESERTA`)}</div><div class="panel"><p class="subtle-note">${leaderboardRules()} Kelas arsip tidak masuk peringkat keseluruhan.</p></div>${leaderboardTable(board)}`,
    "leaderboard",
  );
}
async function historyPage(ticket) {
  const rows = await api("/submissions");
  if (ticket !== state.route) return;
  document.title = tr("Riwayat kode — KodeLab");
  root.innerHTML = shell(
    ui`${pageHead(tr("CATATAN PERCOBAANMU"), tr("Setiap percobaan berarti."), tr("Tinjau kode, hasil pengujian, dan proses belajarmu. Menampilkan hingga 100 kiriman terbaru."))}<div class="table-wrap"><table><thead><tr><th scope="col">Waktu</th><th scope="col">Jenis</th><th scope="col">Bahasa</th><th scope="col">Hasil</th><th scope="col">Nilai</th><th scope="col"></th></tr></thead><tbody>${rows.map((r) => ui`<tr><td>${esc(date(r.created_at))}</td><td>${r.mode === "run" ? tr("Percobaan") : tr("Jawaban")}</td><td class="mono">${language(r.language)}</td><td>${esc(verdicts[r.verdict] || { queued: tr("Mengantre"), running: tr("Diproses"), retry_pending: tr("Mencoba ulang"), system_error: tr("Gangguan layanan") }[r.state] || r.state)}</td><td>${r.score ?? "—"}</td><td><button class="btn small" data-action="submission-detail" data-id="${r.id}">Lihat</button></td></tr>`).join("")}</tbody></table></div>${rows.length ? "" : empty(tr("Belum ada percobaan"), tr("Mulai sebuah latihan untuk menulis kode pertamamu."), tr('<a class="btn primary" href="#/classes">Jelajahi kelas</a>'))}`,
    "history",
  );
}
async function profilePage(ticket) {
  const user = await api("/auth/me");
  if (ticket !== state.route) return;
  state.user = user;
  document.title = tr("Profil — KodeLab");
  root.innerHTML = shell(
    ui`${pageHead(tr("AKUN PRIBADI"), tr("Profil pengguna"), tr("Kelola nama lengkap, email, dan keamanan akunmu."))}<section class="panel"><h2>Informasi profil</h2><form data-form="profile" class="form-stack"><div class="field"><label for="profile-username">Username login</label><input id="profile-username" value="${esc(user.username)}" readonly><small>Username login tetap. Nama lengkap digunakan sebagai nama tampilan.</small></div><div class="field"><label for="profile-name">Nama lengkap</label><input id="profile-name" name="full_name" value="${esc(user.full_name)}" maxlength="120" required autocomplete="name"></div><div class="field"><label for="profile-email">Email</label><input id="profile-email" type="email" name="email" value="${esc(user.email || "")}" maxlength="254" required autocomplete="email"></div><div class="form-error" role="alert"></div><button class="btn primary" type="submit">Simpan profil</button></form></section><section class="panel embedded-leaderboard"><h2>Ubah password</h2><form data-form="password" class="form-stack"><div class="field"><label for="current-password">Password saat ini</label><input id="current-password" type="password" name="current_password" required autocomplete="current-password" maxlength="128"></div><div class="field"><label for="new-password">Password baru</label><input id="new-password" type="password" name="new_password" required autocomplete="new-password" minlength="15" maxlength="128"></div><div class="field"><label for="confirm-password">Konfirmasi password baru</label><input id="confirm-password" type="password" name="confirmation" required autocomplete="new-password" minlength="15" maxlength="128"></div><p class="subtle-note">Minimal 15 karakter. Semua sesi akan dicabut setelah password diubah; masuk kembali dengan password baru.</p><div class="form-error" role="alert"></div><button class="btn primary" type="submit">Ubah password</button></form></section>`,
    "profile",
  );
}
async function sendCode(mode) {
  const editor = state.editor,
    code = $("#code-editor");
  if (!editor || !code) return;
  if (editor.enrollment?.course_archived) {
    toast(tr("Kelas diarsipkan. Pengerjaan baru dinonaktifkan."));
    return;
  }
  const ticket = state.route,
    panel = $("#judge-result");
  persistCode();
  const controls = [
    $('[data-action="run-code"]'),
    $('[data-action="submit-code"]'),
  ];
  if (controls.some((b) => b.disabled)) return;
  controls.forEach((b) => (b.disabled = true));
  const body = {
    problem_version_id: editor.problem.id,
    language: editor.lang,
    source: code.value,
    ...(mode === "run" ? { input: $("#custom-input").value } : {}),
    ...(editor.enrollment
      ? { enrollment_id: editor.enrollment.id, path_step_id: editor.stepId }
      : {}),
  };
  try {
    let row = await api(mode === "run" ? "/runs" : "/submissions", {
      method: "POST",
      body,
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    panel.innerHTML = renderResult(row);
    const deadline = Date.now() + 210000;
    while (
      !["completed", "system_error"].includes(row.state) &&
      Date.now() < deadline
    ) {
      await new Promise((r) => setTimeout(r, 1200));
      if (ticket !== state.route) return;
      row = await api(ui`/submissions/${row.id}`);
      if (ticket !== state.route) return;
      panel.innerHTML = renderResult(row);
    }
    if (!["completed", "system_error"].includes(row.state))
      panel.innerHTML += ui`<p class="subtle-note">Pekerjaan masih diproses. Kamu dapat memeriksanya di <a href="#/history">Riwayat kode</a>.</p>`;
    if (row.verdict === "ACCEPTED" && editor.enrollment) {
      const updated = await api(ui`/enrollments/${editor.enrollment.id}`);
      if (ticket !== state.route) return;
      editor.enrollment = updated;
      const outline = $(".learn-outline");
      if (outline)
        outline.innerHTML = ui`<div class="eyebrow">JALUR BELAJARMU</div><h3>${esc(updated.title)}</h3>${progress(updated.progress)}<p class="subtle-note">Lama pengerjaan: ${learningTime(updated)}</p><div>${stepRows(updated, true, editor.stepId)}</div>`;
      const next = updated.steps
        .slice(updated.steps.findIndex((s) => s.id === editor.stepId) + 1)
        .find((s) => !s.locked);
      if (next) {
        const link = $("#next-step");
        link.classList.remove("visually-hidden");
        link.href = ui`#/learn/${updated.id}/${next.id}`;
      }
      toast(
        updated.complete
          ? tr("Seluruh langkah wajib selesai. Progres sudah tersimpan.")
          : tr("Jawaban benar. Langkah berikutnya sudah terbuka."),
      );
    }
  } catch (error) {
    if (ticket === state.route)
      panel.innerHTML = ui`<div class="result-box" role="alert">${esc(error.message)}</div>`;
  } finally {
    if (ticket === state.route) controls.forEach((b) => (b.disabled = false));
  }
}
async function render() {
  const ticket = ++state.route;
  state.editor = null;
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const route = parts[0] || "dashboard";
  if (!state.user) {
    authPage(route === "register" ? "register" : "login");
    return;
  }
  if (["login", "register"].includes(route)) {
    go("/dashboard");
    return;
  }
  const section = ["course", "path-progress", "participant-work"].includes(route)
    ? "studio"
    : ["learning", "learn", "classes", "catalog"].includes(route)
    ? "classes"
    : route;
  root.innerHTML = shell(
    '<div class="loading-state"><span class="spinner"></span>Memuat ruang belajarmu…</div>',
    section,
  );
  try {
    if (route === "dashboard") await dashboard(ticket);
    else if (route === "classes") {
      if (parts[1] === "archive" && state.user.role === "student")
        go("/classes");
      else if (parts[1] === "archive") await classesPage(ticket, true, Number(parts[2]) || 0);
      else if (parts[1] === "page") await classesPage(ticket, false, Number(parts[2]) || 0);
      else if (parts[1]) await classPage(parts[1], ticket);
      else await classesPage(ticket);
    } else if (route === "catalog") go("/classes");
    else if (route === "learning") await learningPage(parts[1], ticket);
    else if (route === "learn") await stepPage(parts[1], parts[2], ticket);
    else if (route === "leaderboard") await leaderboardPage(ticket);
    else if (route === "practice") go("/classes");
    else if (route === "history") await historyPage(ticket);
    else if (route === "profile") await profilePage(ticket);
    else if (
      [
        "studio",
        "course",
        "path-progress",
        "participant-work",
        "lesson-editor",
        "problem-editor",
        "path-editor",
        "admin",
      ].includes(route)
    ) {
      if (!isTeacher()) throw new Error(tr("Halaman ini khusus pengajar."));
      const html = await renderStudio(parts, ticket);
      if (ticket === state.route)
        root.innerHTML = shell(html, route === "admin" ? (parts[1] === "plugins" ? "admin/plugins" : "admin") : "studio");
    } else
      root.innerHTML = shell(
        empty(
          tr("Halaman tidak ditemukan"),
          tr("Kembali ke ruang belajar untuk melanjutkan."),
          tr('<a class="btn primary" href="#/dashboard">Ke ringkasan</a>'),
        ),
      );
    if (ticket === state.route)
      window.scrollTo({ top: 0, behavior: "instant" });
  } catch (error) {
    if (ticket === state.route && state.user)
      root.innerHTML = shell(
        ui`<div class="page-error"><h2>Halaman belum dapat dibuka.</h2><p class="muted">${esc(error.message)}</p><div class="row wrap"><button class="btn" data-action="refresh">${icon("refresh")}Coba lagi</button><a class="btn primary" href="#/dashboard">Ke ringkasan</a></div></div>`,
        section,
      );
  }
}
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.dataset.form) return;
  event.preventDefault();
  const data = new FormData(form);
  const kind = form.dataset.form;
  if (kind === "profile") {
    await formTask(form, async () => {
      state.user = await api("/auth/profile", {
        method: "PATCH",
        body: {
          full_name: String(data.get("full_name")),
          email: String(data.get("email")),
        },
      });
      toast(tr("Profil diperbarui."));
      refresh();
    });
    return;
  }
  if (kind === "password") {
    await formTask(form, async () => {
      if (data.get("new_password") !== data.get("confirmation"))
        throw new Error(tr("Konfirmasi password belum sesuai."));
      await api("/auth/password", {
        method: "POST",
        body: {
          current_password: String(data.get("current_password")),
          new_password: String(data.get("new_password")),
        },
      });
      state.user = null;
      for (const key of Object.keys(sessionStorage))
        if (key.startsWith("kodelab:")) sessionStorage.removeItem(key);
      go("/login");
      toast(tr("Password diubah. Silakan masuk kembali."));
    });
    return;
  }
  if (kind === "join-class") {
    await formTask(form, async () => {
      const result = await api("/courses/join", {
        method: "POST",
        body: { code: String(data.get("code")) },
      });
      closeModal();
      toast(tr("Berhasil bergabung ke kelas."));
      go(ui`/classes/${result.course_id}`);
    });
    return;
  }
  if (["login", "register"].includes(kind)) {
    await formTask(form, async () => {
      const credentials = {
        username: String(data.get("username")).trim().toLowerCase(),
        password: String(data.get("password")),
      };
      if (kind === "register")
        await api("/auth/register", {
          method: "POST",
          body: {
            ...credentials,
            full_name: String(data.get("full_name")),
            email: String(data.get("email")),
          },
        });
      const result = await api("/auth/login", {
        method: "POST",
        body: credentials,
      });
      state.user = result.user;
      go("/dashboard");
    });
    return;
  }
  await studioSubmit(form, data, event.submitter?.value || "save");
});
document.addEventListener("click", async (event) => {
  if (
    event.target.closest("#main-sidebar a[href]") &&
    $("#main-sidebar.is-open")
  )
    toggleSidebar(false);
  const el = event.target.closest("[data-action]");
  if (!el || el.disabled) return;
  const action = el.dataset.action;
  try {
    if (action === "join-class") {
      modal(
        tr("Gabung ke kelas privat"),
        ui`<form data-form="join-class" class="form-stack"><div class="field"><label for="join-code">Kode undangan 6 digit</label><input id="join-code" name="code" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required autocomplete="off" placeholder="Contoh: 012345"></div><p class="help">Minta kode aktif kepada pengajar. Bergabung ke kelas tidak memulai penghitung waktu learning path.</p>${formFooter(tr("Gabung kelas"))}</form>`,
      );
    } else if (action === "open-sidebar") toggleSidebar(true);
    else if (action === "close-sidebar") toggleSidebar(false);
    else if (action === "close-modal") closeModal();
    else if (action === "refresh") refresh();
    else if (action === "logout") {
      await api("/auth/logout", { method: "POST" });
      state.user = null;
      try {
        for (const key of Object.keys(sessionStorage))
          if (key.startsWith("kodelab:")) sessionStorage.removeItem(key);
      } catch {}
      closeModal();
      go("/login");
      render();
    } else if (action === "profile") {
      go("/profile");
    } else if (action === "enroll-path") {
      el.disabled = true;
      const enrollment = await api(ui`/paths/${el.dataset.id}/enroll`, {
        method: "POST",
      });
      go(ui`/learning/${enrollment.id}`);
    } else if (action === "open-step")
      go(ui`/learn/${el.dataset.enrollment}/${el.dataset.id}`);
    else if (action === "complete-reading") {
      el.disabled = true;
      const e = await api(
        ui`/enrollments/${el.dataset.enrollment}/steps/${el.dataset.id}/complete`,
        { method: "POST" },
      );
      if (e.next_step_id) go(ui`/learn/${e.id}/${e.next_step_id}`);
      else go(ui`/learning/${e.id}`);
    } else if (action === "run-code" || action === "submit-code")
      await sendCode(action === "run-code" ? "run" : "judge");
    else if (action === "reset-code") {
      const code = $("#code-editor");
      code.value = starters[state.editor.lang];
      persistCode();
    } else if (action === "submission-detail") {
      const r = await api(ui`/submissions/${el.dataset.id}`);
      modal(
        tr("Detail percobaan"),
        ui`<div class="row spread">${badge(language(r.language), "solid")}<small>${esc(date(r.created_at))}</small></div><pre class="code-detail">${esc(r.source)}</pre>${renderResult(r)}<div class="modal-footer"><button class="btn" data-action="close-modal">Tutup</button></div>`,
      );
    } else await studioAction(action, el);
  } catch (error) {
    el.disabled = false;
    toast(error.message);
  }
});
document.addEventListener("input", (event) => {
  if (event.target.id === "code-editor") persistCode();
  if (event.target.id === "class-search") {
    $("#class-cards").innerHTML =
      state.courseCatalog
        .filter((c) =>
          c.title.toLowerCase().includes(event.target.value.toLowerCase()),
        )
        .map(courseCard)
        .join("") ||
      tr('<p class="muted">Tidak ada kelas yang sesuai pencarian.</p>');
  }
  studioChange(event);
});
document.addEventListener("change", (event) => {
  if (event.target.id === "ui-locale") {
    persistCode();
    setLocale(event.target.value);
    return;
  }
  if (event.target.id === "code-language" && state.editor) {
    syncCompiler(true);
    updateLines();
  }
  studioChange(event);
});
document.addEventListener("keydown", (event) => {
  if (event.target.id !== "code-editor") return;
  const el = event.target;
  if (event.key === "Tab") {
    event.preventDefault();
    el.setRangeText("  ", el.selectionStart, el.selectionEnd, "end");
    persistCode();
  }
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    sendCode("run");
  }
});
document.addEventListener(
  "scroll",
  (event) => {
    if (event.target?.id === "code-editor") {
      $("#line-numbers").scrollTop = event.target.scrollTop;
    }
  },
  true,
);
window.addEventListener("hashchange", () => {
  closeModal();
  render();
});
window.addEventListener("kode:refresh", render);
window.addEventListener("kode:expired", () => {
  closeModal();
  go("/login");
  render();
  toast(tr("Sesi berakhir. Silakan masuk kembali."));
});
try {
  state.user = await api("/auth/me");
} catch {}
await render();
