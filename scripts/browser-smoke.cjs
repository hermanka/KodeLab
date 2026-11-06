/* Real browser workflow. Secrets remain in memory; no traces or HAR files are written. */
const { chromium, request } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const base = process.env.TEST_BASE_URL || "http://127.0.0.1:8000";
const settings = Object.fromEntries(
  fs
    .readFileSync(path.join(__dirname, "../.env"), "utf8")
    .split(/\r?\n/)
    .filter((x) => x.includes("=") && !x.startsWith("#"))
    .map((x) => [x.slice(0, x.indexOf("=")), x.slice(x.indexOf("=") + 1)]),
);
const secrets = [settings.BOOTSTRAP_ADMIN_PASSWORD];
const C =
  '#include <stdio.h>\nint main(void){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);return 0;}';
const CPP =
  '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}';
const errors = [],
  foreign = [];
let browser;
function watch(page) {
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (
      m.type() === "error" &&
      /Content Security Policy|Refused to/.test(m.text())
    )
      errors.push(m.text());
  });
  page.on("request", (req) => {
    if (!req.url().startsWith(base) && /^https?:/.test(req.url()))
      foreign.push(new URL(req.url()).hostname);
  });
}
async function login(page, username, password) {
  await page.goto(base);
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Masuk ke KodeLab" }).click();
  await page
    .getByRole("heading", { name: `Halo, ${username}.`, exact: true })
    .waitFor();
}
async function json(response) {
  assert(response.ok(), `API request failed with HTTP ${response.status()}`);
  return response.json();
}
async function waitResult(page, title) {
  await page
    .locator("#judge-result .result-title")
    .filter({ hasText: title })
    .waitFor({ timeout: 150000 });
}
async function csrf(context) {
  return (await context.cookies()).find((c) => c.name === "judgement_csrf")
    ?.value;
}
async function enrollment(context, id) {
  return json(await context.request.get(`${base}/enrollments/${id}`));
}
async function createLesson(page, cid, title, body) {
  await page.goto(`${base}/#/lesson-editor/new/${cid}`);
  await page.locator("#content-title").fill(title);
  await page.locator("#body-markdown").fill(body);
  await page.getByRole("button", { name: "Terbitkan", exact: true }).click();
  await page
    .locator(".editor-aside .badge")
    .filter({ hasText: "TERBIT" })
    .waitFor();
}
async function main() {
  fs.mkdirSync(path.join(__dirname, "../artifacts"), { recursive: true });
  browser = await chromium.launch({ channel: "msedge", headless: true });
  const adminContext = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const admin = await adminContext.newPage();
  watch(admin);
  await admin.goto(base);
  await admin.getByRole("heading", { name: "Lanjutkan langkahmu." }).waitFor();
  await admin.screenshot({ path: "artifacts/web-login.png", fullPage: true });
  await login(
    admin,
    settings.BOOTSTRAP_ADMIN_USERNAME,
    settings.BOOTSTRAP_ADMIN_PASSWORD,
  );
  const suffix = crypto.randomBytes(3).toString("hex");
  const teacherName = "pengajar_" + suffix,
    studentName = "peserta_" + suffix,
    password = crypto.randomBytes(24).toString("hex");
  secrets.push(password);
  await admin.goto(`${base}/#/admin`);
  for (const [username, role] of [
    [teacherName, "teacher"],
    [studentName, "student"],
  ]) {
    await admin.getByRole("button", { name: "Buat akun", exact: true }).click();
    await admin.locator("#new-username").fill(username);
    await admin.locator("#new-password").fill(password);
    await admin.locator("#new-role").selectOption(role);
    await admin
      .getByRole("dialog")
      .getByRole("button", { name: "Buat akun", exact: true })
      .click();
    await admin.getByRole("dialog").waitFor({ state: "hidden" });
    await admin.getByRole("cell", { name: username, exact: true }).waitFor();
  }
  console.log(
    "PASS browser: login, secure cookies, and administrator account creation",
  );

  const teacherContext = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    }),
    teacher = await teacherContext.newPage();
  watch(teacher);
  await login(teacher, teacherName, password);
  await teacher.goto(`${base}/#/studio`);
  await teacher
    .getByRole("button", { name: "Buat kelas", exact: true })
    .first()
    .click();
  await teacher.locator("#course-title").fill("Pemrograman Dasar C/C++");
  await teacher
    .getByLabel("Kelas publik · peserta dapat bergabung sendiri")
    .check();
  await teacher
    .getByRole("dialog")
    .getByRole("button", { name: "Buat kelas", exact: true })
    .click();
  await teacher.waitForURL(/#\/course\//);
  const cid = new URL(teacher.url()).hash.split("/")[2];
  await createLesson(
    teacher,
    cid,
    "Mengenal input dan output",
    `# Program dimulai dari sebuah ide\n\nProgram menerima **input**, mengolahnya, lalu menghasilkan **output**. Pada latihan ini, kita akan menjumlahkan dua bilangan.\n\n## Membaca dua bilangan\n\nDi C, gunakan \`scanf\`. Di C++, gunakan \`std::cin\`. Pisahkan kedua bilangan dengan spasi atau baris baru.\n\n\`\`\`cpp\n#include <iostream>\nint main() {\n  int a, b;\n  std::cin >> a >> b;\n  std::cout << a + b << "\\n";\n}\n\`\`\`\n\n## Sebelum melanjutkan\n\n- Perhatikan tipe data yang dipakai.\n- Output cukup berupa hasil penjumlahan.\n- Jangan tambahkan prompt input pada jawaban latihan.\n\nCoba ubah inputnya: apa yang terjadi jika salah satu bilangan bernilai negatif?`,
  );
  await createLesson(
    teacher,
    cid,
    "Refleksi: pahami hasilnya",
    "## Kamu sudah menulis program pertamamu\n\nCoba jelaskan dengan bahasamu sendiri: bagaimana dua bilangan dari input berubah menjadi satu hasil?\n\nKamu dapat kembali ke latihan untuk mencoba nilai nol dan bilangan negatif.",
  );
  await teacher.goto(`${base}/#/problem-editor/new/${cid}`);
  await teacher.locator("#content-title").fill("Jumlah dua bilangan");
  await teacher
    .locator("#statement")
    .fill(
      "Baca dua bilangan bulat antara -1000000 dan 1000000. Cetak jumlahnya tanpa teks tambahan.\n\n**Contoh:** input `2 3` menghasilkan output `5`.",
    );
  await teacher.locator("#case-input-0").fill("2 3\n");
  await teacher.locator("#case-expected-0").fill("5\n");
  await teacher.getByRole("button", { name: "Tambah kasus" }).click();
  await teacher.locator("#case-input-1").fill("-7 -8\n");
  await teacher.locator("#case-expected-1").fill("-15\n");
  await teacher.locator("#reference-c17").fill(C);
  await teacher.locator("#reference-cpp17").fill(CPP);
  await teacher.getByRole("button", { name: "Uji kunci", exact: true }).click();
  await teacher
    .getByText("Kunci lolos pengujian", { exact: true })
    .waitFor({ timeout: 150000 });
  await teacher.getByRole("button", { name: "Terbitkan", exact: true }).click();
  await teacher
    .locator(".editor-aside .badge")
    .filter({ hasText: "TERBIT" })
    .waitFor();
  const problemVersion = new URL(teacher.url()).hash.split("/")[2];
  console.log(
    "PASS browser: teacher creates materials, private test cases, and validates/publishes C/C++ references",
  );

  await teacher.goto(`${base}/#/path-editor/new/${cid}`);
  await teacher.locator("#content-title").fill("Dasar Pemrograman C/C++");
  await teacher
    .locator("#path-description")
    .fill(
      "Mulai dari input dan output, tulis program pertamamu, lalu uji pemahaman melalui latihan yang terarah.",
    );
  await teacher
    .locator("#step-target-0")
    .selectOption({ label: "Mengenal input dan output · v1" });
  await teacher.getByRole("button", { name: "Tambah langkah" }).click();
  await teacher.locator("#step-kind-1").selectOption("exercise");
  await teacher.getByRole("button", { name: "Tambah langkah" }).click();
  await teacher
    .locator("#step-target-2")
    .selectOption({ label: "Refleksi: pahami hasilnya · v1" });
  await teacher.locator('[name="step-required-2"]').uncheck();
  await teacher.getByRole("button", { name: "Terbitkan", exact: true }).click();
  await teacher
    .locator(".editor-aside .badge")
    .filter({ hasText: "TERBIT" })
    .waitFor();
  const pathVersion = new URL(teacher.url()).hash.split("/")[2];
  const pathInfo = await json(
    await teacherContext.request.get(
      `${base}/author/path-versions/${pathVersion}`,
    ),
  );
  await teacher.screenshot({
    path: "artifacts/web-studio.png",
    fullPage: true,
  });
  console.log(
    "PASS browser: learning-path builder, published references, ordering, and optional step",
  );

  const studentContext = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    }),
    student = await studentContext.newPage();
  watch(student);
  await login(student, studentName, password);
  await student.goto(`${base}/#/classes`);
  await student.locator("#class-search").fill("no_matching_class_" + suffix);
  await student
    .getByText("Tidak ada kelas yang sesuai pencarian.", { exact: true })
    .waitFor();
  await student.locator("#class-search").fill("");
  assert.equal(await student.locator('[data-action="enroll-path"]').count(), 0);
  await student
    .locator(`[data-course-id="${cid}"]`)
    .getByRole("link", { name: "Buka kelas" })
    .click();
  await student
    .getByRole("heading", { name: "Learning path di kelas ini", exact: true })
    .waitFor();
  await student.screenshot({
    path: "artifacts/web-class-paths.png",
    fullPage: true,
  });
  await student
    .locator(`[data-action="enroll-path"][data-id="${pathInfo.path_id}"]`)
    .click();
  await student.waitForURL(/#\/learning\//);
  const eid = new URL(student.url()).hash.split("/")[2];
  let e = await enrollment(studentContext, eid);
  assert(e.steps[1].locked && e.steps[2].locked);
  const bypass = await studentContext.request.post(`${base}/submissions`, {
    headers: { "X-CSRF-Token": await csrf(studentContext) },
    data: {
      problem_version_id: problemVersion,
      language: "cpp17",
      source: CPP,
      enrollment_id: eid,
      path_step_id: e.steps[1].id,
    },
  });
  assert.equal(bypass.status(), 403);
  assert.equal(
    (
      await studentContext.request.get(`${base}/problems/${problemVersion}`)
    ).status(),
    403,
  );
  await student
    .locator(`[data-action="open-step"][data-id="${e.steps[0].id}"]`)
    .click();
  await student
    .locator(".prose")
    .getByRole("heading", { name: "Program dimulai dari sebuah ide" })
    .waitFor();
  await student.screenshot({
    path: "artifacts/web-reading.png",
    fullPage: true,
  });
  await student
    .getByRole("button", { name: "Selesai membaca", exact: true })
    .click();
  await student.locator("#code-editor").waitFor();
  await student.locator(`.breadcrumb a[href="#/classes/${cid}"]`).waitFor();
  e = await enrollment(studentContext, eid);
  assert.equal(e.progress, 50);
  assert(e.steps[2].locked);
  console.log(
    "PASS browser: enrollment, prerequisite lock, direct-API rejection, and reading completion",
  );

  await student.locator("#code-language").selectOption("cpp17");
  await student.locator("#code-editor").fill(CPP);
  await student.locator("#custom-input").fill("40 2\n");
  await student.getByRole("button", { name: "Jalankan", exact: true }).click();
  await waitResult(student, "Program berhasil dijalankan");
  assert.equal(
    (await student.locator("#judge-result pre").last().textContent()).trim(),
    "42",
  );
  assert.equal((await enrollment(studentContext, eid)).progress, 50);
  await student
    .locator("#code-editor")
    .fill("#include <iostream>\nint main(){std::cout<<0;}");
  await student
    .getByRole("button", { name: "Kirim jawaban", exact: true })
    .click();
  await waitResult(student, "Hasil belum sesuai");
  assert.equal((await enrollment(studentContext, eid)).progress, 50);
  await student.locator("#code-editor").fill(CPP);
  await student
    .getByRole("button", { name: "Kirim jawaban", exact: true })
    .click();
  await waitResult(student, "Jawaban benar");
  await student.locator('.learn-outline progress[value="100"]').waitFor();
  e = await enrollment(studentContext, eid);
  assert(e.complete && !e.steps[2].locked);
  assert.equal(
    await student
      .locator('.learn-outline [data-id="' + e.steps[2].id + '"]')
      .isDisabled(),
    false,
  );
  await student.screenshot({
    path: "artifacts/web-exercise.png",
    fullPage: true,
  });
  assert.deepEqual(
    await student.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage).filter((k) =>
        /token|password|session/i.test(k),
      ),
    })),
    { local: [], session: [] },
  );
  await student.reload();
  await student.locator("#code-language").waitFor();
  assert.equal(await student.locator("#code-language").inputValue(), "cpp17");
  assert.equal(await student.locator("#code-editor").inputValue(), CPP);
  await student.goto(`${base}/#/learning/${eid}`);
  await student
    .getByRole("heading", { name: "Jalur belajar selesai." })
    .waitFor();
  assert(e.completed_at && e.completion_seconds >= 0 && e.score === 100);
  const finalDuration = e.completion_seconds;
  await student.locator(".learning-duration").waitFor();
  assert.equal(await student.locator('a[href^="#/practice"]').count(), 0);
  assert.equal(await student.locator(".embedded-leaderboard").count(), 0);
  await student.locator(`.breadcrumb a[href="#/classes/${cid}"]`).click();
  await student
    .getByRole("heading", { name: "Leaderboard kelas", exact: true })
    .waitFor();
  await student.getByRole("table", { name: "Leaderboard" }).waitFor();
  await student
    .locator(".leaderboard-self")
    .filter({ hasText: studentName })
    .waitFor();
  await student.screenshot({
    path: "artifacts/web-leaderboard-class.png",
    fullPage: true,
  });
  assert.equal(
    (await enrollment(studentContext, eid)).completion_seconds,
    finalDuration,
  );
  await student.goto(`${base}/#/leaderboard`);
  await student
    .getByRole("heading", { name: "Leaderboard keseluruhan" })
    .waitFor();
  await student.locator(".leaderboard-self").waitFor();
  assert.equal(
    await student.locator("#leaderboard-path, #leaderboard-version").count(),
    0,
  );
  assert.equal(
    await student
      .getByRole("columnheader", { name: "Latihan wajib", exact: true })
      .count(),
    0,
  );
  await student.setViewportSize({ width: 390, height: 844 });
  await student.screenshot({
    path: "artifacts/web-leaderboard-mobile.png",
    fullPage: true,
  });
  assert(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
    "Leaderboard overflows on mobile",
  );
  await student.setViewportSize({ width: 1440, height: 1000 });
  for (const viewer of [teacher, admin]) {
    await viewer.goto(`${base}/#/classes/${cid}`);
    await viewer.getByRole("table", { name: "Leaderboard" }).waitFor();
    await viewer
      .getByRole("cell", { name: studentName, exact: true })
      .waitFor();
    await viewer.goto(`${base}/#/leaderboard`);
    await viewer
      .getByRole("heading", { name: "Leaderboard keseluruhan" })
      .waitFor();
  }
  await student.goto(`${base}/#/practice/sum-v1`);
  await student.waitForURL(/#\/classes$/);
  console.log(
    "PASS browser: class/global leaderboards for all three roles, fixed duration, standalone route removed, mobile layout",
  );
  await student.goto(`${base}/#/dashboard`);
  await student
    .getByRole("heading", { name: `Halo, ${studentName}.` })
    .waitFor();
  await student.screenshot({
    path: "artifacts/web-dashboard.png",
    fullPage: true,
  });
  await student.setViewportSize({ width: 390, height: 844 });
  await student.screenshot({
    path: "artifacts/web-mobile.png",
    fullPage: true,
  });
  assert(
    await student.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
    "Mobile page overflows horizontally",
  );
  console.log(
    "PASS browser: real run/wrong/correct grading, progress unlock, persistence, and responsive mobile layout",
  );

  const extraPath = await json(await teacherContext.request.post(`${base}/author/courses/${cid}/paths`, {
    headers: {"X-CSRF-Token": await csrf(teacherContext)},
    data: {title:"Path progres parsial", languages:["c17","cpp17"], sequential:true,
      steps: pathInfo.steps.filter(s => s.kind === "reading").map(s => ({key:s.key,title:s.title,module:s.module,kind:s.kind,required:true,prerequisites:[],lesson_version_id:s.lesson_version_id}))}
  }));
  const classProgress = async () => json(await teacherContext.request.get(`${base}/author/courses/${cid}/progress`));
  assert.equal((await classProgress())[0].progress, 100, "Draft path must not reduce progress");
  await json(await teacherContext.request.post(`${base}/author/path-versions/${extraPath.id}/publish`, {
    headers:{"X-CSRF-Token":await csrf(teacherContext)},data:{edit_revision:1}
  }));
  assert.equal((await classProgress())[0].progress, 50, "Unstarted published path counts as zero");
  const extraEnrollment = await json(await studentContext.request.post(`${base}/paths/${extraPath.path_id}/enroll`, {
    headers:{"X-CSRF-Token":await csrf(studentContext)}
  }));
  await json(await studentContext.request.post(`${base}/enrollments/${extraEnrollment.id}/steps/${extraEnrollment.steps[0].id}/complete`, {
    headers:{"X-CSRF-Token":await csrf(studentContext)}
  }));
  assert.equal((await classProgress())[0].progress, 75, "One complete and one half-complete path must yield 75%");
  assert.equal((await classProgress()).length,1);
  await teacher.goto(`${base}/#/course/${cid}/progress`);
  await teacher.getByRole("cell", { name: new RegExp(studentName) }).waitFor();
  await teacher.getByRole("cell", { name: /75%/ }).waitFor();
  await teacher
    .getByRole("columnheader", { name: "Total lama pengerjaan" })
    .waitFor();
  assert.equal(await teacher.getByRole("columnheader", {name: "Jalur belajar", exact:true}).count(), 0);
  assert.equal(await teacher.getByRole("link", {name: "Kiriman kode", exact:true}).count(), 0);
  await teacher.screenshot({path: "artifacts/web-class-progress.png", fullPage:true});
  await teacher.goto(`${base}/#/course/${cid}/paths`);
  await teacher.locator(`a[href="#/path-progress/${pathInfo.path_id}"]`).click();
  await teacher.getByRole("cell", { name: new RegExp(studentName) }).waitFor();
  await teacher.getByRole("link", {name: "Detail pengerjaan"}).click();
  await teacher.getByRole("heading", {name: studentName, exact:true}).waitFor();
  await teacher.locator(".learning-duration").waitFor();
  await teacher.getByRole("button", {name: "Lihat kode", exact:true}).first().click();
  assert.equal(await teacher.locator(".code-detail").textContent(), CPP);
  await teacher.locator("#review-input").fill("20 22\n");
  await teacher.getByRole("button", {name: "Jalankan kode", exact:true}).click();
  await teacher.locator("#review-result").getByText("42", {exact:true}).waitFor({timeout:150000});
  const afterReplay = await enrollment(studentContext, eid);
  assert.equal(afterReplay.completion_seconds, finalDuration);
  assert.equal(afterReplay.progress, 100);
  await teacher.screenshot({path: "artifacts/web-instructor-code-review.png", fullPage:true});
  await teacher.getByRole("dialog").getByRole("button", {name:"Tutup", exact:true}).last().click();
  await teacher.setViewportSize({width:390,height:844});
  assert(await teacher.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Report mobile page overflows");
  await teacher.selectOption("#ui-locale", "en");
  await teacher.getByRole("heading", {name: "Work history", exact:true}).waitFor();
  assert.equal(await teacher.getByRole("heading", {name:studentName,exact:true}).count(),1);
  await teacher.selectOption("#ui-locale", "id");
  await teacher.getByRole("heading", {name:"Riwayat pengerjaan",exact:true}).waitFor();
  console.log("PASS browser: one participant per class progress row, per-path participant details, original C++ replay output 42, unchanged student result, English and mobile reports");
  await student.getByRole("button", { name: "Keluar", exact: true }).click();
  await student
    .getByRole("heading", { name: "Lanjutkan langkahmu." })
    .waitFor();
  assert.equal(
    (await studentContext.request.get(`${base}/auth/me`)).status(),
    401,
  );
  assert.deepEqual(errors, [], "Browser JavaScript/CSP errors");
  assert.deepEqual(
    foreign,
    [],
    "UI made unexpected third-party network requests",
  );
  console.log(
    "PASS browser: teacher progress report, logout revocation, no JavaScript/CSP errors, and local-only assets",
  );
  fs.writeFileSync(
    "artifacts/browser-result.json",
    JSON.stringify(
      {
        passed: true,
        groups: 8,
        base,
        screenshots: [
          "web-login.png",
          "web-studio.png",
          "web-reading.png",
          "web-exercise.png",
          "web-dashboard.png",
          "web-mobile.png",
          "web-leaderboard-class.png",
          "web-leaderboard-mobile.png",
          "web-class-progress.png",
          "web-instructor-code-review.png",
        ],
      },
      null,
      2,
    ),
  );
  await browser.close();
}
main().catch(async (error) => {
  let message = error.stack || error.message || String(error);
  for (const secret of secrets.filter(Boolean))
    message = message.split(secret).join("[redacted]");
  console.error(message);
  if (browser) await browser.close();
  process.exitCode = 1;
});
