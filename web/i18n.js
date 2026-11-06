const dictionaries = await Promise.all(
  ["id", "en"].map(async (locale) => {
    const response = await fetch(`/assets/locales/${locale}.json`);
    if (!response.ok) throw new Error("Unable to load UI language");
    return [locale, await response.json()];
  }),
);
const catalogs = Object.fromEntries(dictionaries);
export function getLocale() {
  try {
    return localStorage.getItem("kodelab:locale") === "en" ? "en" : "id";
  } catch {
    return "id";
  }
}
const locale = getLocale();
document.documentElement.lang = locale;
const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pattern = new RegExp(
  `(?<![\\p{L}\\p{N}_])(?:${Object.keys(catalogs.en)
    .sort((a, b) => b.length - a.length)
    .map(escapeRegex)
    .join("|")})(?![\\p{L}\\p{N}_])`,
  "gu",
);
export function tr(value) {
  if (locale === "id") return value;
  return value.replace(pattern, (key) => catalogs.en[key] || key);
}
// Translate source literals before interpolating dynamic content. User text,
// Markdown, code, output, names and API data are never sent to the translator.
export function ui(strings, ...values) {
  return strings.reduce(
    (html, part, index) =>
      html + tr(part) + (index < values.length ? values[index] : ""),
    "",
  );
}
export function localeControl() {
  return `<label class="locale-control"><span class="visually-hidden">${locale === "en" ? "Interface language" : "Bahasa antarmuka"}</span><select id="ui-locale" aria-label="${locale === "en" ? "Interface language" : "Bahasa antarmuka"}"><option value="id" ${locale === "id" ? "selected" : ""}>Indonesia</option><option value="en" ${locale === "en" ? "selected" : ""}>English</option></select></label>`;
}
export function setLocale(value) {
  if (!["id", "en"].includes(value)) return;
  try {
    localStorage.setItem("kodelab:locale", value);
  } catch {}
  location.reload();
}
const skipLink = document.querySelector(".skip-link");
if (skipLink) {
  skipLink.textContent = tr("Lewati ke konten");
  skipLink.addEventListener("click", event => {
    event.preventDefault();
    const main = document.getElementById("main");
    if (main) { main.tabIndex = -1; main.focus(); }
  });
}
const initial = document.querySelector(".initial-loading");
if (initial) initial.textContent = tr("Menyiapkan ruang belajar…");
