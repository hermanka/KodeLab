import { ui, tr, localeControl, getLocale, setLocale } from "./i18n.js";
import {pluginsPage, pluginAction, pluginSubmit} from "./plugins.js";
import {
  state,
  $,
  esc,
  icon,
  badge,
  progress,
  duration,
  courseStatusTabs,
  pagination as reportPaging,
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
  verdicts,
  renderResult,
} from "./core.js";

let edit = null,
  builder = [],
  targets = { lessons: [], problems: [] },
  courseCache = [];
const head = (label, title, text, action = "") =>
  ui`<div class="page-head"><div><div class="eyebrow">${esc(label)}</div><h1>${esc(title)}</h1><p>${esc(text)}</p></div>${action}</div>`;
const breadcrumb = (cid) =>
  ui`<div class="breadcrumb"><a href="#/studio">Studio pengajar</a>${icon("chevron")}<a href="#/course/${cid}/materials">Konten kelas</a></div>`;
const statusLabel = (s) =>
  ({
    draft: "DRAFT",
    validating: tr("MENGUJI KUNCI"),
    published: tr("TERBIT"),
    archived: tr("ARSIP"),
  })[s] || s;
const btn = (text, action, id, kind = "", cls = "") =>
  ui`<button type="button" class="btn small ${cls}" data-action="${action}" data-id="${esc(id)}" data-kind="${kind}" ${text.includes("<svg") ? ui`aria-label="${{ "archive-content": tr("Arsipkan konten"), "step-up": tr("Naikkan langkah"), "step-down": tr("Turunkan langkah"), "step-remove": tr("Hapus langkah") }[action] || tr("Tindakan")}"` : ""}>${text}</button>`;
