# Windows: jalankan otomatis saat komputer menyala

**Cara A — folder Startup (paling sederhana, berjalan saat Anda login):**
1. Tekan `Win+R`, ketik `shell:startup`, Enter.
2. Klik kanan → *New → Shortcut* → arahkan ke `C:\PATH\KE\prototipe\start.bat`.

**Cara B — Task Scheduler (berjalan saat logon, dapat diatur ulang bila gagal):**
1. Buka *Task Scheduler* → *Create Task…*.
2. Tab *General*: nama `KredMikro Prototipe`; pilih *Run only when user is logged on*.
3. Tab *Triggers*: *New… → At log on*.
4. Tab *Actions*: *New… → Start a program* → Program: `C:\PATH\KE\prototipe\start.bat`; *Start in*: `C:\PATH\KE\prototipe`.
5. Tab *Settings*: centang *If the task fails, restart every 1 minute*.

Atau impor berkas `kredmikro_task.xml` (ubah path terlebih dahulu): *Action → Import Task…*.

**Dengan Docker Desktop:** aktifkan *Start Docker Desktop when you sign in*; layanan di `docker-compose.yml` memakai `restart: unless-stopped` sehingga hidup kembali otomatis.
