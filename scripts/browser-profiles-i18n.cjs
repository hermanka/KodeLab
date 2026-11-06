const { chromium } = require("playwright");
const fs = require("node:fs");
const crypto = require("node:crypto");
const assert = require("node:assert/strict");
const base = process.env.TEST_BASE_URL || "http://127.0.0.1:8000";
const env = Object.fromEntries(
  fs
    .readFileSync(".env", "utf8")
    .split(/\r?\n/)
    .filter((x) => x.includes("="))
    .map((x) => [x.slice(0, x.indexOf("=")), x.slice(x.indexOf("=") + 1)]),
);
const suffix = crypto.randomBytes(4).toString("hex");
const username = "profile_" + suffix,
  password = crypto.randomBytes(24).toString("hex"),
  nextPassword = crypto.randomBytes(24).toString("hex");
const secrets = [password, nextPassword, env.BOOTSTRAP_ADMIN_PASSWORD];
let browser, admin, cid;
const title = "Kelas Materi Indonesia " + suffix;
async function raw(ctx, path, method = "GET", data) {
  const csrf = (await ctx.cookies()).find(
    (c) => c.name === "judgement_csrf",
  )?.value;
  return ctx.request.fetch(base + path, {
    method,
    headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
    ...(data === undefined ? {} : { data }),
  });
}
async function json(ctx, path, method = "GET", data) {
  const response = await raw(ctx, path, method, data);
  assert(response.ok(), `HTTP ${response.status()} for ${method} ${path}`);
  return response.json();
}
async function main() {
  browser = await chromium.launch({ channel: "msedge", headless: true });
  admin = await browser.newContext();
  await json(admin, "/auth/login", "POST", {
    username: env.BOOTSTRAP_ADMIN_USERNAME,
    password: env.BOOTSTRAP_ADMIN_PASSWORD,
  });
  const course = await json(admin, "/courses", "POST", {
    title,
    description: "Materi ini tidak diterjemahkan.",
    is_public: true,
  });
  cid = course.id;
  const material = await json(admin, `/author/courses/${cid}/lessons`, "POST", {
    title: "Materi Pertama",
    body_markdown:
      "# Materi asli\nKelas dan materi ini tetap berbahasa Indonesia.",
  });
  await json(admin, `/author/lesson-versions/${material.id}/publish`, "POST", {
    edit_revision: 1,
  });
  const path = await json(admin, `/author/courses/${cid}/paths`, "POST", {
    title: "Materi Wajib",
    steps: [
      {
        key: "read",
        title: "Materi Pertama",
        kind: "reading",
        lesson_version_id: material.id,
      },
    ],
  });
  await json(admin, `/author/path-versions/${path.id}/publish`, "POST", {
    edit_revision: 1,
  });
  const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    }),
    page = await context.newPage(),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/#/register");
  await page.locator("#full-name").fill("Siswa Kelas Tetap");
  await page
    .locator("#registration-email")
    .fill(`profile_${suffix}@example.test`);
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page
    .getByRole("button", { name: "Buat akun peserta", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Halo, Siswa Kelas Tetap.", exact: true })
    .waitFor();
  await page.goto(base + "/#/profile");
  await page.locator("#profile-name").fill("Nama Baru Kelas");
  await page.locator("#profile-email").fill(`updated_${suffix}@example.test`);
  await page
    .getByRole("button", { name: "Simpan profil", exact: true })
    .click();
  await page.waitForFunction(() =>
    document
      .querySelector(".user-info")
      ?.textContent.includes("Nama Baru Kelas"),
  );
  await page.locator("#ui-locale").selectOption("en");
  await page
    .getByRole("heading", { name: "User profile", exact: true })
    .waitFor();
  assert.equal(await page.locator("html").getAttribute("lang"), "en");
  assert.equal(
    await page.locator("#profile-name").inputValue(),
    "Nama Baru Kelas",
  );
  assert.equal(await page.locator("#profile-username").inputValue(), username);
  await page.screenshot({
    path: "artifacts/web-profile-en.png",
    fullPage: true,
  });
  await page.goto(`${base}/#/classes/${cid}`);
  await page.getByRole("heading", { name: title, exact: true }).waitFor();
  await page
    .getByText("Materi ini tidak diterjemahkan.", { exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Start learning", exact: true })
    .click();
  await page.waitForURL(/#\/learning\//);
  const eid = new URL(page.url()).hash.split("/")[2];
  await page.getByRole("button", { name: /Materi Pertama/ }).click();
  await page
    .locator(".prose")
    .getByText("Kelas dan materi ini tetap berbahasa Indonesia.", {
      exact: true,
    })
    .waitFor();
  await page
    .getByRole("button", { name: "Finished reading", exact: true })
    .waitFor();
  await page.screenshot({
    path: "artifacts/web-material-en-ui.png",
    fullPage: true,
  });
  console.log(
    "PASS profiles: complete registration, profile edit, EN/ID catalogs and unchanged Indonesian names/materials",
  );
  const settings = await json(admin, `/courses/${cid}/settings`);
  await json(admin, `/courses/${cid}/settings`, "PATCH", {
    title,
    description: course.description,
    is_public: false,
    edit_revision: settings.edit_revision,
  });
  assert.equal((await raw(context, `/enrollments/${eid}`)).status(), 404);
  const invitation = await json(admin, `/courses/${cid}/invitation`, "POST");
  secrets.push(invitation.code);
  assert.equal(
    (await json(admin, `/courses/${cid}/settings`)).code,
    invitation.code,
  );
  assert.equal((await raw(context, `/courses/${cid}/settings`)).status(), 404);
  await page.goto(base + "/#/classes");
  await page
    .getByRole("button", { name: "Join with a code", exact: true })
    .click();
  await page.locator("#join-code").fill(invitation.code);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Join class", exact: true })
    .click();
  await page.waitForURL(`**/#/classes/${cid}`);
  assert.equal((await json(context, `/enrollments/${eid}`)).id, eid);
  await json(admin, `/courses/${cid}/archive`, "POST");
  assert.equal((await raw(context, `/courses/${cid}/learning`)).status(), 404);
  await page.goto(base + "/#/classes/archive");
  await page.waitForURL(/#\/classes$/);
  assert.equal(
    await page
      .getByRole("link", { name: "Archived classes", exact: true })
      .count(),
    0,
  );
  console.log(
    "PASS access: public membership cannot bypass private access; invite preserves enrollment; students cannot open archives",
  );
  await page.goto(base + "/#/profile");
  await page.locator("#ui-locale").selectOption("id");
  await page
    .getByRole("heading", { name: "Profil pengguna", exact: true })
    .waitFor();
  const second = await browser.newContext();
  await json(second, "/auth/login", "POST", { username, password });
  await page.locator("#current-password").fill("incorrect-password");
  await page.locator("#new-password").fill(nextPassword);
  await page.locator("#confirm-password").fill(nextPassword);
  await page
    .getByRole("button", { name: "Ubah password", exact: true })
    .click();
  await page
    .locator('[data-form="password"] .form-error')
    .filter({ hasText: "Password saat ini tidak sesuai." })
    .waitFor();
  await page.locator("#current-password").fill(password);
  await page
    .getByRole("button", { name: "Ubah password", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Lanjutkan langkahmu.", exact: true })
    .waitFor();
  assert.equal((await raw(second, "/auth/me")).status(), 401);
  assert.equal(
    (await raw(second, "/auth/login", "POST", { username, password })).status(),
    401,
  );
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(nextPassword);
  await page
    .getByRole("button", { name: "Masuk ke KodeLab", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Halo, Nama Baru Kelas.", exact: true })
    .waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS password: current-password verification, all sessions revoked, new login works, mobile and JavaScript checks pass",
  );
}
main()
  .catch((e) => {
    let message = e.stack || e.message;
    for (const secret of secrets.filter(Boolean))
      message = message.split(secret).join("[redacted]");
    console.error(message);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (admin && cid)
      try {
        await raw(admin, `/courses/${cid}`, "DELETE", {
          confirmation_title: title,
        });
      } catch {}
    if (browser) await browser.close();
  });
