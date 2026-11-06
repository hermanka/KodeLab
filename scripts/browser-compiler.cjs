/* Compiler-selection regression; test credentials remain in memory. */
const { chromium, request } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const base = process.env.TEST_BASE_URL || "http://127.0.0.1:8000";
const env = Object.fromEntries(
  fs
    .readFileSync(path.join(__dirname, "../.env"), "utf8")
    .split(/\r?\n/)
    .filter((x) => x.includes("=") && !x.startsWith("#"))
    .map((x) => [x.slice(0, x.indexOf("=")), x.slice(x.indexOf("=") + 1)]),
);
const C =
  '#include <stdio.h>\nint main(void){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);return 0;}';
const CPP =
  '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<"\\n";}';
const password = crypto.randomBytes(24).toString("hex");
let browser;

async function run(page, selected, title, submit = false) {
  const endpoint = submit ? "/submissions" : "/runs";
  const [sent] = await Promise.all([
    page.waitForRequest(
      (r) => r.method() === "POST" && new URL(r.url()).pathname === endpoint,
    ),
    page
      .getByRole("button", {
        name: submit ? "Kirim jawaban" : "Jalankan",
        exact: true,
      })
      .click(),
  ]);
  assert.equal(
    sent.postDataJSON().language,
    selected,
    "Request language must match the visible selector",
  );
  await page
    .locator("#judge-result .result-title")
    .filter({ hasText: title })
    .waitFor({ timeout: 150000 });
  await page.locator(`#judge-result [data-compiler="${selected}"]`).waitFor();
}

async function main() {
  const admin = await request.newContext({ baseURL: base });
  const login = await admin.post("/auth/login", {
    data: {
      username: env.BOOTSTRAP_ADMIN_USERNAME,
      password: env.BOOTSTRAP_ADMIN_PASSWORD,
    },
  });
  assert(login.ok(), "Administrator login failed");
  const token = (await login.json()).access_token;
  const username = "compiler_" + crypto.randomBytes(4).toString("hex");
  const created = await admin.post("/admin/users", {
    headers: { Authorization: "Bearer " + token },
    data: { username, password, role: "student" },
  });
  assert.equal(created.status(), 201);
  await admin.dispose();
  browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage();
  await page.goto(base);
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Masuk ke KodeLab" }).click();
  await page
    .getByRole("heading", { name: `Halo, ${username}.`, exact: true })
    .waitFor();
  const context = page.context();
  const csrf = (await context.cookies()).find(
    (c) => c.name === "judgement_csrf",
  ).value;
  const paths = await (await context.request.get(base + "/paths")).json();
  const path = paths.find(
    (p) =>
      p.title === "Dasar Pemrograman C/C++" && p.languages.includes("cpp17"),
  );
  assert(path, "Run test:browser first to create the example learning path");
  const response = await context.request.post(
    `${base}/paths/${path.id}/enroll`,
    { headers: { "X-CSRF-Token": csrf } },
  );
  assert(response.ok());
  const e = await response.json();
  const exercise = e.steps.find((s) => s.kind === "exercise");
  assert(exercise);
  for (const step of e.steps) {
    if (step.id === exercise.id) break;
    if (step.kind === "reading") {
      const completed = await context.request.post(
        `${base}/enrollments/${e.id}/steps/${step.id}/complete`,
        { headers: { "X-CSRF-Token": csrf } },
      );
      assert(completed.ok());
    }
  }
  await page.goto(`${base}/#/learn/${e.id}/${exercise.id}`);
  await page.locator("#code-language").selectOption("cpp17");
  await page.locator("#code-editor").fill(CPP);
  await page.reload();
  await page.locator("#code-editor").waitFor();
  assert.equal(
    await page.locator("#code-language").inputValue(),
    "cpp17",
    "Reload must retain C++17",
  );
  assert.equal(await page.locator("#code-editor").inputValue(), CPP);
  assert.equal(
    await page.locator("#editor-filename").textContent(),
    "main.cpp",
  );
  await page.locator("#custom-input").fill("40 2\n");
  await run(page, "cpp17", "Program berhasil dijalankan");
  assert.equal(
    (await page.locator("#judge-result pre").last().textContent()).trim(),
    "42",
  );
  await run(page, "cpp17", "Jawaban benar", true);
  console.log(
    "PASS compiler: C++17 and its draft persist across reload; real G++ run/submission pass",
  );

  await page.locator("#code-language").selectOption("c17");
  await page.locator("#code-editor").fill(C);
  await run(page, "c17", "Jawaban benar", true);
  console.log("PASS compiler: C17 continues to compile and pass with GCC");

  // Browser form restoration can update the select without a change event.
  await page.locator("#code-editor").fill(CPP);
  await page.evaluate(() => {
    document.querySelector("#code-language").value = "cpp17";
  });
  await run(page, "cpp17", "Program berhasil dijalankan");
  assert.equal(
    await page.locator("#editor-filename").textContent(),
    "main.cpp",
  );
  console.log(
    "PASS compiler: submission uses the visible selection even without a change event",
  );

  await page.locator("#code-language").selectOption("c17");
  await page.locator("#code-editor").fill(CPP);
  await run(page, "c17", "Kesalahan kompilasi");
  await page.locator("#judge-result .compiler-hint").waitFor();
  console.log(
    "PASS compiler: explicit C17 is respected; C++ header mismatch has actionable guidance",
  );
  await page.getByRole("button", { name: "Keluar", exact: true }).click();
  await browser.close();
}

main().catch(async (error) => {
  let text = error.stack || error.message;
  for (const secret of [password, env.BOOTSTRAP_ADMIN_PASSWORD].filter(Boolean))
    text = text.split(secret).join("[redacted]");
  console.error(text);
  if (browser) await browser.close();
  process.exitCode = 1;
});
