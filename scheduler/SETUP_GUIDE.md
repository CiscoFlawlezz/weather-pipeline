# Automating the Phoenix CLI Collector — Complete Beginner Walkthrough

This guide turns your collector from something you run by hand into something
Windows runs by itself, three times a day.

**How to read this guide:** every step is ONE physical action — one click, one
key, one line to type. After most steps there is a **You should see:** line
telling you what appears if it worked. If you do not see it, stop and check the
Troubleshooting section (Part 10) before moving on.

You do **not** need to understand any of the code. You only need to follow the
steps in order.

**Legend**
- **Type:** `something` → type exactly what is between the backticks, then look
  for the expected result. Do **not** press Enter unless the step says "press
  **Enter**."
- **Click** → a single left mouse click.
- **Right-click** → a single right mouse click.
- **Double-click** → two quick left clicks.
- A word in **bold** that names a button or menu item is the thing you click.

---

## Part 0 — What you are building (read once, no actions)

Three scheduled tasks. All three run the **same** file, `run_cli_collection.bat`.

| Task name                       | Runs at (your local clock) | Why it exists                     |
|---------------------------------|----------------------------|-----------------------------------|
| `WeatherPipeline_CLI_Primary`   | 6:00 PM                     | The normal daily collection       |
| `WeatherPipeline_CLI_Amendment` | 11:30 PM                    | Catches corrected/amended reports |
| `WeatherPipeline_CLI_Final`     | 12:30 AM                    | Late-publication safety sweep     |

Running three times a day is safe. The collector remembers what it already
saved, so extra runs just say "already stored — skipped" and change nothing.
Nothing here ever overwrites your data.

You will do these parts in order:
1. Put the files in the right folders (Part 1)
2. Make sure the Python environment exists (Part 2)
3. Test the collector by hand (Part 3)
4. Import the three tasks into Task Scheduler (Part 4)
5. Test a task by hand (Part 5)
6. Turn on history so you can prove it ran (Part 6)
7. Find your logs (Part 7)
8. Verify everything with a checklist (Part 11)

---

## Part 1 — Put the files where they belong

Your project folder is `C:\Projects\weather-pipeline`. You have four new files
to place: one `.bat` file and a `scheduler` folder containing three `.xml`
files and this guide.

### 1.1 — Open your project folder

1. Press the **Windows key** on your keyboard (bottom-left, has the Windows
   logo). **You should see:** the Start menu open with a search box.
2. **Type:** `This PC`
3. Press **Enter**. **You should see:** a File Explorer window titled
   **This PC** with your drives listed.
4. Double-click the drive named **Local Disk (C:)** (or **Windows (C:)**).
   **You should see:** the contents of your C: drive.
5. Double-click the **Projects** folder. **You should see:** the contents of
   `Projects`, including a **weather-pipeline** folder.
6. Double-click **weather-pipeline**. **You should see:** files including
   `config.yaml`, `requirements.txt`, and folders like `collectors`, `core`,
   `storage`.

> If there is no `C:\Projects\weather-pipeline`, your project lives somewhere
> else. Note your real path — you will need it — and see Part 8.

Leave this File Explorer window open. This folder is called the **repo root**
for the rest of the guide.

### 1.2 — Place the wrapper file at the repo root

1. Find the file `run_cli_collection.bat` wherever you downloaded it (likely
   your **Downloads** folder).
2. Right-click `run_cli_collection.bat`. **You should see:** a menu.
3. Click **Cut**.
4. Click back into the **weather-pipeline** File Explorer window from step 1.1.
5. Right-click any empty white space inside that window. **You should see:** a
   menu.
6. Click **Paste**. **You should see:** `run_cli_collection.bat` now sitting in
   `weather-pipeline`, next to `config.yaml`.

### 1.3 — Place the scheduler folder at the repo root

1. Find the **scheduler** folder you downloaded (it contains three `.xml`
   files and this guide).
2. Right-click the **scheduler** folder. Click **Cut**.
3. Click back into the **weather-pipeline** window.
4. Right-click empty white space. Click **Paste**. **You should see:** a
   **scheduler** folder now inside `weather-pipeline`.
