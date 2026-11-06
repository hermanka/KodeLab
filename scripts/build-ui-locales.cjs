/* Source-only UI catalogs. Dynamic values (including course content) never enter tr(). */
const fs = require("node:fs");
const pairs = `
Kelas|Classes
Kelas aktif|Active classes
Arsip kelas|Archived classes
Studio pengajar|Teacher studio
Ringkasan|Overview
Jalur belajar|Learning paths
Learning path di kelas ini|Learning paths in this class
Materi|Material
Latihan kode|Coding exercise
Latihan berhasil|Exercises passed
Riwayat kode|Submission history
Leaderboard kelas|Class leaderboard
Leaderboard keseluruhan|Overall leaderboard
Profil|Profile
Profil pengguna|User profile
Informasi profil|Profile information
Nama lengkap|Full name
Username login|Login username
Username login tetap. Nama lengkap digunakan sebagai nama tampilan.|Your login username stays the same. Your full name is your display name.
Kelola nama lengkap, email, dan keamanan akunmu.|Manage your full name, email, and account security.
Simpan profil|Save profile
Profil diperbarui.|Profile updated.
Ubah password|Change password
Password saat ini|Current password
Password baru|New password
Konfirmasi password baru|Confirm new password
Konfirmasi password belum sesuai.|Password confirmation does not match.
Password diubah. Silakan masuk kembali.|Password changed. Please sign in again.
Minimal 15 karakter. Semua sesi akan dicabut setelah password diubah; masuk kembali dengan password baru.|At least 15 characters. Changing your password signs out all sessions. Sign in again with your new password.
Masuk|Sign in
Masuk ke KodeLab|Sign in to KodeLab
Daftar|Register
Buat akun|Create account
Buat akun peserta|Create student account
Buat ruang belajarmu.|Create your learning space.
Lanjutkan langkahmu.|Continue your journey.
Sudah punya akun?|Already have an account?
Baru mulai belajar?|New here?
Kata sandi|Password
Kata sandi awal|Initial password
Masukkan kata sandi|Enter your password
Minimal 15 karakter|At least 15 characters
Minimal 15 karakter. Sampaikan hanya kepada pemilik akun.|At least 15 characters. Share only with the account owner.
Daftar sebagai peserta dan mulai jalur belajarmu.|Register as a student and begin your learning journey.
Masuk untuk melanjutkan jalur dan kode yang kamu kerjakan.|Sign in to continue your learning paths and code.
Mulai dari logika.|Start with logic.
Wujudkan|Bring it to life
dengan kode.|with code.
Langsung di browser|Right in your browser
Pelajari C dan C++ selangkah demi selangkah. Baca konsepnya, tulis programnya, dan temukan jawaban lewat percobaan.|Learn C and C++ step by step. Read the concepts, write your code, and explore through practice.
Baca. Tulis. Pahami.|Read. Code. Understand.
Satu konsep, satu latihan.|One concept, one exercise.
Bangun pemahaman lewat kode.|Build understanding through code.
Mulai dari sebuah kelas.|Start with a class.
Buka kelas, pilih learning path, lalu pelajari materi dan kerjakan latihan secara bertahap.|Open a class, choose a learning path, then work through its materials and exercises.
Buka kelas|Open class
Tinjau kelas|Review class
Kelola kelas|Manage class
Jelajahi kelas|Explore classes
Lanjutkan kelas|Continue class
Temukan kelas pertamamu|Find your first class
Kelas yang kamu ikuti|Your classes
Kelas publik dan kelas yang dapat kamu akses.|Public classes and classes you can access.
Kelas arsip yang dapat kamu tinjau.|Archived classes you can review.
Belum ada kelas arsip|No archived classes
Belum ada kelas tersedia|No classes available
Kelas arsip yang dapat kamu akses akan muncul di sini.|Archived classes you can access will appear here.
Kelas publik atau kelas yang ditugaskan kepadamu akan muncul di sini.|Public classes and classes assigned to you will appear here.
Cari kelas|Search classes
Cari kelas…|Search classes…
Tidak ada kelas yang sesuai pencarian.|No classes match your search.
Gabung dengan kode|Join with a code
Gabung ke kelas privat|Join a private class
Gabung kelas|Join class
Kode undangan 6 digit|6-digit invitation code
Minta kode aktif kepada pengajar. Bergabung ke kelas tidak memulai penghitung waktu learning path.|Ask your teacher for an active code. Joining a class does not start a learning path timer.
Berhasil bergabung ke kelas.|You have joined the class.
Belum ada learning path|No learning paths yet
Pengajar belum menerbitkan jalur belajar di kelas ini.|The teacher has not published a learning path in this class yet.
Pilih learning path di kelas ini untuk mulai belajar atau melanjutkan progresmu.|Choose a learning path in this class to start or continue learning.
Temukan learning path, pelajari materi, dan kerjakan latihan di dalam kelas ini.|Discover learning paths, study materials, and complete exercises in this class.
Tinjau kembali materi dan progres yang tersimpan.|Review your saved materials and progress.
Kelas publik|Public class
Kelas privat|Private class
Kelas diarsipkan|Archived class
Jalur diikuti|Paths joined
Jalur selesai|Paths completed
Nilai total|Total score
Nilai|Score
Peringkat|Rank
Peserta|Student
Pengajar|Teacher
Administrator|Administrator
Administrasi|Administration
Peran|Role
Peran baru|New role
Peran di kelas|Class role
Waktu|Time
Waktu penyelesaian|Completion time
Lama pengerjaan|Elapsed time
Lama pengerjaan:|Elapsed time:
Belum selesai|Not completed
selesai|completed
berjalan|in progress
hari|days
jam|hours
menit|minutes
detik|seconds
Jalur|Path
jalur|path
jalur belajar|learning path
langkah|steps
langkah wajib|required steps
langkah wajib selesai.|required steps completed.
langkah wajib sudah kamu selesaikan. Luangkan waktu untuk langkah berikutnya.|required steps completed. Make time for your next step.
dari|of
Kamu mengikuti versi|You are following version
. Progres tersimpan di akunmu.|. Your progress is saved to your account.
VERSI|VERSION
Versi|Version
Versi terbit|Published version
JALUR BELAJAR|LEARNING PATH
JALUR SELESAI|PATH COMPLETED
Materi referensi|Reference material
Lanjutkan belajar|Continue learning
Lanjutkan langkah|Continue step
Langkah berikutnya|Next step
Lihat jalur|View path
Mulai belajar|Start learning
Tinjau kembali|Review
Selesai membaca|Finished reading
Konfirmasi setelah kamu selesai membaca.|Confirm after you finish reading.
Pemahamanmu akan diuji pada latihan berikutnya.|The next exercise will test your understanding.
Jalur belajar selesai.|Learning path completed.
Seluruh langkah wajib sudah kamu tuntaskan. Kamu dapat meninjau kembali materi dan latihan kapan saja.|You have completed all required steps. You can review the materials and exercises at any time.
Hanya jawaban benar yang menyelesaikan latihan.|Only an accepted answer completes an exercise.
Wajib|Required
Opsional|Optional
Selesaikan prasyarat|Complete prerequisites
Langkah|Step
Langkah wajib|Required steps
Nama jalur belajar|Learning path name
Judul langkah|Step title
Judul|Title
Judul materi|Material title
Judul soal|Problem title
Isi materi|Material body
Pernyataan soal|Problem statement
Deskripsi|Description
Deskripsi kelas|Class description
Nama kelas|Class name
Pengaturan|Settings
Pengaturan kelas|Class settings
Simpan pengaturan|Save settings
Pengaturan kelas tersimpan.|Class settings saved.
Kelas publik · peserta dapat bergabung sendiri|Public class · students can join themselves
Kelas privat hanya dapat diakses anggota yang ditugaskan atau bergabung dengan kode undangan. Perubahan akses tidak menghapus anggota atau progres lama. Mengubah ke publik menonaktifkan kode undangan.|Private classes require an assignment or an invitation code. Existing members and progress are retained. Switching to public disables the invitation code.
Kode undangan|Invitation code
Kode undangan kelas|Class invitation code
Kode aktif ditampilkan di halaman ini untuk pemilik kelas dan admin.|The active code is displayed here for the class owner and administrators.
Kode enam digit berlaku 24 jam dan memberikan keanggotaan peserta, tanpa memulai learning path.|The six-digit code is valid for 24 hours and grants student membership without starting a learning path.
Buat kode undangan|Create invitation code
Ganti kode undangan|Replace invitation code
Buat kode undangan baru?|Create a new invitation code?
Buat kode|Create code
Nonaktifkan kode|Disable code
Nonaktifkan kode undangan?|Disable invitation code?
Kode undangan dinonaktifkan.|Invitation code disabled.
Kode undangan hanya tersedia untuk kelas privat.|Invitation codes are only available for private classes.
Kode undangan tidak valid, kedaluwarsa, atau sudah dinonaktifkan.|The invitation code is invalid, expired, or disabled.
Tidak ada kode undangan aktif.|No active invitation code.
Aktif hingga|Active until
Ubah dan simpan kelas sebagai privat untuk membuat kode undangan.|Switch and save the class as private to create an invitation code.
Kode sebelumnya tidak berlaku lagi. Kode baru dapat digunakan selama 24 jam. Bagikan hanya kepada calon anggota kelas.|The previous code will stop working. The new code will be valid for 24 hours. Share only with prospective class members.
Kode yang sudah dibagikan tidak dapat digunakan lagi. Anggota yang sudah bergabung tetap memiliki akses.|The shared code will no longer work. Existing members keep their access.
Peserta membuka Kelas → Gabung dengan kode.|Students open Classes → Join with a code.
Arsipkan kelas|Archive class
Arsipkan kelas?|Archive class?
Pulihkan kelas|Restore class
Pulihkan kelas?|Restore class?
Hapus kelas|Delete class
Hapus kelas permanen?|Permanently delete class?
Hapus permanen|Delete permanently
Ketik nama kelas untuk mengonfirmasi|Type the class name to confirm
Kelas diarsipkan.|Class archived.
Kelas dipulihkan.|Class restored.
Kelas dan seluruh data pembelajarannya dihapus.|The class and all its learning data have been deleted.
Kelas disembunyikan dari katalog dan menjadi hanya-baca. Konten, histori, nilai, serta progres tetap tersimpan dan kelas dapat dipulihkan.|The class will be hidden and become read-only. Content, history, scores, and progress are preserved; the class can be restored.
Kelas kembali aktif. Peserta dapat melanjutkan progres sebelumnya.|The class becomes active again. Students can continue their previous progress.
Seluruh materi, versi konten, bank soal, kunci, kasus uji, learning path, keanggotaan, histori kiriman, nilai, dan progres kelas ini akan dihapus permanen. Akun pengguna tetap ada. Tindakan ini tidak dapat dibatalkan.|All materials, versions, problems, reference solutions, test cases, learning paths, memberships, submissions, scores, and progress in this class will be deleted permanently. User accounts are retained. This cannot be undone.
Konten dan progres tersimpan. Pulihkan kelas untuk melanjutkan pembelajaran.|Content and progress are preserved. Restore the class to resume learning.
Kelas yang diarsipkan akan muncul di sini dan dapat dipulihkan atau dihapus.|Archived classes appear here and can be restored or deleted.
Kelas diarsipkan. Pulihkan kelas sebelum membuat perubahan.|Class archived. Restore it before making changes.
Kelas diarsipkan. Pulihkan kelas untuk membuat konten.|Class archived. Restore it before creating content.
Kelas diarsipkan. Pengerjaan baru dinonaktifkan.|Class archived. New work is disabled.
Nama kelas belum sesuai. Ketik nama kelas persis seperti yang ditampilkan.|The class name does not match. Type it exactly as displayed.
Masih ada penilaian atau uji kunci berjalan. Tunggu hingga selesai, lalu hapus kelas kembali.|Judging or reference validation is running. Wait for it to finish before deleting the class.
Rancang ruang belajarnya.|Design their learning space.
Kelola materi, latihan, dan jalur belajar untuk setiap kelas.|Manage materials, exercises, and learning paths for each class.
Buat kelas|Create class
Buat kelas baru|Create a new class
Bangun kelas pertamamu.|Create your first class.
Mulai dengan sebuah kelas, lalu tambahkan materi dan latihan.|Start with a class, then add materials and exercises.
Bank soal|Problem bank
Peserta|Student
Progres|Progress
Kiriman kode|Submissions
Konten kelas|Class content
Kembali ke kelas|Back to class
Materi, latihan, dan perkembangan peserta dalam satu tempat.|Materials, exercises, and student progress in one place.
Tambahkan anggota|Add member
Tambahkan anggota kelas|Add class members
Username akun|Account username
Penugasan pengajar hanya berlaku untuk akun dengan peran pengajar.|Teacher assignments require an account with the teacher role.
Tambahkan|Add
Cabut akses|Revoke access
Cabut akses kelas?|Revoke class access?
Anggota ini tidak dapat lagi mengakses kelas privat atau mengirim jawaban baru. Riwayat kode tetap tersimpan.|This member will lose access to the private class and cannot submit new answers. Submission history is retained.
Belum ada anggota tambahan.|No additional members yet.
Tambahkan peserta dengan username akun mereka. Pemilik kelas selalu memiliki akses.|Add students using their account usernames. The class owner always has access.
Belum ada konten|No content yet
Kelas ini diarsipkan dan hanya dapat ditinjau.|This class is archived and can only be reviewed.
Kelas ini tidak dapat kamu kelola.|You cannot manage this class.
Bahasa|Language
Bahasa jalur|Path languages
Bahasa yang diizinkan|Allowed languages
Jalankan|Run
Kirim jawaban|Submit answer
Input percobaan|Custom input
Masukkan input untuk mencoba program…|Enter input to test your program…
Kode program|Source code
Editor kode|Code editor
Kembalikan kode awal|Reset starter code
Tab untuk indentasi · Ctrl / ⌘ + Enter untuk menjalankan|Tab to indent · Ctrl / ⌘ + Enter to run
Draft kode tersimpan sementara di tab ini.|Code drafts are saved temporarily in this tab.
CONTOH INPUT|SAMPLE INPUT
CONTOH OUTPUT|SAMPLE OUTPUT
Jawaban benar|Accepted answer
Hasil belum sesuai|Wrong answer
Kesalahan kompilasi|Compilation error
Program berhenti dengan error|Runtime error
Batas waktu terlampaui|Time limit exceeded
Batas memori terlampaui|Memory limit exceeded
Keluaran terlalu banyak|Output limit exceeded
Program berhasil dijalankan|Program executed successfully
Mengompilasi dan menguji program…|Compiling and testing your program…
Menunggu giliran penilaian…|Waiting for judging…
Hasil akan muncul secara otomatis.|Results will appear automatically.
Penilaian sedang bermasalah|Judging service issue
Kode tersimpan. Gangguan layanan tidak diberi nilai nol.|Your code is saved. Infrastructure issues do not receive a zero score.
Pesan compiler|Compiler message
Pesan error|Error message
Output program|Program output
Output yang diharapkan|Expected output
Detail contoh terbuka|Public sample details
Hasil|Result
Jenis|Type
Jawaban|Answer
Percobaan|Test run
Lihat|View
Lihat kode|View code
Detail percobaan|Submission details
Lihat semua|View all
Lihat audit|View audit
Belum ada percobaan|No submissions yet
Mulai sebuah latihan untuk menulis kode pertamamu.|Start an exercise to write your first program.
Tinjau kode, hasil pengujian, dan proses belajarmu. Menampilkan hingga 100 kiriman terbaru.|Review your code, test results, and learning journey. Showing up to 100 recent submissions.
Setiap percobaan berarti.|Every attempt matters.
Gangguan layanan|Service issue
Diproses|Processing
Mengantre|Queued
Mencoba ulang|Retry pending
Belum ada kiriman.|No submissions yet.
Program yang dikerjakan peserta pada soal kelas ini akan muncul di sini.|Submissions for problems in this class appear here.
Perjalanan peserta akan tercatat di sini.|Student progress will appear here.
Progres muncul setelah peserta mengikuti jalur belajar yang diterbitkan.|Progress appears once students join a published learning path.
Belum ada peringkat|No rankings yet
Peringkat muncul setelah peserta mengikuti jalur dengan latihan wajib.|Rankings appear once students join a path with required exercises.
Leaderboard belum dapat dimuat|Unable to load leaderboard
Muat ulang halaman untuk mencoba kembali.|Reload the page to try again.
Akumulasi nilai dari kelas yang dapat kamu akses.|Total scores from the classes you can access.
Nilai kelas adalah jumlah nilai learning path dalam kelas ini.|The class score is the sum of learning path scores within this class.
Nilai keseluruhan adalah jumlah nilai learning path pada kelas yang dapat kamu akses.|The overall score sums learning path scores from classes you can access.
Kelas arsip tidak masuk peringkat keseluruhan.|Archived classes are excluded from the overall ranking.
Simpan|Save
Batal|Cancel
Tutup|Close
Tutup menu|Close menu
Buka menu|Open menu
Keluar|Sign out
Menu|Menu
Navigasi belajar|Learning navigation
Progres belajar|Learning progress
Statistik belajar|Learning statistics
Status kelas|Class status
Kembali ke ruang belajar untuk melanjutkan.|Return to your learning space to continue.
Ke ringkasan|Go to overview
Halaman tidak ditemukan|Page not found
Halaman belum dapat dibuka.|Unable to open this page.
Halaman ini khusus pengajar.|This page is restricted to teachers.
Coba lagi|Try again
Data|Data
Perubahan tersimpan.|Changes saved.
Sesi berakhir. Silakan masuk kembali.|Your session expired. Please sign in again.
Silakan masuk untuk melanjutkan.|Please sign in to continue.
Username atau kata sandi belum sesuai.|The username or password is incorrect.
Username tidak tersedia. Gunakan username lain.|Username unavailable. Choose another one.
Terlalu banyak percobaan. Silakan tunggu sebelum mencoba lagi.|Too many attempts. Please wait before trying again.
Layanan belum dapat memproses permintaan.|The service cannot process this request yet.
Selesaikan langkah prasyarat terlebih dahulu.|Complete the prerequisites first.
Latihan selesai setelah jawaban dinyatakan benar.|An exercise is completed after an accepted official answer.
Uji kunci|Validate reference solutions
Uji kunci untuk draft terbaru terlebih dahulu sebelum menerbitkan soal.|Validate the latest draft's reference solutions before publishing.
Draft telah berubah. Muat ulang sebelum menyimpan.|The draft has changed. Reload before saving.
Draft berubah. Simpan dan uji kunci kembali sebelum menerbitkan.|The draft changed. Save and validate it again before publishing.
Simpan draft|Save draft
Terbitkan|Publish
Tinjau|Review
Edit|Edit
Revisi|Revise
Buat revisi baru|Create a new revision
Arsipkan|Archive
Arsipkan konten|Archive content
Arsipkan konten?|Archive content?
Konten tidak akan tersedia untuk penggunaan baru. Riwayat dan versi yang sudah diikuti peserta tetap tersimpan.|Content will no longer be available for new use. Existing history and enrolled versions are preserved.
Konten berhasil diterbitkan.|Content published.
Draft tersimpan.|Draft saved.
Validasi kunci dimulai.|Reference validation started.
Kunci lolos pengujian|Reference validation passed
Kunci belum lolos|Reference validation failed
Kunci lolos. Soal siap diterbitkan.|Reference solutions passed. The problem is ready to publish.
Kunci belum lolos. Tinjau hasil pengujian.|Reference validation failed. Review the test results.
Validasi mengalami gangguan. Draft dapat diuji ulang.|Validation encountered a service issue. You can validate the draft again.
Validasi berlangsung|Validation in progress
Gangguan validasi|Validation service issue
Pratinjau tersimpan|Saved preview
Solusi acuan · privat|Reference solution · private
Solusi ini diuji di sandbox dan tidak ditampilkan kepada peserta.|This solution runs in the sandbox and is never shown to students.
Kasus uji|Test cases
Tambah kasus|Add test case
Contoh terbuka|Public sample
Batas eksekusi|Execution limits
Memori (MiB)|Memory (MiB)
Waktu per kasus (detik)|Time per case (seconds)
Perubahan draft membatalkan hasil uji sebelumnya.|Changing the draft invalidates previous validation.
Minimal satu contoh terbuka. Gunakan kasus tersembunyi untuk menguji variasi jawaban.|Provide at least one public sample. Use hidden cases to test a range of answers.
Maksimal 10 kasus uji.|A maximum of 10 test cases is allowed.
Sisakan minimal satu kasus uji.|Keep at least one test case.
Susunan langkah|Step order
Tambah langkah|Add step
Hapus langkah|Remove step
Naikkan langkah|Move step up
Turunkan langkah|Move step down
Langkah baru|New step
Langkah tanpa judul|Untitled step
Modul|Module
Prasyarat|Prerequisites
Prasyarat tambahan|Additional prerequisites
Pilih konten…|Choose content…
Buka langkah secara berurutan|Unlock steps sequentially
Langkah wajib sebelumnya menjadi prasyarat otomatis. Langkah opsional tidak menghalangi kelulusan.|Previous required steps automatically become prerequisites. Optional steps do not block completion.
Maksimal 60 langkah per jalur.|A maximum of 60 steps per path is allowed.
Sisakan minimal satu langkah.|Keep at least one step.
Ctrl / ⌘ untuk memilih beberapa.|Use Ctrl / ⌘ to select multiple items.
Referensi sebelumnya (periksa ketersediaan)|Previous reference (check availability)
Terbitkan materi atau soal di kelas ini sebelum menyusun jalur belajar.|Publish material or problems in this class before building a learning path.
Konten terbit|Published content
Bahasa jalur|Path languages
Simpan peran|Save role
Ubah peran|Change role
Ubah peran akun|Change account role
Nonaktifkan|Deactivate
Aktifkan|Activate
Status akun diperbarui.|Account status updated.
Kelola akses dengan tepat.|Manage access carefully.
Buat akun pengajar dan peserta, atur peran, atau cabut akses akun.|Create teacher and student accounts, set roles, or revoke account access.
Perubahan izin mencabut seluruh sesi akun terkait. Akunmu sendiri tidak dapat diubah melalui tindakan ini.|Permission changes revoke all sessions for the account. You cannot change your own account here.
Seluruh sesi akun akan dicabut setelah perubahan.|All account sessions will be revoked after this change.
Jejak perubahan.|Change history.
Catatan tindakan sensitif tanpa menyertakan kata sandi atau isi kunci.|A record of sensitive actions without passwords or reference code.
Objek|Object
Tindakan|Action
Status|Status
Aktif|Active
Nonaktif|Inactive
Arsip|Archived
Terbit|Published
Selesai|Completed
MengujI kunci|Validating references
materi|material
soal|problem
latihan|exercises
tersedia|available
belum siap|not ready
Halo,|Hello,
Kamu|You
Temukan kelas, pilih jalur belajar di dalamnya, lalu pelajari C dan C++ selangkah demi selangkah.|Find a class, choose a learning path, and learn C and C++ step by step.
Pemahaman dimulai dari mencoba.|Understanding begins with practice.
Setiap baris kode adalah satu langkah menuju pemahaman baru.|Every line of code is a step toward understanding.
Kelas sedang disiapkan|Classes are being prepared
Pengajar akan menyediakan kelas dan jalur belajar di sini.|Teachers will provide classes and learning paths here.
Bangun pemahaman pemrograman melalui materi dan latihan bertahap.|Build programming skills through structured materials and exercises.
Satu jalur. Banyak kemajuan.|One path. Many achievements.
Simpan draft dan uji kuncinya sebelum menerbitkan.|Save the draft and validate its reference solutions before publishing.
Versi terbit tersimpan. Buat revisi untuk mengubahnya.|The published version is preserved. Create a revision to make changes.
Pastikan urutan dan prasyarat sesuai tujuan belajarnya.|Check the sequence and prerequisites against your learning objectives.
Tinjau materi sebelum membagikannya ke peserta.|Review the material before sharing it with students.
Penjelasan yang jelas membuat konsep lebih mudah dipahami.|Clear explanations make concepts easier to understand.
Pisahkan soal yang dibaca peserta dari kunci penilaian privat.|Keep the student-facing problem separate from its private reference solutions.
Hubungkan materi dan latihan menjadi perjalanan yang terarah.|Connect materials and exercises into a guided journey.
Materi pertama dimulai di sini.|Your first material starts here.
Siapkan latihan untuk peserta.|Prepare exercises for your students.
Susun perjalanan belajarnya.|Build their learning journey.
Buat draft, tinjau isinya, kemudian terbitkan saat sudah siap.|Create a draft, review it, and publish when ready.
Gabungkan materi dan soal yang sudah terbit menjadi jalur belajar.|Combine published materials and problems into a learning path.
Gunakan Markdown untuk judul, daftar, dan blok kode. HTML aktif tidak dijalankan.|Use Markdown for headings, lists, and code blocks. Active HTML is not executed.
Markdown didukung. Hindari menaruh kunci privat di pernyataan soal.|Markdown is supported. Keep private reference solutions out of the problem statement.
Apa yang akan dipahami peserta setelah jalur ini?|What will students understand after this path?
Jelaskan tugas, format input/output, dan batas nilai…|Describe the task, input/output format, and constraints…
Contoh: Pemrograman dasar|Example: Programming fundamentals
Contoh: Mengenal input dan output|Example: Understanding input and output
Contoh: Jumlah dua bilangan|Example: Sum of two integers
Contoh: Dasar pemrograman C/C++|Example: C/C++ fundamentals
Contoh: 012345|Example: 012345
Nama lengkap dan email wajib diisi.|Full name and email are required.
Nama lengkap tidak boleh kosong.|Full name cannot be blank.
Email sudah digunakan.|Email is already in use.
Password saat ini tidak sesuai.|Current password is incorrect.
Password baru harus berbeda.|New password must differ from your current password.
Untuk kelas privat, masukkan kode undangan atau hubungi pengajar untuk penugasan.|For private classes, enter an invitation code or ask your teacher for an assignment.
`;
const en = {};
const additional = {
"Plugin pada soal terbit dikunci. Buat revisi untuk memilih plugin lain, lalu simpan dan uji kunci kembali.": "The judge on a published problem is locked. Create a revision to select another plugin, then save and validate the reference solutions again.",
"Plugin aktif:": "Active plugins:",
"Ganti plugin melalui revisi": "Change plugin in a revision",
  "Versi tervalidasi:": "Validated version:",
  "Lewati ke konten": "Skip to content",
  "Menyiapkan ruang belajar…": "Preparing your learning space…",
  "KodeLab — Belajar C & C++": "KodeLab — Learn C & C++",
  Buat: "Create",
  Akun: "Account",
  "KodeLab beranda": "KodeLab home",
  "Kode lama tidak dapat ditampilkan. Ganti kode undangan untuk menampilkan kode baru.":
    "The old code cannot be displayed. Replace the invitation code to display a new one.",
  "BELAJAR DENGAN MENCOBA": "LEARN THROUGH PRACTICE",
  "RUANG BELAJAR UNTUK RASA INGIN TAHU": "A SPACE FOR CURIOUS MINDS",
  "BANGUN FONDASI YANG KUAT": "BUILD A STRONG FOUNDATION",
  "RUANG BELAJAR": "LEARNING SPACE",
  "RUANG BELAJARMU": "YOUR LEARNING SPACE",
  "TEMUKAN RUANG BELAJARMU": "FIND YOUR LEARNING SPACE",
  "AKUN PRIBADI": "PERSONAL ACCOUNT",
  "SELAMAT DATANG KEMBALI": "WELCOME BACK",
  "LANGKAH PERTAMAMU": "YOUR FIRST STEP",
  "JALUR BELAJARMU": "YOUR LEARNING PATH",
  "PROGRES BELAJARMU": "YOUR PROGRESS",
  "PERJALANAN BELAJAR": "LEARNING JOURNEY",
  PENGELOLAAN: "MANAGEMENT",
  "KELOLA KELAS": "MANAGE CLASS",
  "STUDIO KONTEN": "CONTENT STUDIO",
  "PUBLIKASI KONTEN": "CONTENT PUBLICATION",
  "KEMAJUAN BERSAMA": "PROGRESS TOGETHER",
  "LANJUTKAN DARI SINI": "CONTINUE HERE",
  "CATATAN PERCOBAANMU": "YOUR SUBMISSION RECORD",
  "// setiap langkah dimulai dari satu baris kode.":
    "// every journey starts with a line of code.",
  "Setiap jalur menyumbang maksimal 100 poin dari latihan wajib Accepted dan dihitung sekali sesuai versi enrollment. Jalur arsip dan jalur tanpa latihan wajib tidak menambah nilai. Nilai sama diurutkan berdasarkan total waktu penyelesaian tercepat. Durasi final tersedia setelah seluruh jalur yang menyumbang nilai selesai; peserta yang belum selesai berada setelah peserta dengan durasi final pada nilai yang sama. Nilai dan durasi identik berbagi peringkat. Waktu termasuk jeda sejak enrollment.":
    "Each path contributes up to 100 points from accepted required exercises, counted once using the enrolled version. Archived paths and paths without required exercises do not add points. Equal scores are ordered by the shortest total completion time. Time becomes final when all contributing paths are completed; unfinished students follow those with final times at the same score. Equal scores and times share a rank. Time includes breaks since enrollment.",
  "Pekerjaan masih diproses. Kamu dapat memeriksanya di":
    "Your submission is still being processed. You can check it in",
  "Seluruh langkah wajib selesai. Progres sudah tersimpan.":
    "All required steps are complete. Your progress is saved.",
  "Jawaban benar. Langkah berikutnya sudah terbuka.":
    "Accepted answer. The next step is unlocked.",
  "Pengaturan telah berubah. Muat ulang halaman sebelum menyimpan.":
    "Settings have changed. Reload the page before saving.",
  "(tidak ada output)": "(no output)",
  "Peserta dapat bergabung melalui jalur belajar yang terbit.":
    "Students can join through published learning paths.",
  "Kelas privat untuk anggota yang ditugaskan atau memiliki kode undangan.":
    "A private class for assigned or invited members.",
  "Kelas diarsipkan. Konten hanya dapat ditinjau sampai kelas dipulihkan.":
    "Class archived. Content is read-only until the class is restored.",
  "DOMjudge · belum diaktifkan": "DOMjudge · not enabled",
  "Bagikan kode ini kepada calon anggota. Kode juga tersedia di halaman Pengaturan dan berlaku hingga":
    "Share this code with prospective members. It is also available on the Settings page and is valid until",
  "3–40 huruf, angka, atau underscore. Diawali huruf.":
    "3–40 letters, digits, or underscores. Start with a letter.",
  "Email sudah digunakan.": "Email is already in use.",
  "Kode ini menggunakan fitur C++. Pilih compiler C++17 (G++) di editor jika tersedia, lalu jalankan kembali.":
    "This code uses C++ features. Select C++17 (G++) in the editor, if available, and run it again.",
  "C & C++ · Belajar interaktif berbahasa Indonesia":
    "C & C++ · Interactive learning",
  "KodeLab · Ruang belajar C & C++": "KodeLab · C & C++ learning space",
  "01 / Pahami konsep": "01 / Understand",
  "02 / Coba sendiri": "02 / Try it",
  "03 / Lanjutkan": "03 / Continue",
};
Object.assign(en, additional, {
  "Plugin penilaian": "Judging plugins",
  "Pasang paket penilai buatan sendiri dan kelola versinya.": "Install your own judging packages and manage their versions.",
  "Pasang plugin": "Install plugin",
  "Paket ZIP": "ZIP package",
  "Maksimal 256 KiB. Berisi plugin.json dan plugin.py di akar ZIP.": "Maximum 256 KiB. Contains plugin.json and plugin.py at the ZIP root.",
  "Saya mempercayai kode plugin ini untuk dijalankan pada server.": "I trust this plugin code to run on the server.",
  "Plugin baru dipasang dalam keadaan nonaktif. Versi baru tidak mengganti versi aktif secara otomatis.": "New plugins are installed inactive. New versions do not automatically replace the active version.",
  "Plugin terpasang": "Installed plugins",
  "Penilai custom bawaan selalu tersedia. Soal terbit dan pekerjaan antrean tetap memakai versi yang dikunci saat validasi.": "The built-in custom judge remains available. Published problems and queued jobs keep the version pinned during validation.",
  "Versi aktif": "Active version",
  "Terapkan versi": "Apply version",
  "Aktifkan": "Activate",
  "Hapus plugin": "Uninstall plugin",
  "Belum ada plugin tambahan.": "No additional plugins installed.",
  "Plugin yang masih dirujuk soal atau histori tidak dapat dihapus.": "Plugins referenced by problems or history cannot be uninstalled.",
  "Hapus plugin ini": "Uninstall this plugin",
  "Pengaturan plugin tersimpan.": "Plugin settings saved.",
  "Pilih ZIP maksimal 256 KiB dan setujui kepercayaan kode.": "Choose a ZIP up to 256 KiB and confirm that you trust its code.",
  "Paket tidak dapat dibaca.": "Unable to read package.",
  "Plugin terpasang. Aktifkan untuk menggunakannya.": "Plugin installed. Activate it to use it.",
  "Plugin dihapus.": "Plugin uninstalled.",
  "Akses administrator diperlukan.": "Administrator access required.",
  "Versi plugin dikunci saat validasi kunci. Perubahan penilai memerlukan validasi ulang.": "The plugin version is pinned during reference validation. Changing the judge requires revalidation.",
  "Plugin penilaian tidak tersedia. Aktifkan kembali atau hubungi administrator.": "Judging plugin unavailable. Reactivate it or contact an administrator.",
  "Versi plugin sudah terpasang. Gunakan nomor versi baru.": "Plugin version already installed. Use a new version number.",
  "Nonaktifkan plugin sebelum menghapusnya.": "Deactivate the plugin before uninstalling.",
  "Plugin masih digunakan oleh soal atau histori penilaian.": "The plugin is still referenced by problems or judging history.",
  "Paket plugin tidak valid. Periksa format API v1, isi ZIP, dan batas 256 KiB.": "Invalid plugin package. Check API v1 format, ZIP contents, and the 256 KiB limit.",
  "Pilih plugin penilaian yang aktif.": "Select an active judging plugin."
});
Object.assign(en, {
  "Learning path harus memiliki minimal satu langkah wajib sebelum diterbitkan.": "A learning path must have at least one required step before publication.",
  "Hasil peserta": "Participant results",
  "HASIL PESERTA": "PARTICIPANT RESULTS",
  "DETAIL PENGERJAAN": "WORK DETAILS",
  "Detail pengerjaan": "Work details",
  "Path selesai": "Paths completed",
  "Total lama pengerjaan": "Total time spent",
  "Progres kelas adalah rata-rata progres langkah wajib seluruh learning path terbit yang aktif. Path yang belum dimulai bernilai 0%.": "Class progress is the average required-step progress across all active published learning paths. Unstarted paths count as 0%.",
  "Peserta kelas dan riwayat belajarnya akan muncul di sini.": "Class participants and their learning history will appear here.",
  "Belum ada peserta.": "No participants yet.",
  "Halaman laporan": "Report pages",
  "Sebelumnya": "Previous",
  "Berikutnya": "Next",
  "Kembali ke learning path": "Back to learning paths",
  "Pengerjaan mengikuti versi learning path saat peserta mulai belajar.": "Work follows the learning path version from when the participant started.",
  "Sedang dikerjakan": "In progress",
  "Belum dimulai": "Not started",
  "Kembali ke daftar peserta": "Back to participants",
  "Riwayat pengerjaan": "Work history",
  "Peserta ini belum memulai learning path.": "This participant has not started the learning path.",
  "Jalankan ulang kode": "Run code again",
  "Eksekusi pengajar tidak mengubah nilai atau progres peserta.": "Instructor runs do not change participant scores or progress.",
  "Jalankan kode": "Run code",
  "Menjalankan kode…": "Running code…",
  "Eksekusi masih diproses. Coba lagi nanti.": "Execution is still being processed. Please check again later.",
});
for (const line of pairs.trim().split("\n")) {
  const [id, translated] = line.split("|");
  if (!translated) continue;
  en[id] = translated;
  en[id.toUpperCase()] = translated.toUpperCase();
}
const id = Object.fromEntries(Object.keys(en).map((key) => [key, key]));
fs.mkdirSync("web/locales", { recursive: true });
fs.writeFileSync("web/locales/id.json", JSON.stringify(id, null, 2) + "\n");
fs.writeFileSync("web/locales/en.json", JSON.stringify(en, null, 2) + "\n");
