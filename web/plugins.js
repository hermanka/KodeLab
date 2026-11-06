import {ui, tr} from "./i18n.js";
import {$, api, esc, badge, modal, closeModal, formFooter, formTask, refresh, toast, state} from "./core.js";

export async function pluginsPage() {
  if (state.user?.role !== "admin") throw new Error(tr("Akses administrator diperlukan."));
  const plugins = await api("/admin/judge-plugins");
  return ui`<div class="page-head"><div><div class="eyebrow">ADMINISTRASI</div><h1>Plugin penilaian</h1><p>Pasang paket penilai buatan sendiri dan kelola versinya.</p></div><a class="btn" href="#/admin">Kelola akun</a></div>
    <section class="panel"><h2>Pasang plugin</h2><form data-form="install-plugin" class="form-stack">
    <div class="field"><label for="plugin-package">Paket ZIP</label><input id="plugin-package" name="package" type="file" accept=".zip" required><small>Maksimal 256 KiB. Berisi plugin.json dan plugin.py di akar ZIP.</small></div>
    <label class="check"><input name="trusted" type="checkbox" required>Saya mempercayai kode plugin ini untuk dijalankan pada server.</label>
    <p class="help">Plugin baru dipasang dalam keadaan nonaktif. Versi baru tidak mengganti versi aktif secara otomatis.</p>
    <p class="form-error" role="alert"></p><div><button class="btn primary" type="submit">Pasang plugin</button></div></form></section>
    <section><h2>Plugin terpasang</h2><p class="subtle-note">Penilai custom bawaan selalu tersedia. Soal terbit dan pekerjaan antrean tetap memakai versi yang dikunci saat validasi.</p>
    ${plugins.length ? plugins.map(p => ui`<article class="panel" data-plugin-id="${esc(p.id)}"><div class="row spread wrap"><h3>${esc(p.name)}</h3>${badge(p.enabled ? tr("AKTIF") : tr("NONAKTIF"),p.enabled ? "active" : "")}</div><p>${esc(p.description)}</p><p class="mono">${esc(p.id)} · v${esc(p.version)}</p>
      <div class="field"><label for="plugin-version-${esc(p.id)}">Versi aktif</label><select id="plugin-version-${esc(p.id)}">${p.versions.map(v => ui`<option value="${esc(v.revision)}" ${v.revision===p.active_revision ? "selected" : ""}>${esc(v.version)}</option>`).join("")}</select></div>
      <div class="row wrap"><button class="btn" data-action="activate-plugin" data-id="${esc(p.id)}">${p.enabled ? tr("Terapkan versi") : tr("Aktifkan")}</button>${p.enabled ? ui`<button class="btn" data-action="deactivate-plugin" data-id="${esc(p.id)}">Nonaktifkan</button>` : ui`<button class="btn danger" data-action="uninstall-plugin" data-id="${esc(p.id)}">Hapus plugin</button>`}</div></article>`).join("") : ui`<p>Belum ada plugin tambahan.</p>`}</section>`;
}

export async function pluginAction(action, el) {
  if (!["activate-plugin", "deactivate-plugin", "uninstall-plugin"].includes(action)) return false;
  if (action === "uninstall-plugin") {
    modal(tr("Hapus plugin"), ui`<form data-form="uninstall-plugin" data-id="${esc(el.dataset.id)}" class="form-stack"><p>Plugin yang masih dirujuk soal atau histori tidak dapat dihapus.</p><label class="check"><input type="checkbox" name="confirm" required>Hapus plugin ini</label>${formFooter(tr("Hapus plugin"),true)}</form>`);
  } else {
    el.disabled = true;
    try {
      await api(`/admin/judge-plugins/${encodeURIComponent(el.dataset.id)}`, {method:"PATCH",body:{enabled:action==="activate-plugin",revision:$("#plugin-version-"+el.dataset.id).value}});
      toast(tr("Pengaturan plugin tersimpan.")); refresh();
    } finally { if(el.isConnected) el.disabled=false; }
  }
  return true;
}

export async function pluginSubmit(form) {
  if (!["install-plugin","uninstall-plugin"].includes(form.dataset.form)) return false;
  // Capture controls before formTask disables them.
  const file = form.elements.package?.files[0], trusted = form.elements.trusted?.checked;
  await formTask(form, async()=>{
    if(form.dataset.form==="install-plugin") {
      if(!file || file.size>262144 || !trusted) throw new Error(tr("Pilih ZIP maksimal 256 KiB dan setujui kepercayaan kode."));
      const encoded = await new Promise((resolve,reject)=>{
        const reader=new FileReader(); reader.onload=()=>resolve(String(reader.result).split(",")[1]);
        reader.onerror=()=>reject(new Error(tr("Paket tidak dapat dibaca."))); reader.readAsDataURL(file);
      });
      await api("/admin/judge-plugins", {method:"POST",body:{package_base64:encoded,trusted_code:true}});
      toast(tr("Plugin terpasang. Aktifkan untuk menggunakannya.")); refresh();
    } else {
      await api(`/admin/judge-plugins/${encodeURIComponent(form.dataset.id)}`, {method:"DELETE"});
      closeModal(); toast(tr("Plugin dihapus.")); refresh();
    }
  });
  return true;
}