5. Double-click **scheduler** to open it. **You should see** exactly these
   files:
   - `WeatherPipeline_CLI_Primary.xml`
   - `WeatherPipeline_CLI_Amendment.xml`
   - `WeatherPipeline_CLI_Final.xml`
   - `SETUP_GUIDE.md` (this file)
6. Click the **back arrow** (top-left of the window, a left-pointing arrow) to
   return to the `weather-pipeline` folder.

When you are done, `weather-pipeline` should contain, among other things:
`run_cli_collection.bat` and a `scheduler` folder.

> **If your project is NOT at `C:\Projects\weather-pipeline`:** do Part 8 now to
> fix three paths, then come back to Part 2.

---

## Part 2 — Make sure the Python environment exists (one time)

The tasks run Python from a folder called `venv` inside your project. If you
have already set this up and run the collector before, **skip to Part 3**.
Otherwise do this once.

### 2.1 — Open Git Bash in the project folder

1. In the **weather-pipeline** File Explorer window, right-click any empty
   white space. **You should see:** a menu.
2. Click **Git Bash Here**. (On Windows 11 you may first need to click **Show
   more options** to see it.) **You should see:** a black terminal window whose
   last line looks like `rjkir@Kirbs MINGW64 /c/Projects/weather-pipeline`.

> No **Git Bash Here**? Use PowerShell instead: in File Explorer, click the
> address bar at the top, type `powershell`, press **Enter**. A blue window
> opens already pointed at the folder.

### 2.2 — Check whether venv already exists

1. Click into the terminal window so it has focus.
2. **Type:** `ls venv/Scripts/python.exe`
3. Press **Enter**.
   - **If you see** `venv/Scripts/python.exe` printed back → it already exists.
     **Skip to Part 3.**
   - **If you see** `No such file or directory` → continue to 2.3.

### 2.3 — Create the environment (only if 2.2 said "No such file")

1. **Type:** `py -m venv venv`
2. Press **Enter**. **You should see:** the prompt return after a few seconds
   with no error. A `venv` folder now exists.
3. **Type:** `venv/Scripts/python.exe -m pip install -r requirements.txt`
4. Press **Enter**. **You should see:** several lines of "Collecting..." and
   "Successfully installed..." ending with the prompt returning.
5. **Type:** `ls venv/Scripts/python.exe`
6. Press **Enter**. **You should see:** `venv/Scripts/python.exe`. If you see
   that, the environment is ready.

Keep this terminal window open for Part 3.

---

## Part 3 — Test the collector by hand (do this before touching Task Scheduler)

If it cannot run by hand, no schedule will help. This proves the file works.

### 3.1 — Run the wrapper

1. Click into the Git Bash terminal.
2. **Type:** `./run_cli_collection.bat`
3. Press **Enter**. **You should see:** the terminal think for a few seconds,
   then the prompt returns. It is **normal to see almost nothing on screen** —
   all the detail goes to a log file, which you check next.

### 3.2 — Read today's log

1. **Type:** `cat logs/automation_$(date +%Y-%m-%d).log`
2. Press **Enter**. **You should see** a block of text ending in one of these
   two, and BOTH mean success:
   - `phoenix: stored CLIPHX-... | ... | high=NNN low=NN ...` followed by
     `SUCCESS on attempt 1 (exit 0)` — a new report was saved.
   - `phoenix: product CLIPHX-... already stored — skipped` followed by
     `SUCCESS on attempt 1 (exit 0)` — there was nothing new to save. Also
     correct.

### 3.3 — Confirm the exit code was zero

1. **Type:** `echo $?`
2. Press **Enter**. **You should see:** `0`. Zero means success.

> **If it failed:** the log will show `FAILURE on attempt 1 ... retrying in
> 60s`, wait a minute, try again, and if it still fails end with `FAILURE on
> attempt 2 ... giving up`, and `echo $?` will show a number other than `0`.
> Read the log — the reason (for example, no internet, or a weather.gov error)
> is printed there. Fix that, then repeat Part 3. **Do not go to Part 4 until
> Part 3 succeeds at least once.**

