/* Uses a newly created test class only; never deletes pre-existing classes. */
const { chromium, request } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const crypto = require("node:crypto");
const base = process.env.TEST_BASE_URL || "http://127.0.0.1:8000";
const env = Object.fromEntries(
  fs
    .readFileSync(".env", "utf8")
    .split(/\r?\n/)
    .filter((x) => x.includes("=") && !x.startsWith("#"))
    .map((x) => [x.slice(0, x.indexOf("=")), x.slice(x.indexOf("=") + 1)]),
);
const password = crypto.randomBytes(24).toString("hex");
const suffix = crypto.randomBytes(4).toString("hex");
const C =
  '#include <stdio.h>\nint main(void){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);return 0;}';
const CPP =
  '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}';
let browser, admin;
let testCourseId;
const inviteCodes = [];
async function raw(context, path, method = "GET", data) {
  const cookies = await context.cookies();
  const csrf = cookies.find((c) => c.name === "judgement_csrf")?.value;
  return context.request.fetch(base + path, {
    method,
    headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
    ...(data === undefined ? {} : { data }),
  });
}
async function json(context, path, method = "GET", data) {
  const response = await raw(context, path, method, data);
  assert(response.ok(), `HTTP ${response.status()} for ${method} ${path}`);
  return response.json();
}
async function waitResult(context, path) {
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const row = await json(context, path);
    assert.notEqual(row.state, "system_error");
    if (row.state === "completed") return row;
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
  throw new Error("Judging timed out");
}
async function main() {
  fs.mkdirSync("artifacts", { recursive: true });
  browser = await chromium.launch({ channel: "msedge", headless: true });
  admin = await browser.newContext();
  await json(admin, "/auth/login", "POST", {
    username: env.BOOTSTRAP_ADMIN_USERNAME,
    password: env.BOOTSTRAP_ADMIN_PASSWORD,
  });
  const originalCourses = (await json(admin, "/courses")).map((c) => c.id);
  for (const role of ["teacher", "student"])
    await json(admin, "/admin/users", "POST", {
      username: `lifecycle_${role}_${suffix}`,
      role,
      password,
    });
  const teacher = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const student = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  for (const [context, role] of [
    [teacher, "teacher"],
    [student, "student"],
  ])
    await json(context, "/auth/login", "POST", {
      username: `lifecycle_${role}_${suffix}`,
      password,
    });
  let title = `Kelas uji penghapusan ${suffix}`;
  const course = await json(teacher, "/courses", "POST", {
    title,
    is_public: true,
  });
  const cid = course.id;
  assert(!originalCourses.includes(cid));
  testCourseId = cid;
  const lesson = await json(teacher, `/author/courses/${cid}/lessons`, "POST", {
    title: "Input dan output",
    body_markdown: "# Materi\nPelajari input dan output.",
  });
  await json(teacher, `/author/lesson-versions/${lesson.id}/publish`, "POST", {
    edit_revision: 1,
  });
  const problem = await json(
    teacher,
    `/author/courses/${cid}/problems`,
    "POST",
    {
      title: "Penjumlahan",
      statement: "Jumlahkan dua bilangan.",
      languages: ["c17", "cpp17"],
      cases: [
        { input: "2 3\n", expected: "5\n", public: true },
        { input: "-8 9\n", expected: "1\n", public: false },
      ],
      reference_solutions: { c17: C, cpp17: CPP },
    },
  );
  const job = await json(
    teacher,
    `/author/problem-versions/${problem.id}/validate`,
    "POST",
    { edit_revision: 1 },
  );
  assert((await waitResult(teacher, `/author/validations/${job.id}`)).valid);
  await json(
    teacher,
    `/author/problem-versions/${problem.id}/publish`,
    "POST",
    { edit_revision: 1 },
  );
  const path = await json(teacher, `/author/courses/${cid}/paths`, "POST", {
    title: "Jalur uji lifecycle",
    steps: [
      {
        key: "intro",
        title: "Materi",
        kind: "reading",
        lesson_version_id: lesson.id,
      },
      {
        key: "sum",
        title: "Latihan",
        kind: "exercise",
        problem_version_id: problem.id,
      },
    ],
  });
  await json(teacher, `/author/path-versions/${path.id}/publish`, "POST", {
    edit_revision: 1,
  });
  const e = await json(student, `/paths/${path.path_id}/enroll`, "POST");
  await json(
    student,
    `/enrollments/${e.id}/steps/${e.steps[0].id}/complete`,
    "POST",
  );
  const body = {
    problem_version_id: problem.id,
    enrollment_id: e.id,
    path_step_id: e.steps[1].id,
    language: "cpp17",
    source: CPP,
  };
  const submission = await json(student, "/submissions", "POST", body);
  assert.equal(
    (await waitResult(student, `/submissions/${submission.id}`)).verdict,
    "ACCEPTED",
  );
  // Extra unpublished versions exercise deletion beyond the currently published data.
  const draft = await json(
    teacher,
    `/author/problems/${problem.problem_id}/versions`,
    "POST",
  );
  const pathDraft = await json(
    teacher,
    `/author/paths/${path.path_id}/versions`,
    "POST",
  );
  const pages = [await teacher.newPage(), await student.newPage()],
    errors = [];
  pages.forEach((p) =>
    p.on("pageerror", (error) => errors.push(error.message)),
  );
  const [tp, sp] = pages;
  await sp.goto(`${base}/#/classes/${cid}`);
  await sp
    .getByRole("heading", { name: "Leaderboard kelas", exact: true })
    .waitFor();
  await sp.locator(".embedded-leaderboard .leaderboard-self").waitFor();
  assert.equal(
    await sp
      .getByRole("link", { name: "Leaderboard kelas", exact: true })
      .count(),
    0,
  );
  const completed = await json(student, `/enrollments/${e.id}`);
  await sp.setViewportSize({ width: 390, height: 844 });
  assert(
    await sp.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  );
  await sp.screenshot({
    path: "artifacts/web-class-embedded-leaderboard.png",
    fullPage: true,
  });
  console.log(
    "PASS lifecycle: real C/C++ validation, Accepted, and embedded leaderboard on the class page/mobile",
  );
  // Exercise settings and invitation UI on the newly created test class only.
  await json(admin, "/admin/users", "POST", {
    username: `visibility_guest_${suffix}`,
    role: "student",
    password,
  });
  const guest = await browser.newContext();
  await json(guest, "/auth/login", "POST", {
    username: `visibility_guest_${suffix}`,
    password,
  });
  const gp = await guest.newPage();
  gp.on("pageerror", (error) => errors.push(error.message));
  await tp.goto(`${base}/#/course/${cid}/settings`);
  title += " privat";
  await tp.locator("#settings-title").fill(title);
  await tp
    .locator("#settings-description")
    .fill("Deskripsi kelas privat untuk peserta undangan.");
  await tp
    .locator('[data-form="course-settings"] [name="is_public"]')
    .uncheck();
  await tp
    .getByRole("button", { name: "Simpan pengaturan", exact: true })
    .click();
  await tp
    .getByRole("button", { name: "Buat kode undangan", exact: true })
    .waitFor();
  assert.equal((await raw(guest, `/courses/${cid}/learning`)).status(), 404);
  assert.equal((await raw(student, `/enrollments/${e.id}`)).status(), 404);

  async function generateInvite(label) {
    await tp.getByRole("button", { name: label, exact: true }).click();
    await tp
      .getByRole("dialog")
      .getByRole("button", { name: "Buat kode", exact: true })
      .click();
    await tp.locator("#invite-code").waitFor();
    const code = (await tp.locator("#invite-code").textContent()).trim();
    inviteCodes.push(code);
    assert(/^[0-9]{6}$/.test(code), "Invitation must contain six ASCII digits");
    await tp
      .getByRole("dialog")
      .getByRole("button", { name: "Tutup", exact: true })
      .last()
      .click();
    return code;
  }
  const firstCode = await generateInvite("Buat kode undangan");
  assert.equal(
    (await raw(student, "/courses/join", "POST", { code: firstCode })).status(),
    200,
  );
  assert.equal(
    (await json(student, `/enrollments/${e.id}`)).completion_seconds,
    completed.completion_seconds,
  );
  await gp.goto(`${base}/#/classes`);
  await gp
    .getByRole("button", { name: "Gabung dengan kode", exact: true })
    .click();
  await gp.locator("#join-code").fill(firstCode);
  await gp
    .getByRole("dialog")
    .getByRole("button", { name: "Gabung kelas", exact: true })
    .click();
  await gp.waitForURL(`**/#/classes/${cid}`);
  await gp.getByRole("heading", { name: title, exact: true }).waitFor();
  await gp
    .getByText("Deskripsi kelas privat untuk peserta undangan.", {
      exact: true,
    })
    .waitFor();
  assert.equal((await json(guest, "/my/learning")).length, 0);
  await tp.reload();
  await tp
    .getByRole("button", { name: "Ganti kode undangan", exact: true })
    .waitFor();
  assert.equal(
    (await tp.locator("#settings-invite-code").textContent()).trim(),
    firstCode,
  );
  const secondCode = await generateInvite("Ganti kode undangan");
  assert.equal(
    (await raw(guest, "/courses/join", "POST", { code: firstCode })).status(),
    400,
  );
  await tp
    .getByRole("button", { name: "Nonaktifkan kode", exact: true })
    .click();
  await tp
    .getByRole("dialog")
    .getByRole("button", { name: "Nonaktifkan", exact: true })
    .click();
  await tp
    .getByRole("button", { name: "Buat kode undangan", exact: true })
    .waitFor();
  assert.equal(
    (await raw(guest, "/courses/join", "POST", { code: secondCode })).status(),
    400,
  );
  await tp.locator('[data-form="course-settings"] [name="is_public"]').check();
  await tp
    .getByRole("button", { name: "Simpan pengaturan", exact: true })
    .click();
  await tp
    .getByText(
      "Ubah dan simpan kelas sebagai privat untuk membuat kode undangan.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    (await json(student, `/enrollments/${e.id}`)).completion_seconds,
    completed.completion_seconds,
  );
  await tp.screenshot({
    path: "artifacts/web-course-settings.png",
    fullPage: true,
  });
  console.log(
    "PASS visibility: name/description and public/private settings, 6-digit invite join, rotation/revocation, existing progress preserved; no invitation appears in screenshots",
  );
  await tp.goto(`${base}/#/course/${cid}/materials`);
  await tp.getByRole("button", { name: "Arsipkan kelas", exact: true }).click();
  await tp
    .getByRole("dialog")
    .getByRole("button", { name: "Arsipkan kelas", exact: true })
    .click();
  await tp
    .getByRole("button", { name: "Pulihkan kelas", exact: true })
    .waitFor();
  await tp.goto(`${base}/#/studio`);
  await tp.getByRole("link", { name: "Kelas aktif", exact: true }).waitFor();
  assert.equal(await tp.locator(`[data-course-id="${cid}"]`).count(), 0);
  await tp.getByRole("link", { name: "Arsip kelas", exact: true }).click();
  await tp.locator(`[data-course-id="${cid}"]`).waitFor();
  await tp.reload();
  await tp.locator(`[data-course-id="${cid}"]`).waitFor();
  await sp.goto(`${base}/#/classes`);
  await sp.locator("#class-search").waitFor();
  assert.equal(await sp.locator(`[data-course-id="${cid}"]`).count(), 0);
  assert.equal(
    await sp.getByRole("link", { name: "Arsip kelas", exact: true }).count(),
    0,
  );
  assert.equal((await raw(student, `/courses/${cid}/learning`)).status(), 404);
  assert.equal(
    (await raw(student, `/courses/${cid}/leaderboard`)).status(),
    404,
  );
  assert.equal((await raw(student, `/enrollments/${e.id}`)).status(), 404);
  assert.equal(
    (await raw(student, "/submissions", "POST", body)).status(),
    404,
  );
  assert.equal(
    (await json(teacher, `/courses/${cid}/leaderboard`)).rows[0].score,
    100,
  );
  assert.equal(
    (
      await raw(teacher, `/author/courses/${cid}/lessons`, "POST", {
        title: "No",
        body_markdown: "No",
      })
    ).status(),
    409,
  );
  assert.equal(
    (await json(student, "/leaderboards")).rows.some(
      (r) => r.username === `lifecycle_student_${suffix}`,
    ),
    false,
  );
  await tp.screenshot({
    path: "artifacts/web-course-archived.png",
    fullPage: true,
  });
  await tp.getByRole("button", { name: "Pulihkan kelas", exact: true }).click();
  await tp
    .getByRole("dialog")
    .getByRole("button", { name: "Pulihkan kelas", exact: true })
    .click();
  await tp.locator(`[data-course-id="${cid}"]`).waitFor({ state: "hidden" });
  assert(new URL(tp.url()).hash === "#/studio/archive");
  await tp.getByRole("link", { name: "Kelas aktif", exact: true }).click();
  await tp
    .getByRole("button", { name: "Arsipkan kelas", exact: true })
    .waitFor();
  assert((await json(student, "/paths")).some((p) => p.id === path.path_id));
  assert.equal(
    (await json(student, `/enrollments/${e.id}`)).completion_seconds,
    completed.completion_seconds,
  );
  console.log(
    "PASS lifecycle: teacher archives/restores through UI; catalog and overall leaderboard hide archived class, progress remains fixed",
  );
  // Re-archive from the active list; the card must move out immediately.
  await tp.getByRole("button", { name: "Arsipkan kelas", exact: true }).click();
  await tp
    .getByRole("dialog")
    .getByRole("button", { name: "Arsipkan kelas", exact: true })
    .click();
  await tp.locator(`[data-course-id="${cid}"]`).waitFor({ state: "hidden" });
  await tp.getByRole("link", { name: "Arsip kelas", exact: true }).click();
  await tp.locator(`[data-course-id="${cid}"]`).waitFor();
  // Deleting from the archive tab must refresh and preserve the selected filter.
  const targetCard = tp
    .locator(".course-card")
    .filter({ has: tp.getByRole("heading", { name: title, exact: true }) });
  await targetCard
    .getByRole("button", { name: "Hapus kelas", exact: true })
    .click();
  await tp.locator("#delete-course-title").fill("wrong");
  await tp
    .getByRole("dialog")
    .getByRole("button", { name: "Hapus permanen", exact: true })
    .click();
  await tp
    .locator(".form-error")
    .filter({ hasText: "Nama kelas belum sesuai" })
    .waitFor();
  await tp.locator("#delete-course-title").fill(title);
  await tp.screenshot({
    path: "artifacts/web-course-delete-confirmation.png",
    fullPage: true,
  });
  const listReloaded = tp.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/courses" &&
      response.request().method() === "GET" &&
      response.ok(),
  );
  await tp
    .getByRole("dialog")
    .getByRole("button", { name: "Hapus permanen", exact: true })
    .click();
  await tp.waitForURL(/#\/studio\/archive$/);
  await listReloaded;
  await targetCard.waitFor({ state: "hidden" });
  console.log(
    "PASS lifecycle: archive filter persists across reload; restore/archive/delete update both status lists immediately",
  );
  for (const url of [
    `/courses/${cid}/leaderboard`,
    `/author/courses/${cid}/content`,
    `/author/problem-versions/${problem.id}`,
    `/author/problem-versions/${draft.id}`,
    `/author/lesson-versions/${lesson.id}`,
    `/author/path-versions/${path.id}`,
    `/author/path-versions/${pathDraft.id}`,
    `/author/validations/${job.id}`,
  ])
    assert.equal((await raw(teacher, url)).status(), 404);
  assert.equal((await raw(student, `/enrollments/${e.id}`)).status(), 404);
  assert.equal(
    (await raw(student, `/submissions/${submission.id}`)).status(),
    404,
  );
  assert.equal((await json(student, "/submissions")).length, 0);
  const remaining = (await json(admin, "/courses")).map((c) => c.id);
  assert(!remaining.includes(cid));
  assert(originalCourses.every((id) => remaining.includes(id)));
  assert.deepEqual(errors, []);
  console.log(
    "PASS lifecycle: wrong-name protection and permanent deletion of populated class in MariaDB; existing classes/accounts remain intact",
  );
  await browser.close();
}
main().catch(async (error) => {
  let message = error.stack || error.message;
  for (const secret of [
    password,
    env.BOOTSTRAP_ADMIN_PASSWORD,
    ...inviteCodes,
  ].filter(Boolean))
    message = message.split(secret).join("[redacted]");
  console.error(message);
  if (admin && testCourseId) {
    try {
      const settings = await raw(admin, `/courses/${testCourseId}/settings`);
      if (settings.ok()) {
        const own = await settings.json();
        if (own.title.startsWith(`Kelas uji penghapusan ${suffix}`))
          await raw(admin, `/courses/${testCourseId}`, "DELETE", {
            confirmation_title: own.title,
          });
      }
    } catch {}
  }
  if (browser) await browser.close();
  process.exitCode = 1;
});