function courseLifecycle(course) {
  return course.can_delete
    ? ui`<div class="row wrap course-lifecycle">${btn(course.archived ? tr("Pulihkan kelas") : tr("Arsipkan kelas"), course.archived ? "restore-course" : "archive-course", course.id)}${btn(tr("Hapus kelas"), "delete-course", course.id, "", "danger")}</div>`
    : "";
}
function contentTable(rows, kind, cid, archived = false) {
  if (archived) rows = rows.map((row) => ({ ...row, archived: true }));
  if (!rows.length && archived)
    return empty(
      tr("Belum ada konten"),
      tr("Kelas ini diarsipkan dan hanya dapat ditinjau."),
    );
  if (!rows.length)
    return empty(
      kind === "lessons"
        ? tr("Materi pertama dimulai di sini.")
        : kind === "problems"
          ? tr("Siapkan latihan untuk peserta.")
          : tr("Susun perjalanan belajarnya."),
      kind === "paths"
        ? tr(
            "Gabungkan materi dan soal yang sudah terbit menjadi jalur belajar.",
          )
        : tr("Buat draft, tinjau isinya, kemudian terbitkan saat sudah siap."),
      ui`<a class="btn primary" href="#/${kind === "lessons" ? "lesson" : kind === "problems" ? "problem" : "path"}-editor/new/${cid}">${icon("plus")}Buat ${kind === "lessons" ? tr("materi") : kind === "problems" ? tr("soal") : tr("jalur")}</a>`,
    );
  return ui`<div class="table-wrap"><table><thead><tr><th scope="col">Judul</th><th scope="col">Versi</th><th scope="col">Status</th><th scope="col">Tindakan</th></tr></thead><tbody>${rows.map((row) => ui`<tr><td><strong>${esc(row.title)}</strong></td><td class="mono">v${row.revision}</td><td>${badge(row.archived ? tr("ARSIP") : statusLabel(row.status), row.status === "published" && !row.archived ? "active" : "")}</td><td><div class="table-actions"><a class="btn small" href="#/${kind === "lessons" ? "lesson" : kind === "problems" ? "problem" : "path"}-editor/${row.id}/${cid}">${row.status === "draft" && !row.archived ? "Edit" : tr("Tinjau")}</a>${row.status === "published" && !row.archived ? btn(tr("Revisi"), "revise-content", row.lesson_id || row.problem_id || row.path_id, kind) : ""}${kind === "paths" && row.status === "published" ? ui`<a class="btn small" href="#/path-progress/${row.path_id}">Hasil peserta</a>` : ""}${!row.archived ? btn(icon("archive"), "archive-content", row.lesson_id || row.problem_id || row.path_id, kind) : ""}</div></td></tr>`).join("")}</tbody></table></div>`;
}
async function studioHome(archived = false, offset = 0, ticket) {
  const courses = await api(ui`/courses?status=${archived ? "archived" : "active"}&managed=true&offset=${offset}`);
  if (ticket !== state.route) return "";
  courseCache = courses;
  return ui`${head(tr("STUDIO PENGAJAR"), tr("Rancang ruang belajarnya."), tr("Kelola materi, latihan, dan jalur belajar untuk setiap kelas."), '<button class="btn primary" data-action="new-course">' + icon("plus") + tr("Buat kelas</button>"))}${courseStatusTabs("studio", archived)}<div class="cards">${courseCache.map((c) => ui`<article class="path-card course-card" data-course-id="${esc(c.id)}"><div class="row spread">${badge(c.archived ? tr("KELAS DIARSIPKAN") : c.is_public ? tr("KELAS PUBLIK") : tr("KELAS PRIVAT"), "solid")}${icon(c.is_public ? "globe" : "lock")}</div><h3>${esc(c.title)}</h3><p>${esc(c.description || (c.archived ? tr("Konten dan progres tersimpan. Pulihkan kelas untuk melanjutkan pembelajaran.") : c.is_public ? tr("Peserta dapat bergabung melalui jalur belajar yang terbit.") : tr("Kelas privat untuk anggota yang ditugaskan atau memiliki kode undangan.")))}</p><div class="card-bottom"><a class="btn full" href="#/course/${c.id}/materials">${c.archived ? tr("Tinjau kelas") : tr("Kelola kelas")} ${icon("arrow")}</a>${courseLifecycle(c)}</div></article>`).join("")}</div>${courseCache.length ? "" : archived ? empty(tr("Belum ada kelas arsip"), tr("Kelas yang diarsipkan akan muncul di sini dan dapat dipulihkan atau dihapus.")) : empty(tr("Bangun kelas pertamamu."), tr("Mulai dengan sebuah kelas, lalu tambahkan materi dan latihan."), tr('<button class="btn primary" data-action="new-course">Buat kelas</button>'))}`;
}
async function coursePage(cid, tab = "materials", offset = 0, ticket) {
  if (tab === "submissions") { go(ui`/course/${cid}/progress`); return ""; }
  const [course, content, paths] = await Promise.all([
    api(ui`/courses/${cid}`),
    api(ui`/author/courses/${cid}/content?offset=${offset}`),
    api(ui`/author/courses/${cid}/paths?offset=${offset}`),
  ]);
  if (ticket !== state.route) return "";
  if (!course?.can_manage)
    throw new Error(tr("Kelas ini tidak dapat kamu kelola."));
  courseCache = [course];
  const tabs = [
    ["materials", tr("Materi")],
    ["problems", tr("Bank soal")],
    ["paths", "Learning path"],
    ["members", tr("Peserta")],
    ["progress", tr("Progres")],
    ...(course.can_delete ? [["settings", tr("Pengaturan")]] : []),
  ];
  const names = {
    materials: [tr("materi"), "lesson"],
    problems: [tr("soal"), "problem"],
    paths: [tr("jalur"), "path"],
  };
  let body = "",
    actions = "";
  if (names[tab]) {
    const [name, route] = names[tab];
    actions = ui`<a class="btn primary" href="#/${route}-editor/new/${cid}">${icon("plus")}Buat ${name}</a>`;
    body = contentTable(
      tab === "materials"
        ? content.lessons
        : tab === "problems"
          ? content.problems
          : paths,
      tab === "materials" ? "lessons" : tab,
      cid,
      course.archived,
    );
    body += reportPaging(ui`/course/${cid}/${tab}`, offset, (tab === "materials" ? content.lessons : tab === "problems" ? content.problems : paths).length);
  } else if (tab === "members") {
    const rows = await api(ui`/courses/${cid}/members?offset=${offset}`);
    const canAssign =
      !course.archived &&
      (state.user.role === "admin" || course.owner_id === state.user.id);
    actions = canAssign
      ? ui`<button class="btn primary" data-action="add-member" data-id="${cid}">${icon("plus")}Tambahkan anggota</button>`
      : "";
    body = rows.length
      ? ui`<div class="table-wrap"><table><thead><tr><th scope="col">Username</th><th scope="col">Peran di kelas</th><th scope="col"></th></tr></thead><tbody>${rows.map((row) => ui`<tr><td><strong>${esc(row.username)}</strong></td><td>${row.role === "teacher" ? tr("Pengajar") : tr("Peserta")}</td><td>${canAssign ? ui`<button class="btn small" data-action="remove-member" data-course="${cid}" data-id="${row.id}">Cabut akses</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`
      : empty(
          tr("Belum ada anggota tambahan."),
          tr(
            "Tambahkan peserta dengan username akun mereka. Pemilik kelas selalu memiliki akses.",
          ),
        );
    body += reportPaging(ui`/course/${cid}/members`, offset, rows.length);
  } else if (tab === "progress") {
    const rows = await api(ui`/author/courses/${cid}/progress?offset=${offset}`);
    body = ui`<p class="subtle-note">Progres kelas adalah rata-rata progres langkah wajib seluruh learning path terbit yang aktif. Path yang belum dimulai bernilai 0%.</p>` + (rows.length
      ? ui`<div class="table-wrap"><table><thead><tr><th scope="col">Peserta</th><th scope="col">Path selesai</th><th scope="col">Progres</th><th scope="col">Total lama pengerjaan</th></tr></thead><tbody>${rows.map((r) => ui`<tr><td><strong>${esc(r.full_name || r.username)}</strong><small class="muted"> @${esc(r.username)}</small></td><td>${r.completed_paths}/${r.total_paths}</td><td>${r.progress}% ${progress(r.progress)}</td><td>${duration(r.elapsed_seconds)}</td></tr>`).join("")}</tbody></table></div>`
      : empty(tr("Belum ada peserta."), tr("Peserta kelas dan riwayat belajarnya akan muncul di sini."))) + reportPaging(ui`/course/${cid}/progress`, offset, rows.length);
  } else if (tab === "settings") {
    const settings = await api(ui`/courses/${cid}/settings`);
    body = ui`<section class="panel"><h2>Pengaturan kelas</h2><form data-form="course-settings" data-id="${cid}" data-revision="${settings.edit_revision}" class="form-stack"><fieldset ${settings.archived ? "disabled" : ""}><div class="field"><label for="settings-title">Nama kelas</label><input id="settings-title" name="title" required maxlength="200" value="${esc(settings.title)}"></div><div class="field"><label for="settings-description">Deskripsi kelas</label><textarea id="settings-description" name="description" maxlength="8000" rows="4">${esc(settings.description)}</textarea></div><label class="check"><input type="checkbox" name="is_public" ${settings.is_public ? "checked" : ""}>Kelas publik · peserta dapat bergabung sendiri</label><p class="help">Kelas privat hanya dapat diakses anggota yang ditugaskan atau bergabung dengan kode undangan. Perubahan akses tidak menghapus anggota atau progres lama. Mengubah ke publik menonaktifkan kode undangan.</p><div class="form-error" role="alert"></div><button class="btn primary" type="submit">Simpan pengaturan</button></fieldset></form></section><section class="panel embedded-leaderboard"><h2>Kode undangan</h2><p>Kode enam digit berlaku 24 jam dan memberikan keanggotaan peserta, tanpa memulai learning path. Kode aktif ditampilkan di halaman ini untuk pemilik kelas dan admin.</p>${settings.is_public ? tr('<p class="subtle-note">Ubah dan simpan kelas sebagai privat untuk membuat kode undangan.</p>') : ui`<p class="subtle-note">${settings.invite_enabled ? ui`Aktif hingga ${esc(date(settings.invite_expires_at))}.` : tr("Tidak ada kode undangan aktif.")}</p>${settings.code ? ui`<output id="settings-invite-code" class="mono invite-code">${esc(settings.code)}</output>` : settings.invite_enabled ? tr('<p class="subtle-note">Kode lama tidak dapat ditampilkan. Ganti kode undangan untuk menampilkan kode baru.</p>') : ""}<div class="row wrap"><button class="btn" data-action="rotate-invitation" data-id="${cid}" ${settings.archived ? "disabled" : ""}>${settings.invite_enabled ? tr("Ganti kode undangan") : tr("Buat kode undangan")}</button>${settings.invite_enabled ? ui`<button class="btn" data-action="revoke-invitation" data-id="${cid}" ${settings.archived ? "disabled" : ""}>Nonaktifkan kode</button>` : ""}</div>`}</section>`;
  }
  const lifecycle = courseLifecycle(course);
  return ui`${breadcrumb(cid)}${head(tr("KELOLA KELAS"), course.title, course.description || tr("Materi, latihan, dan perkembangan peserta dalam satu tempat."), course.archived ? "" : actions)}${course.archived ? tr('<p class="inline-note">KELAS DIARSIPKAN · Konten dan progres tersimpan. Pulihkan kelas untuk melanjutkan kegiatan belajar.</p>') : ""}${lifecycle}<div class="tabs">${tabs.map(([id, text]) => ui`<a class="btn ghost ${id === tab ? "active" : ""}" href="#/course/${cid}/${id}" ${id === tab ? 'aria-current="page"' : ""}>${text}</a>`).join("")}</div>${body}`;
}
const reportOffset = (value) => /^\d+$/.test(value || "") ? Number(value) : 0;
async function pathReport(pathId, offset) {
  const r = await api(ui`/author/paths/${pathId}/progress?offset=${offset}`);
  return ui`${breadcrumb(r.course_id)}${head(tr("HASIL PESERTA"), r.title, r.course_title)}<a class="btn" href="#/course/${r.course_id}/paths">Kembali ke learning path</a><p class="subtle-note">Pengerjaan mengikuti versi learning path saat peserta mulai belajar.</p>${r.participants.length ? ui`<div class="table-wrap"><table><thead><tr><th scope="col">Peserta</th><th scope="col">Status</th><th scope="col">Versi</th><th scope="col">Progres</th><th scope="col">Lama pengerjaan</th><th scope="col"></th></tr></thead><tbody>${r.participants.map(p => ui`<tr><td><strong>${esc(p.full_name || p.username)}</strong><small class="muted"> @${esc(p.username)}</small></td><td>${p.enrollment ? p.enrollment.complete ? tr("Selesai") : tr("Sedang dikerjakan") : tr("Belum dimulai")}</td><td>${p.enrollment ? ui`v${p.enrollment.revision}` : "—"}</td><td>${p.enrollment?.progress ?? 0}% ${progress(p.enrollment?.progress)}</td><td>${p.enrollment ? learningTime(p.enrollment) : "—"}</td><td><a class="btn small" href="#/participant-work/${pathId}/${p.user_id}">Detail pengerjaan</a></td></tr>`).join("")}</tbody></table></div>` : empty(tr("Belum ada peserta."), tr("Peserta kelas dan riwayat belajarnya akan muncul di sini."))}${reportPaging(ui`/path-progress/${pathId}`, offset, r.participants.length)}`;
}
async function participantReport(pathId, userId, offset) {
  const r = await api(ui`/author/paths/${pathId}/participants/${userId}?offset=${offset}`);
  const p = r.participant, e = r.enrollment;
  return ui`${breadcrumb(r.course_id)}${head(tr("DETAIL PENGERJAAN"), p.full_name || p.username, ui`${r.title} · @${p.username}`)}<a class="btn" href="#/path-progress/${pathId}">Kembali ke daftar peserta</a>${e ? ui`<section class="panel embedded-leaderboard"><h2>${esc(e.title)} · v${e.revision}</h2><p>${e.progress ?? 0}% · ${e.completed_count}/${e.required_count} langkah wajib · ${learningTime(e)}</p>${progress(e.progress)}<div class="table-wrap"><table><thead><tr><th scope="col">Langkah</th><th scope="col">Jenis</th><th scope="col">Status</th></tr></thead><tbody>${e.steps.map(s => ui`<tr><td>${esc(s.title)} ${s.required ? "" : badge(tr("Opsional"))}</td><td>${s.kind === "reading" ? tr("Materi") : tr("Latihan kode")}</td><td>${s.completed ? tr("Selesai") : tr("Belum selesai")}</td></tr>`).join("")}</tbody></table></div></section><section class="panel embedded-leaderboard"><h2>Riwayat pengerjaan</h2>${r.submissions.length ? ui`<div class="table-wrap"><table><thead><tr><th scope="col">Waktu</th><th scope="col">Latihan</th><th scope="col">Bahasa</th><th scope="col">Jenis</th><th scope="col">Hasil</th><th scope="col">Nilai</th><th scope="col"></th></tr></thead><tbody>${r.submissions.map(s => ui`<tr><td>${esc(date(s.created_at))}</td><td>${esc(s.step_title)}</td><td>${language(s.language)}</td><td>${s.mode === "run" ? tr("Percobaan") : tr("Jawaban")}</td><td>${esc(verdicts[s.verdict] || s.state)}</td><td>${s.score ?? "—"}</td><td><button class="btn small" data-action="review-code" data-id="${s.id}" data-participant="${esc(p.full_name || p.username)}" data-exercise="${esc(s.step_title)}" data-archived="${r.archived}">Lihat kode</button></td></tr>`).join("")}</tbody></table></div>` : ui`<p>Belum ada kiriman.</p>`}${reportPaging(ui`/participant-work/${pathId}/${userId}`, offset, r.submissions.length)}</section>` : empty(tr("Belum dimulai"), tr("Peserta ini belum memulai learning path."))}`;
}
function editorAside(kind, model, cid, validation) {
  const isPublished = model.status === "published",
    isValidating = model.status === "validating",
    valid = validation?.state === "completed" && validation.valid;
  return ui`<aside class="editor-aside"><div class="panel"><div class="eyebrow">${isPublished ? tr("VERSI TERBIT") : tr("PUBLIKASI KONTEN")}</div>${badge(statusLabel(model.status || "draft"), isPublished ? "active" : "")}<p class="subtle-note">${model.course_archived ? tr("Kelas diarsipkan. Konten hanya dapat ditinjau sampai kelas dipulihkan.") : isPublished ? tr("Versi terbit tersimpan. Buat revisi untuk mengubahnya.") : kind === "problem" ? tr("Simpan draft dan uji kuncinya sebelum menerbitkan.") : kind === "path" ? tr("Pastikan urutan dan prasyarat sesuai tujuan belajarnya.") : tr("Tinjau materi sebelum membagikannya ke peserta.")}</p>${!model.archived && !isPublished && !isValidating ? ui`<button class="btn" type="submit" value="save">${icon("file")}Simpan draft</button>${kind === "problem" ? ui`<button class="btn" type="submit" value="validate">${icon("play")}Uji kunci</button>` : ""}<button class="btn primary" type="submit" value="publish" ${kind === "problem" && !valid ? "disabled" : ""}>${icon("check")}Terbitkan</button>` : ""}${isValidating ? '<div class="row"><span class="spinner"></span><small>Menguji seluruh bahasa…</small></div>' : ""}${isPublished && !model.archived ? ui`<button class="btn primary" type="button" data-action="revise-content" data-id="${model.lesson_id || model.problem_id || model.path_id}" data-kind="${kind === "lesson" ? "lessons" : kind === "problem" ? "problems" : "paths"}">${icon("edit")}Buat revisi baru</button>` : ""}<a class="btn" href="#/course/${cid}/${kind === "lesson" ? "materials" : kind === "problem" ? "problems" : "paths"}">Kembali ke kelas</a>${model.id ? ui`<small>Versi ${model.revision} · Revisi draft ${model.edit_revision}</small>` : ""}</div>${
    validation
      ? ui`<div class="result-box ${valid ? "success" : ""}"><div class="result-title">${icon(valid ? "check" : "code")}${valid ? tr("Kunci lolos pengujian") : validation.state === "completed" ? tr("Kunci belum lolos") : validation.state === "system_error" ? tr("Gangguan validasi") : tr("Validasi berlangsung")}</div>${Object.entries(
          validation.result || {},
        )
          .map(
            ([lang, result]) =>
              ui`<div class="status-line">${badge(language(lang), "solid")}<small>${esc(verdicts[result.verdict] || result.verdict)}</small></div>${result.compile_log ? ui`<pre>${esc(result.compile_log)}</pre>` : ""}${
                result.cases
                  ?.filter((c) => c.verdict !== "ACCEPTED")
                  .map(
                    (c) =>
                      ui`<small>${esc(verdicts[c.verdict] || c.verdict)}</small><pre>${esc(c.stdout || c.stderr || tr("(tidak ada output)"))}</pre>`,
                  )
                  .join("") || ""
              }`,
          )
          .join(
            "",
          )}<p class="subtle-note">Perubahan draft membatalkan hasil uji sebelumnya.</p></div>`
      : ""
  }</aside>`;
}
function caseRow(c, index) {
  return ui`<div class="case-row"><div class="row spread"><strong>Kasus uji ${index + 1}</strong><div class="row"><label class="check"><input type="checkbox" name="case-public-${index}" ${c.public ? "checked" : ""}>Contoh terbuka</label><button type="button" class="icon-button" data-action="remove-case" data-index="${index}" aria-label="Hapus kasus ${index + 1}">${icon("trash")}</button></div></div><div class="form-grid"><div class="field"><label for="case-input-${index}">Input</label><textarea id="case-input-${index}" name="case-input-${index}" spellcheck="false">${esc(c.input)}</textarea></div><div class="field"><label for="case-expected-${index}">Output yang diharapkan</label><textarea id="case-expected-${index}" name="case-expected-${index}" spellcheck="false">${esc(c.expected)}</textarea></div></div></div>`;
}
function getCases(form) {
  return [...form.querySelectorAll(".case-row")].map((_, i) => ({
    input: form.elements[ui`case-input-${i}`].value,
    expected: form.elements[ui`case-expected-${i}`].value,
    public: form.elements[ui`case-public-${i}`].checked,
  }));
}
function problemFields(model) {
  return ui`<div class="form-stack"><div class="field"><label for="content-title">Judul soal</label><input id="content-title" name="title" value="${esc(model.title)}" required maxlength="200" placeholder="Contoh: Jumlah dua bilangan"></div><div class="field"><label for="statement">Pernyataan soal</label><textarea id="statement" name="statement" required rows="6" placeholder="Jelaskan tugas, format input/output, dan batas nilai…">${esc(model.statement)}</textarea><span class="help">Markdown didukung. Hindari menaruh kunci privat di pernyataan soal.</span></div><div class="field"><span class="label">Bahasa yang diizinkan</span><div class="row"><label class="check"><input type="checkbox" name="lang" value="c17" ${(model.languages || []).includes("c17") ? "checked" : ""}>C17</label><label class="check"><input type="checkbox" name="lang" value="cpp17" ${(model.languages || []).includes("cpp17") ? "checked" : ""}>C++17</label></div></div><div class="field"><label for="problem-provider">Plugin penilaian</label><select id="problem-provider" name="provider" required>${!edit.providers[model.provider || "custom"] ? ui`<option value="${esc(model.provider)}" selected>${esc(model.provider)} (nonaktif)</option>` : ""}${Object.entries(edit.providers).filter(([id,p]) => p.implemented || id === model.provider).map(([id,p]) => ui`<option value="${esc(id)}" ${id === (model.provider || "custom") ? "selected" : ""}>${esc(p.name || id)}</option>`).join("")}</select><small>Versi plugin dikunci saat validasi kunci. Perubahan penilai memerlukan validasi ulang.</small>${model.provider_version ? ui`<small>Versi tervalidasi: ${esc(model.provider_version)}</small>` : ""}</div><div><div class="section-head"><h3 class="form-section-title">Kasus uji</h3><button class="btn small" type="button" data-action="add-case">${icon("plus")}Tambah kasus</button></div><div id="case-list">${model.cases.map(caseRow).join("")}</div><small>Minimal satu contoh terbuka. Gunakan kasus tersembunyi untuk menguji variasi jawaban.</small></div><div><h3 class="form-section-title">Solusi acuan · privat</h3>${["c17", "cpp17"].map((lang) => ui`<div class="field reference-field" data-language="${lang}" ${model.languages.includes(lang) ? "" : "hidden"}><label for="reference-${lang}">Solusi ${language(lang)}</label><textarea class="reference-source" id="reference-${lang}" name="reference-${lang}" spellcheck="false">${esc(model.reference_solutions?.[lang] || "")}</textarea></div>`).join("")}<small>Solusi ini diuji di sandbox dan tidak ditampilkan kepada peserta.</small></div><details><summary>Batas eksekusi</summary><div class="form-grid"><div class="field"><label for="limit-time">Waktu per kasus (detik)</label><input id="limit-time" type="number" name="limit-time" min="1" max="5" value="${model.limits.time_seconds}" required></div><div class="field"><label for="limit-memory">Memori (MiB)</label><input id="limit-memory" type="number" name="limit-memory" min="64" max="256" value="${model.limits.memory_mb}" required></div></div><p class="subtle-note">Penilai C/C++ · ${model.limits.compile_seconds} detik kompilasi · ${model.limits.output_bytes} byte output.</p></details></div>`;
}
function gatherProblem(form) {
  const langs = [...form.querySelectorAll('[name="lang"]:checked')].map(
    (x) => x.value,
  );
  return {
    title: form.elements.title.value,
    statement: form.elements.statement.value,
    languages: langs,
    provider: form.elements.provider.value,
    limits: {
      ...edit.model.limits,
      time_seconds: Number(form.elements["limit-time"].value),
      memory_mb: Number(form.elements["limit-memory"].value),
    },
    cases: getCases(form),
    reference_solutions: Object.fromEntries(
      langs.map((lang) => [lang, form.elements[ui`reference-${lang}`].value]),
    ),
  };
}
function stepBuilderRow(s, i) {
  const choices = s.kind === "reading" ? targets.lessons : targets.problems,
    target = s.kind === "reading" ? s.lesson_version_id : s.problem_version_id;
  return ui`<div class="builder-step" data-index="${i}"><div class="row spread"><span class="builder-title">${String(i + 1).padStart(2, "0")} / ${s.kind === "reading" ? tr("Materi") : tr("Latihan kode")}</span><div class="row">${btn(icon("up"), "step-up", i)}${btn(icon("down"), "step-down", i)}${btn(icon("trash"), "step-remove", i)}</div></div><div class="form-grid"><div class="field"><label for="step-title-${i}">Judul langkah</label><input id="step-title-${i}" name="step-title-${i}" required maxlength="200" value="${esc(s.title)}"></div><div class="field"><label for="step-module-${i}">Modul</label><input id="step-module-${i}" name="step-module-${i}" required maxlength="120" value="${esc(s.module)}"></div><div class="field"><label for="step-kind-${i}">Jenis</label><select id="step-kind-${i}" name="step-kind-${i}" data-step-kind="${i}"><option value="reading" ${s.kind === "reading" ? "selected" : ""}>Materi</option><option value="exercise" ${s.kind === "exercise" ? "selected" : ""}>Latihan kode</option></select></div><div class="field"><label for="step-target-${i}">Konten terbit</label><select id="step-target-${i}" name="step-target-${i}" data-step-target="${i}" required><option value="">Pilih konten…</option>${target && !choices.some((c) => c.id === target) ? ui`<option value="${esc(target)}" selected>Referensi sebelumnya (periksa ketersediaan)</option>` : ""}${choices.map((c) => ui`<option value="${c.id}" ${c.id === target ? "selected" : ""}>${esc(c.title)} · v${c.revision}</option>`).join("")}</select></div></div><div class="row spread wrap"><label class="check"><input type="checkbox" name="step-required-${i}" ${s.required ? "checked" : ""}>Langkah wajib</label><details><summary>Prasyarat tambahan</summary><label class="visually-hidden" for="step-deps-${i}">Prasyarat ${esc(s.title)}</label><select id="step-deps-${i}" name="step-deps-${i}" multiple>${builder
    .filter((_, n) => n !== i)
    .map(
      (other) =>
        ui`<option value="${esc(other.key)}" ${s.prerequisites.includes(other.key) ? "selected" : ""}>${esc(other.title || tr("Langkah tanpa judul"))}</option>`,
    )
    .join(
      "",
    )}</select><small>Ctrl / ⌘ untuk memilih beberapa.</small></details></div></div>`;
}
function gatherBuilder(form) {
  builder = builder.map((s, i) => {
    const kind = form.elements[ui`step-kind-${i}`].value,
      target = form.elements[ui`step-target-${i}`].value;
    return {
      ...s,
      title: form.elements[ui`step-title-${i}`].value,
      module: form.elements[ui`step-module-${i}`].value,
      kind,
      required: form.elements[ui`step-required-${i}`].checked,
      prerequisites: [...form.elements[ui`step-deps-${i}`].selectedOptions].map(
        (o) => o.value,
      ),
      lesson_version_id: kind === "reading" ? target : null,
      problem_version_id: kind === "exercise" ? target : null,
    };
  });
  return builder;
}
function redrawBuilder() {
  const list = $("#builder-list");
  if (list) list.innerHTML = builder.map(stepBuilderRow).join("");
}
function newStep() {
  const kind = targets.lessons.length ? "reading" : "exercise";
  const target = (kind === "reading" ? targets.lessons : targets.problems)[0];
  return {
    key: "step_" + crypto.randomUUID().slice(0, 8),
    title: target?.title || tr("Langkah baru"),
    module: builder.at(-1)?.module || "Fondasi pemrograman",
    kind,
    required: true,
    prerequisites: [],
    lesson_version_id: kind === "reading" ? target?.id || "" : null,
    problem_version_id: kind === "exercise" ? target?.id || "" : null,
  };
}
async function contentEditor(kind, id, cid, ticket) {
  const course = await api(ui`/courses/${cid}`);
  if (course?.archived && id === "new")
    throw new Error(
      tr("Kelas diarsipkan. Pulihkan kelas untuk membuat konten."),
    );
  let model,
    validation = null;
  if (id === "new")
    model =
      kind === "lesson"
        ? { title: "", body_markdown: "", status: "draft" }
        : kind === "problem"
          ? {
              title: "",
              statement: "",
              languages: ["c17", "cpp17"],
              status: "draft",
              provider: "custom",
              cases: [{ input: "", expected: "", public: true }],
              reference_solutions: { c17: "", cpp17: "" },
              limits: {
                compile_seconds: 10,
                time_seconds: 2,
                memory_mb: 128,
                output_bytes: 65536,
              },
            }
          : {
              title: "",
              description: "",
              languages: ["c17", "cpp17"],
              sequential: true,
              steps: [],
              status: "draft",
            };
  else
    model = await api(
      ui`/author/${kind === "lesson" ? "lesson" : kind === "problem" ? "problem" : "path"}-versions/${id}`,
    );
  if (course?.archived) {
    model.archived = true;
    model.course_archived = true;
  }
  if (model.validation_job_id)
    validation = await api(ui`/author/validations/${model.validation_job_id}`);
  if (kind === "path") {
    const catalog = {lessons: [], problems: []};
    for (let offset = 0; ; offset += 100) {
      const page = await api(ui`/author/courses/${cid}/content?offset=${offset}`);
      if (ticket !== state.route) return "";
      catalog.lessons.push(...page.lessons);
      catalog.problems.push(...page.problems);
      if (page.lessons.length < 100 && page.problems.length < 100) break;
    }
    targets = {
      lessons: catalog.lessons.filter(
        (x) => x.status === "published" && !x.archived,
      ),
      problems: catalog.problems.filter(
        (x) => x.status === "published" && !x.archived,
      ),
    };
    builder = (model.steps || []).map((s) => ({ ...s }));
    if (id === "new" && !builder.length) builder = [newStep()];
  }
  if (ticket !== state.route) return "";
  const providers = kind === "problem" ? await api("/providers") : {};
  if (ticket !== state.route) return "";
  edit = {
    kind,
    id: id === "new" ? null : id,
    cid,
    model,
    validation,
    providers,
    original: null,
  };
  const readonly =
    model.status === "published" ||
    model.status === "validating" ||
    model.archived;
  let fields = "";
  if (kind === "lesson")
    fields = ui`<div class="form-stack"><div class="field"><label for="content-title">Judul materi</label><input id="content-title" name="title" required maxlength="200" value="${esc(model.title)}" placeholder="Contoh: Mengenal input dan output"></div><div class="field"><label for="body-markdown">Isi materi</label><textarea id="body-markdown" class="rich-source" name="body_markdown" required maxlength="32768" placeholder="# Mulai dari konsep\n\nTuliskan penjelasan dan contoh kode…">${esc(model.body_markdown)}</textarea><span class="help">Gunakan Markdown untuk judul, daftar, dan blok kode. HTML aktif tidak dijalankan.</span></div>${model.body_html ? ui`<details><summary>Pratinjau tersimpan</summary><article class="prose preview-content">${model.body_html}</article></details>` : ""}</div>`;
  else if (kind === "problem") fields = problemFields(model);
  else
    fields = ui`<div class="form-stack"><div class="field"><label for="content-title">Nama jalur belajar</label><input id="content-title" name="title" required maxlength="200" value="${esc(model.title)}" placeholder="Contoh: Dasar pemrograman C/C++"></div><div class="field"><label for="path-description">Deskripsi</label><textarea id="path-description" name="description" maxlength="8000" placeholder="Apa yang akan dipahami peserta setelah jalur ini?">${esc(model.description)}</textarea></div><div class="field"><span class="label">Bahasa jalur</span><div class="row"><label class="check"><input type="checkbox" name="lang" value="c17" ${model.languages.includes("c17") ? "checked" : ""}>C17</label><label class="check"><input type="checkbox" name="lang" value="cpp17" ${model.languages.includes("cpp17") ? "checked" : ""}>C++17</label></div></div><label class="check"><input type="checkbox" name="sequential" ${model.sequential ? "checked" : ""}>Buka langkah secara berurutan</label><small>Langkah wajib sebelumnya menjadi prasyarat otomatis. Langkah opsional tidak menghalangi kelulusan.</small><div class="section-head"><h3>Susunan langkah</h3><button type="button" class="btn small" data-action="step-add">${icon("plus")}Tambah langkah</button></div>${!targets.lessons.length && !targets.problems.length ? tr('<p class="admin-note">Terbitkan materi atau soal di kelas ini sebelum menyusun jalur belajar.</p>') : ""}<div id="builder-list">${builder.map(stepBuilderRow).join("")}</div></div>`;
  if (kind === "problem")
    edit.original = {
      title: model.title,
      statement: model.statement,
      languages: model.languages,
      provider: model.provider,
      limits: model.limits,
      cases: model.cases,
      reference_solutions: model.reference_solutions,
    };
  const labels = {
    lesson: tr("materi"),
    problem: tr("soal"),
    path: tr("jalur belajar"),
  };
  const pluginNotice = kind === "problem" && model.status === "published" && !model.archived
    ? ui`<section class="panel"><p>Plugin pada soal terbit dikunci. Buat revisi untuk memilih plugin lain, lalu simpan dan uji kunci kembali.</p><p>Plugin aktif: ${esc(Object.entries(providers).filter(([, p]) => p.implemented).map(([id, p]) => p.name || id).join(", "))}</p>${btn(tr("Ganti plugin melalui revisi"), "revise-content", model.problem_id, "problems")}</section>`
    : "";
  if (model.status === "validating")
    setTimeout(() => pollValidation(model.validation_job_id, ticket), 300);
  return ui`${breadcrumb(cid)}${head(tr("STUDIO KONTEN"), id === "new" ? ui`Buat ${labels[kind]}.` : ui`${model.status === "published" ? tr("Tinjau") : "Edit"} ${labels[kind]}.`, kind === "problem" ? tr("Pisahkan soal yang dibaca peserta dari kunci penilaian privat.") : kind === "path" ? tr("Hubungkan materi dan latihan menjadi perjalanan yang terarah.") : tr("Penjelasan yang jelas membuat konsep lebih mudah dipahami."))}${pluginNotice}<form data-form="content" class="content-editor"><div class="form-error" role="alert"></div><div class="editor-form"><section class="panel"><fieldset ${readonly ? "disabled" : ""}>${fields}</fieldset></section>${editorAside(kind, model, cid, validation)}</div></form>`;
}
async function pollValidation(jobId, ticket) {
  const deadline = Date.now() + 400000;
  while (ticket === state.route && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1700));
    if (ticket !== state.route) return;
    try {
      const job = await api(ui`/author/validations/${jobId}`);
      if (["completed", "system_error"].includes(job.state)) {
        toast(
          job.valid
            ? tr("Kunci lolos. Soal siap diterbitkan.")
            : job.state === "system_error"
              ? tr("Validasi mengalami gangguan. Draft dapat diuji ulang.")
              : tr("Kunci belum lolos. Tinjau hasil pengujian."),
        );
        refresh();
        return;
      }
    } catch (e) {
      toast(e.message);
      return;
    }
  }
}
async function adminPage(tab, offset) {
  if (tab === "plugins") return pluginsPage();
  if (tab === "audit") {
    const rows = await api("/admin/audit");
    return ui`${head(tr("ADMINISTRASI"), tr("Jejak perubahan."), tr("Catatan tindakan sensitif tanpa menyertakan kata sandi atau isi kunci."), '<a class="btn" href="#/admin">Kelola akun</a>')}<div class="table-wrap"><table><thead><tr><th scope="col">Waktu</th><th scope="col">Tindakan</th><th scope="col">Objek</th></tr></thead><tbody>${rows.map((r) => ui`<tr><td>${esc(date(r.created_at))}</td><td>${esc(r.action)}</td><td class="mono">${esc(r.object_id.slice(0, 12))}…</td></tr>`).join("")}</tbody></table></div>`;
  }
  const [rows, providers] = await Promise.all([
    api(ui`/admin/users?offset=${offset}`),
    api("/providers"),
  ]);
  return ui`${head(tr("ADMINISTRASI"), tr("Kelola akses dengan tepat."), tr("Buat akun pengajar dan peserta, atur peran, atau cabut akses akun."), '<button class="btn primary" data-action="new-user">' + icon("plus") + tr("Buat akun</button>"))}<div class="row wrap"><span class="badge active">Penilai custom · ${providers.custom.healthy ? tr("tersedia") : tr("belum siap")}</span><span class="badge">DOMjudge · belum diaktifkan</span><a class="btn small" href="#/admin/plugins">Plugin penilaian</a><a class="btn small" href="#/admin/audit">${icon("shield")}Lihat audit</a></div><div class="subtle-note">Perubahan izin mencabut seluruh sesi akun terkait. Akunmu sendiri tidak dapat diubah melalui tindakan ini.</div><div class="table-wrap"><table><thead><tr><th scope="col">Username</th><th scope="col">Peran</th><th scope="col">Status</th><th scope="col">Tindakan</th></tr></thead><tbody>${rows.map((u) => ui`<tr><td><strong>${esc(u.username)}</strong></td><td>${roleLabel(u.role)}</td><td>${badge(u.is_active ? tr("AKTIF") : tr("NONAKTIF"), u.is_active ? "active" : "")}</td><td><div class="table-actions">${u.id !== state.user.id ? ui`${btn(tr("Ubah peran"), "change-role", u.id)}<button class="btn small" data-action="toggle-user" data-id="${u.id}" data-active="${u.is_active}">${u.is_active ? tr("Nonaktifkan") : tr("Aktifkan")}</button>` : badge("AKUNMU")}</div></td></tr>`).join("")}</tbody></table></div>` + reportPaging("/admin/page", offset, rows.length);
}
export async function renderStudio(parts, ticket) {
  document.title = tr("Studio pengajar — KodeLab");
  const [route, id, cid] = parts;
  if (route === "studio") {
    const offset = reportOffset(cid);
    const html = await studioHome(id === "archive", offset, ticket);
    return html + (ticket === state.route ? reportPaging(id === "archive" ? "/studio/archive" : "/studio/page", offset, courseCache.length) : "");
  }
  if (route === "course") return coursePage(id, cid || "materials", reportOffset(parts[3]), ticket);
  if (route === "path-progress") return pathReport(id, reportOffset(cid));
  if (route === "participant-work") return participantReport(id, cid, reportOffset(parts[3]));
  if (route === "admin") return adminPage(id, reportOffset(cid));
  return contentEditor(route.replace("-editor", ""), id, cid, ticket);
}
export async function studioAction(action, el) {
  if (await pluginAction(action, el)) return;
  if (action === "review-code") {
    const r = await api(ui`/submissions/${el.dataset.id}`);
    modal(tr("Detail pengerjaan"), ui`<h3>${esc(el.dataset.participant)}</h3><p>${esc(el.dataset.exercise)} · ${language(r.language)} · ${esc(date(r.created_at))}</p><pre class="code-detail">${esc(r.source)}</pre>${renderResult(r)}<section><h3>Jalankan ulang kode</h3><p class="subtle-note">Eksekusi pengajar tidak mengubah nilai atau progres peserta.</p><label for="review-input">Input percobaan</label><textarea id="review-input" rows="3" maxlength="32768" spellcheck="false"></textarea><button class="btn primary" data-action="review-run" data-id="${r.id}" ${el.dataset.archived === "true" ? "disabled" : ""}>Jalankan kode</button><div id="review-result" aria-live="polite"></div></section><div class="modal-footer"><button class="btn" data-action="close-modal">Tutup</button></div>`);
  } else if (action === "review-run") {
    const panel = $("#review-result");
    el.disabled = true;
    try {
      panel.innerHTML = ui`<p>Menjalankan kode…</p>`;
      let r = await api(ui`/author/submissions/${el.dataset.id}/run`, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: {input: $("#review-input").value}});
      for (let n = 0; n < 180 && ["queued", "running", "retry_pending"].includes(r.state); n++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (!panel.isConnected || !$("#modal").open) return;
        r = await api(ui`/submissions/${r.id}`);
      }
      if (panel.isConnected) panel.innerHTML = ["queued", "running", "retry_pending"].includes(r.state)
        ? ui`<p>Eksekusi masih diproses. Coba lagi nanti.</p>` : renderResult(r);
    } catch (error) {
      if (panel.isConnected) panel.innerHTML = ui`<p role="alert">${esc(error.message)}</p>`;
    } finally { if (el.isConnected) el.disabled = false; }
  } else if (["rotate-invitation", "revoke-invitation"].includes(action)) {
    const rotate = action === "rotate-invitation";
    modal(
      rotate
        ? tr("Buat kode undangan baru?")
        : tr("Nonaktifkan kode undangan?"),
      ui`<p>${rotate ? tr("Kode sebelumnya tidak berlaku lagi. Kode baru dapat digunakan selama 24 jam. Bagikan hanya kepada calon anggota kelas.") : tr("Kode yang sudah dibagikan tidak dapat digunakan lagi. Anggota yang sudah bergabung tetap memiliki akses.")}</p><form data-form="${action}" data-id="${el.dataset.id}">${formFooter(rotate ? tr("Buat kode") : tr("Nonaktifkan"))}</form>`,
    );
  } else if (
    ["archive-course", "restore-course", "delete-course"].includes(action)
  ) {
    const course = courseCache.find((c) => c.id === el.dataset.id);
    if (!course) return;
    const remove = action === "delete-course",
      archive = action === "archive-course";
    modal(
      remove
        ? tr("Hapus kelas permanen?")
        : archive
          ? tr("Arsipkan kelas?")
          : tr("Pulihkan kelas?"),
      ui`<form data-form="${action}" data-id="${esc(course.id)}" class="form-stack"><p>${remove ? tr("Seluruh materi, versi konten, bank soal, kunci, kasus uji, learning path, keanggotaan, histori kiriman, nilai, dan progres kelas ini akan dihapus permanen. Akun pengguna tetap ada. Tindakan ini tidak dapat dibatalkan.") : archive ? tr("Kelas disembunyikan dari katalog dan menjadi hanya-baca. Konten, histori, nilai, serta progres tetap tersimpan dan kelas dapat dipulihkan.") : tr("Kelas kembali aktif. Peserta dapat melanjutkan progres sebelumnya.")}</p><strong>${esc(course.title)}</strong>${remove ? ui`<div class="field"><label for="delete-course-title">Ketik nama kelas untuk mengonfirmasi</label><input id="delete-course-title" name="confirmation_title" required autocomplete="off" maxlength="200"></div>` : ""}${formFooter(remove ? tr("Hapus permanen") : archive ? tr("Arsipkan kelas") : tr("Pulihkan kelas"))}</form>`,
    );
  } else if (action === "new-course")
    modal(
      tr("Buat kelas baru"),
      ui`<form data-form="new-course" class="form-stack"><div class="field"><label for="course-title">Nama kelas</label><input id="course-title" name="title" required maxlength="200" placeholder="Contoh: Pemrograman dasar"></div><div class="field"><label for="course-description">Deskripsi kelas</label><textarea id="course-description" name="description" maxlength="8000" rows="3"></textarea></div><label class="check"><input type="checkbox" name="is_public">Kelas publik · peserta dapat bergabung sendiri</label>${formFooter(tr("Buat kelas"))}</form>`,
    );
  else if (action === "add-member")
    modal(
      tr("Tambahkan anggota kelas"),
      ui`<form data-form="add-member" data-course="${el.dataset.id}" class="form-stack"><div class="field"><label for="member-username">Username akun</label><input id="member-username" name="username" required placeholder="username_peserta"></div><div class="field"><label for="member-role">Peran di kelas</label><select id="member-role" name="role"><option value="student">Peserta</option><option value="teacher">Pengajar</option></select><span class="help">Penugasan pengajar hanya berlaku untuk akun dengan peran pengajar.</span></div>${formFooter(tr("Tambahkan"))}</form>`,
    );
  else if (action === "remove-member") {
    modal(
      tr("Cabut akses kelas?"),
      ui`<p>Anggota ini tidak dapat lagi mengakses kelas privat atau mengirim jawaban baru. Riwayat kode tetap tersimpan.</p><form data-form="remove-member" data-course="${el.dataset.course}" data-id="${el.dataset.id}">${formFooter(tr("Cabut akses"))}</form>`,
    );
  } else if (action === "revise-content") {
    const kind = el.dataset.kind;
    const result = await api(ui`/author/${kind}/${el.dataset.id}/versions`, {
      method: "POST",
    });
    const cid = location.hash.startsWith("#/course/")
      ? location.hash.split("/")[2]
      : edit?.cid;
    go(
      ui`/${kind === "lessons" ? "lesson" : kind === "problems" ? "problem" : "path"}-editor/${result.id}/${cid}`,
    );
  } else if (action === "archive-content")
    modal(
      tr("Arsipkan konten?"),
      ui`<p>Konten tidak akan tersedia untuk penggunaan baru. Riwayat dan versi yang sudah diikuti peserta tetap tersimpan.</p><form data-form="archive-content" data-kind="${el.dataset.kind}" data-id="${el.dataset.id}">${formFooter(tr("Arsipkan"))}</form>`,
    );
  else if (action === "add-case" || action === "remove-case") {
    const form = $('[data-form="content"]');
    const cases = getCases(form);
    if (action === "add-case") {
      if (cases.length >= 10) {
        toast(tr("Maksimal 10 kasus uji."));
        return;
      }
      cases.push({ input: "", expected: "", public: false });
    } else {
      if (cases.length <= 1) {
        toast(tr("Sisakan minimal satu kasus uji."));
        return;
      }
      cases.splice(Number(el.dataset.index), 1);
    }
    $("#case-list").innerHTML = cases.map(caseRow).join("");
  } else if (action.startsWith("step-")) {
    const form = $('[data-form="content"]');
    gatherBuilder(form);
    const i = Number(el.dataset.id);
    if (action === "step-add") {
      if (builder.length >= 60) {
        toast(tr("Maksimal 60 langkah per jalur."));
        return;
      }
      builder.push(newStep());
    } else if (action === "step-remove") {
      if (builder.length <= 1) {
        toast(tr("Sisakan minimal satu langkah."));
        return;
      }
      const [removed] = builder.splice(i, 1);
      builder.forEach(
        (s) =>
          (s.prerequisites = s.prerequisites.filter((k) => k !== removed.key)),
      );
    } else if (action === "step-up" && i > 0)
      [builder[i - 1], builder[i]] = [builder[i], builder[i - 1]];
    else if (action === "step-down" && i < builder.length - 1)
      [builder[i], builder[i + 1]] = [builder[i + 1], builder[i]];
    redrawBuilder();
  } else if (action === "new-user")
    modal(
      tr("Buat akun"),
      ui`<form data-form="new-user" class="form-stack"><div class="field"><label for="new-username">Username</label><input id="new-username" name="username" required minlength="3" maxlength="40"></div><div class="field"><label for="new-password">Kata sandi awal</label><input id="new-password" name="password" type="password" required minlength="15" maxlength="128" autocomplete="new-password"><span class="help">Minimal 15 karakter. Sampaikan hanya kepada pemilik akun.</span></div><div class="field"><label for="new-role">Peran</label><select id="new-role" name="role"><option value="student">Peserta</option><option value="teacher">Pengajar</option><option value="admin">Administrator</option></select></div>${formFooter(tr("Buat akun"))}</form>`,
    );
  else if (action === "change-role")
    modal(
      tr("Ubah peran akun"),
      ui`<form data-form="change-role" data-id="${el.dataset.id}" class="form-stack"><div class="field"><label for="changed-role">Peran baru</label><select id="changed-role" name="role"><option value="student">Peserta</option><option value="teacher">Pengajar</option><option value="admin">Administrator</option></select></div><small>Seluruh sesi akun akan dicabut setelah perubahan.</small>${formFooter(tr("Simpan peran"))}</form>`,
    );
  else if (action === "toggle-user") {
    await api(ui`/admin/users/${el.dataset.id}`, {
      method: "PATCH",
      body: { is_active: el.dataset.active !== "true" },
    });
    toast(tr("Status akun diperbarui."));
    refresh();
  }
}
function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])]),
    );
  return value;
}
export async function studioSubmit(form, data, intent) {
  if (await pluginSubmit(form)) return;
  const kind = form.dataset.form;
  if (kind === "content") {
    let payload;
    if (edit.kind === "lesson")
      payload = {
        title: String(data.get("title")),
        body_markdown: String(data.get("body_markdown")),
      };
    else if (edit.kind === "problem") payload = gatherProblem(form);
    else
      payload = {
        title: String(data.get("title")),
        description: String(data.get("description")),
        languages: data.getAll("lang"),
        sequential: data.has("sequential"),
        steps: gatherBuilder(form).map((s) => ({
          key: s.key,
          title: s.title,
          module: s.module,
          kind: s.kind,
          required: s.required,
          prerequisites: s.prerequisites,
          lesson_version_id: s.lesson_version_id || null,
          problem_version_id: s.problem_version_id || null,
        })),
      };
    const current = { ...edit };
    await formTask(form, async () => {
      let model = current.model,
        id = current.id;
      if (current.kind === "problem" && intent === "publish") {
        if (
          JSON.stringify(stable(payload)) !==
          JSON.stringify(stable(current.original))
        )
          throw new Error(
            tr(
              "Draft berubah. Simpan dan uji kunci kembali sebelum menerbitkan.",
            ),
          );
      } else {
        const collection =
          current.kind === "lesson"
            ? "lessons"
            : current.kind === "problem"
              ? "problems"
              : "paths";
        const changed =
          current.kind !== "problem" ||
          JSON.stringify(stable(payload)) !==
            JSON.stringify(stable(current.original));
        if (!id)
          model = await api(ui`/author/courses/${current.cid}/${collection}`, {
            method: "POST",
            body: payload,
          });
        else if (changed)
          model = await api(ui`/author/${current.kind}-versions/${id}`, {
            method: "PUT",
            body: { ...payload, edit_revision: model.edit_revision },
          });
        id = model.id;
      }
      if (intent === "validate") {
        await api(ui`/author/problem-versions/${id}/validate`, {
          method: "POST",
          body: { edit_revision: model.edit_revision },
        });
        toast(tr("Validasi kunci dimulai."));
      } else if (intent === "publish") {
        await api(ui`/author/${current.kind}-versions/${id}/publish`, {
          method: "POST",
          body: { edit_revision: model.edit_revision },
        });
        toast(tr("Konten berhasil diterbitkan."));
      } else toast(tr("Draft tersimpan."));
      const target = ui`/${current.kind}-editor/${id}/${current.cid}`;
      if (location.hash === ui`#${target}`) refresh();
      else go(target);
    });
    return;
  }
  await formTask(form, async () => {
    if (kind === "course-settings") {
      await api(ui`/courses/${form.dataset.id}/settings`, {
        method: "PATCH",
        body: {
          title: String(data.get("title")),
          description: String(data.get("description")),
          is_public: data.has("is_public"),
          edit_revision: Number(form.dataset.revision),
        },
      });
      toast(tr("Pengaturan kelas tersimpan."));
      refresh();
      return;
    }
    if (kind === "rotate-invitation") {
      const invitation = await api(ui`/courses/${form.dataset.id}/invitation`, {
        method: "POST",
      });
      closeModal();
      refresh();
      modal(
        tr("Kode undangan kelas"),
        ui`<p>Bagikan kode ini kepada calon anggota. Kode juga tersedia di halaman Pengaturan dan berlaku hingga ${esc(date(invitation.expires_at))}.</p><output id="invite-code" class="mono invite-code">${esc(invitation.code)}</output><p class="subtle-note">Peserta membuka Kelas → Gabung dengan kode.</p><div class="modal-footer"><button type="button" class="btn primary" data-action="close-modal">Tutup</button></div>`,
      );
      return;
    }
    if (kind === "revoke-invitation") {
      await api(ui`/courses/${form.dataset.id}/invitation`, {
        method: "DELETE",
      });
      closeModal();
      toast(tr("Kode undangan dinonaktifkan."));
      refresh();
      return;
    }
    if (["archive-course", "restore-course", "delete-course"].includes(kind)) {
      const remove = kind === "delete-course";
      await api(
        ui`/courses/${form.dataset.id}${remove ? "" : kind === "archive-course" ? "/archive" : "/restore"}`,
        {
          method: remove ? "DELETE" : "POST",
          ...(remove
            ? {
                body: {
                  confirmation_title: String(data.get("confirmation_title")),
                },
              }
            : {}),
        },
      );
      closeModal();
      toast(
        remove
          ? tr("Kelas dan seluruh data pembelajarannya dihapus.")
          : kind === "archive-course"
            ? tr("Kelas diarsipkan.")
            : tr("Kelas dipulihkan."),
      );
      if (remove && !/^#\/?studio(?:\/|$)/.test(location.hash)) go("/studio");
      else refresh();
      return;
    }
    if (kind === "new-course") {
      const row = await api("/courses", {
        method: "POST",
        body: {
          title: String(data.get("title")),
          description: String(data.get("description") || ""),
          is_public: data.has("is_public"),
        },
      });
      closeModal();
      go(ui`/course/${row.id}/materials`);
      return;
    }
    if (kind === "add-member")
      await api(ui`/courses/${form.dataset.course}/members`, {
        method: "POST",
        body: {
          username: String(data.get("username")).trim().toLowerCase(),
          role: String(data.get("role")),
        },
      });
    if (kind === "remove-member")
      await api(
        ui`/courses/${form.dataset.course}/members/${form.dataset.id}`,
        {
          method: "DELETE",
        },
      );
    if (kind === "archive-content")
      await api(ui`/author/${form.dataset.kind}/${form.dataset.id}/archive`, {
        method: "POST",
      });
    if (kind === "new-user")
      await api("/admin/users", {
        method: "POST",
        body: {
          username: String(data.get("username")).trim().toLowerCase(),
          password: String(data.get("password")),
          role: String(data.get("role")),
        },
      });
    if (kind === "change-role")
      await api(ui`/admin/users/${form.dataset.id}`, {
        method: "PATCH",
        body: { role: String(data.get("role")) },
      });
    closeModal();
    toast(tr("Perubahan tersimpan."));
    refresh();
  });
}
export function studioChange(event) {
  if (event.type !== "change") return;
  if (event.target.name === "lang" && edit?.kind === "problem")
    document.querySelectorAll(".reference-field").forEach((field) => {
      field.hidden = !$(ui`[name="lang"][value="${field.dataset.language}"]`)
        .checked;
    });
  if (event.target.dataset.stepKind !== undefined) {
    const i = Number(event.target.dataset.stepKind);
    gatherBuilder($('[data-form="content"]'));
    const s = builder[i],
      target = (s.kind === "reading" ? targets.lessons : targets.problems)[0];
    s.lesson_version_id = s.kind === "reading" ? target?.id || "" : null;
    s.problem_version_id = s.kind === "exercise" ? target?.id || "" : null;
    s.title = target?.title || s.title;
    redrawBuilder();
  } else if (event.target.dataset.stepTarget !== undefined) {
    const i = Number(event.target.dataset.stepTarget);
    gatherBuilder($('[data-form="content"]'));
    const s = builder[i],
      target = (s.kind === "reading" ? targets.lessons : targets.problems).find(
        (t) => t.id === event.target.value,
      );
    if (target) {
      s.title = target.title;
      redrawBuilder();
    }
  }
}