---

## Part 4 — Import the three tasks into Task Scheduler

Now you tell Windows to run the wrapper on a schedule. You will import the
three ready-made task files.

### 4.1 — Open Task Scheduler

1. Press the **Windows key**.
2. **Type:** `Task Scheduler`
3. Press **Enter**. **You should see:** a window titled **Task Scheduler** with
   three vertical panes: a tree on the left, a middle area, and an **Actions**
   list on the right.

### 4.2 — Make a folder to hold your three tasks

1. In the **left pane**, click the small arrow to the left of **Task Scheduler
   Library** if it is collapsed, then right-click **Task Scheduler Library**
   itself. **You should see:** a menu.
2. Click **New Folder...**. **You should see:** a small box asking for a name.
3. **Type:** `WeatherPipeline`
4. Click **OK**. **You should see:** a **WeatherPipeline** entry appear under
   **Task Scheduler Library** in the left pane.
5. In the left pane, click **WeatherPipeline** once to select it. **You should
   see:** the middle pane mostly empty (no tasks yet).

### 4.3 — Import the Primary task (6:00 PM)

1. Look at the **right pane** (the **Actions** column). Click **Import
   Task...**. **You should see:** a file-open window.
2. In that window, navigate to your scheduler folder: click in the address bar
   at the top, **Type:** `C:\Projects\weather-pipeline\scheduler`, press
   **Enter**. **You should see:** the three `.xml` files listed.
3. Click **WeatherPipeline_CLI_Primary.xml** once to select it.
4. Click **Open**. **You should see:** a **Create Task** properties window,
   already filled in (name, trigger, action). You do **not** need to change
   anything.
5. Click **OK** at the bottom of that window.
6. **If a box titled "Enter user account information" appears:** type your
   Windows login password in the password field, then click **OK**. (Windows
   needs this to run the task while you are logged in. If you have no password,
   just click **OK**.)
7. **You should see:** `WeatherPipeline_CLI_Primary` now listed in the middle
   pane.

### 4.4 — Import the Amendment task (11:30 PM)

1. In the **right (Actions)** pane, click **Import Task...** again.
2. If the file window does not already show the scheduler folder, click the
   address bar, **Type:** `C:\Projects\weather-pipeline\scheduler`, press
   **Enter**.
3. Click **WeatherPipeline_CLI_Amendment.xml**.
4. Click **Open**.
5. Click **OK**.
6. Enter your password and click **OK** if asked.
7. **You should see:** `WeatherPipeline_CLI_Amendment` added to the middle pane.

### 4.5 — Import the Final task (12:30 AM)

1. In the **right (Actions)** pane, click **Import Task...** again.
2. Make sure the folder is `C:\Projects\weather-pipeline\scheduler` (use the
   address bar as before if needed).
3. Click **WeatherPipeline_CLI_Final.xml**.
4. Click **Open**.
5. Click **OK**.
6. Enter your password and click **OK** if asked.
7. **You should see:** all THREE tasks now listed in the middle pane:
   `WeatherPipeline_CLI_Primary`, `WeatherPipeline_CLI_Amendment`,
   `WeatherPipeline_CLI_Final`.

> **Faster alternative (optional):** if you are comfortable with a command
> line, Part 9 shows how to import all three with three commands instead.

---

## Part 5 — Test a task by hand

This proves the *task* (not just the file) works.

1. In Task Scheduler's **left pane**, click **WeatherPipeline** to show your
   three tasks in the middle.
2. In the **middle pane**, click **WeatherPipeline_CLI_Primary** once to select
   it (its row highlights).
3. Look at the **right (Actions)** pane. Under the task's name you will see a
   list of actions. Click **Run**. **You should see:** the **Last Run Result**
   column (in the middle pane) start working; it may briefly say the task is
   running.
4. Press the **F5** key to refresh. **You should see** in the **Last Run
   Result** column: **`The operation completed successfully. (0x0)`**. `0x0`
   is what you want.
5. Now confirm it actually did work. Switch to your Git Bash terminal (or open
   a new one via Part 2.1), **Type:**
   `cat logs/automation_$(date +%Y-%m-%d).log`, press **Enter**. **You should
   see:** a fresh run block at the very bottom, newer than the one from Part 3.

> If **Last Run Result** shows anything other than `0x0`, go to Part 10
> (Troubleshooting) and find that code in the table.

---

## Part 6 — Turn on history (so you can prove it ran automatically)

Windows keeps a per-task history, but it is usually switched off by default.
Turn it on once.

1. In Task Scheduler, look at the **far top-right** of the window — this is the
   **Actions** pane for the whole program.
2. Read the entry there:
   - If it says **Enable All Tasks History** → click it. **You should see:** it
     change to say "Disable All Tasks History." History is now on.
   - If it already says **Disable All Tasks History** → history is already on.
     Do nothing.

To view history later:
1. In the middle pane, click a task (e.g. `WeatherPipeline_CLI_Primary`).
2. In the **bottom-middle** area, click the **History** tab. **You should
   see:** timestamped events such as **Task Started**, **Action started**,
   **Task completed**. A run that automatically fired at 6:00 PM will appear
   here even though you did not click Run.

---

## Part 7 — Where your logs live

- **Automation log (the important one):**
  `C:\Projects\weather-pipeline\logs\automation_YYYY-MM-DD.log`
  One file per day. Every run — by hand or scheduled — adds a block to the
  bottom. It never overwrites. The line `SUCCESS on attempt 1 (exit 0)` is your
  proof the collector itself succeeded.
- **Task Scheduler history:** the **History** tab from Part 6 — Windows' own
  record of when the task started and stopped.

To see just the newest lines quickly, in Git Bash **Type:**
`tail -n 40 logs/automation_$(date +%Y-%m-%d).log` and press **Enter**.

---

## Part 8 — ONLY if your project is not at `C:\Projects\weather-pipeline`

Skip this Part entirely if your project IS at that path.

If your project lives somewhere else (for example `D:\stuff\weather-pipeline`),
you must fix three things before importing tasks.

### 8.1 — Fix the wrapper

1. In File Explorer, right-click `run_cli_collection.bat` in your repo root.
2. Click **Show more options** (Windows 11), then **Edit** — or **Edit**
   directly (Windows 10). **You should see:** Notepad open with the file.
3. Find the line near the top that reads `set "REPO=C:\Projects\weather-pipeline"`.
4. Change the path after the `=` to your real folder path (keep the quotes).
5. Press **Ctrl+S** to save. Close Notepad.

### 8.2 — Fix each of the three XML files

For **each** file in the `scheduler` folder (Primary, Amendment, Final):

1. Right-click the `.xml` file → **Open with** → **Notepad**.
2. Find the line containing `<Command>C:\Projects\weather-pipeline\run_cli_collection.bat</Command>`
   and change the path to your real path to `run_cli_collection.bat`.
3. Find the line containing
   `<WorkingDirectory>C:\Projects\weather-pipeline</WorkingDirectory>` and
   change it to your real repo-root path.
4. Press **Ctrl+S** to save. Close Notepad.

> Keep the encoding as-is when saving. If Notepad ever offers an encoding
> choice, leave it on **UTF-16 LE**. Do not "Save As UTF-8" — that can break
> the import.

Now return to Part 2.

---

## Part 9 — Optional: import all three tasks by command line

Instead of the click-through in Part 4, you can import all three at once.

1. Press the **Windows key**, **Type:** `cmd`.
2. In the results, right-click **Command Prompt**, click **Run as
   administrator**. Click **Yes** if Windows asks permission. **You should
   see:** a black window whose title says **Administrator: Command Prompt**.
3. Copy and paste these three lines (right-click in the window to paste),
   pressing **Enter** after each:

```
schtasks /Create /XML "C:\Projects\weather-pipeline\scheduler\WeatherPipeline_CLI_Primary.xml"   /TN "WeatherPipeline\WeatherPipeline_CLI_Primary"
schtasks /Create /XML "C:\Projects\weather-pipeline\scheduler\WeatherPipeline_CLI_Amendment.xml" /TN "WeatherPipeline\WeatherPipeline_CLI_Amendment"
schtasks /Create /XML "C:\Projects\weather-pipeline\scheduler\WeatherPipeline_CLI_Final.xml"     /TN "WeatherPipeline\WeatherPipeline_CLI_Final"
```

**You should see** after each line: `SUCCESS: The scheduled task "..." has
successfully been created.` If it asks for a password, type your Windows
password and press **Enter**.

This same command is how you recreate the tasks on a **different computer**:
copy the `scheduler` folder there and run these three lines.

---

## Part 10 — Troubleshooting

| What you see | What it means / what to do |
|---|---|
| Last Run Result `0x0` | Success. Nothing to fix. |
| Last Run Result `0x1` | The collector failed twice. Open today's log (`cat logs/automation_$(date +%Y-%m-%d).log`); the reason is printed there (often no internet, or a weather.gov error). Fix that and click **Run** again. |
| Last Run Result `0x41301` | The task is still running from before, or was left running. Wait a minute, or right-click the task → **End**, then try again. |
| Last Run Result `0x2` | A file was not found — usually a wrong path to the `.bat`, or `venv\Scripts\python.exe` is missing. Re-check Part 1 and Part 2. |
| Nothing appears in the log at all | The task may not have started (check the History tab), or the `logs` folder could not be created. Run the `.bat` by hand (Part 3) to see the real error. |
| "Git Bash Here" is missing | Use PowerShell: click File Explorer's address bar, type `powershell`, press Enter. |
| Import fails / "The task XML is malformed" | An XML file was re-saved as UTF-8. Copy the original file again from your download and re-import. |
| Asked for a password on every import | Normal. Windows stores your password so the task can run while you are logged in. |
| Runs by hand but never on its own | In the middle pane, check the **Status** column says **Ready** (not Disabled), and click the **Triggers** tab to confirm the time. Also make sure the PC is on at that time (or it will run when the PC next wakes). |

Useful commands (Administrator Command Prompt):
- See a task's full definition: `schtasks /Query /TN "WeatherPipeline\WeatherPipeline_CLI_Primary" /XML`
- Delete a task to start over: `schtasks /Delete /TN "WeatherPipeline\WeatherPipeline_CLI_Primary" /F`

---

## Part 11 — Verification checklist

Do each check once. When all eight pass, automation is proven.

- [ ] **Task exists** — Task Scheduler → **WeatherPipeline** folder shows all
      three tasks in the middle pane.
- [ ] **Task executes manually** — Select `WeatherPipeline_CLI_Primary`, click
      **Run** (right pane), press **F5**; Last Run Result shows **`0x0`**.
- [ ] **Task executes automatically** — Leave the PC on until the next
      scheduled time (or, to test now, set a trigger a few minutes ahead via
      the **Triggers** tab), then confirm the **History** tab shows a
      **Task Started** you did not click.
- [ ] **Collector runs successfully** — Today's log ends a block with
      `SUCCESS on attempt 1 (exit 0)` (or attempt 2).
- [ ] **Database receives a new row when appropriate** — On a run that logged
      `stored CLIPHX-...`, the row count went up by one. Check in Git Bash:
      `venv/Scripts/python.exe -c "import sqlite3;print(sqlite3.connect('data/pipeline.db').execute('select count(*) from raw_nws_cli').fetchone())"`
- [ ] **Duplicate protection still works** — Click **Run** on the same task
      twice; the second time the log says `already stored — skipped` and the
      row count above does **not** change.
- [ ] **Logs are written** — `logs\automation_YYYY-MM-DD.log` exists for today
      and has text in it.
- [ ] **Scheduler XML recreates the task** — Delete one task
      (`schtasks /Delete ... /F`), re-import its XML (Part 4 or Part 9), and
      confirm it reappears and still runs.

When all eight boxes are checked, the Phoenix CLI collector is running
unattended, logging every run, retrying once on a hiccup, and fully
re-creatable from the `scheduler` folder on any machine.
