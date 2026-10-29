# Operator Console (TUI): Options and Demo Flow

## The 10 options at a glance

| Opt | Name | One-liner |
|---|---|---|
| **0** | LOGON | Signs you on to z/OS: user ID and password are checked against z/OSMF, and the password goes to the OS keyring. |
| **1** | CONNECT | Live health of both channels to the mainframe (HTTPS to z/OSMF, SSH to z/OS UNIX), plus system information from our agent on z/OS. |
| **2** | DSLIST | Lists the project's data sets (the mainframe "files"), which you can browse, download, upload or count. |
| **3** | SDSF | Job queue: every batch job, its return code, the return code of each step, and its printed output. |
| **4** | PIPELINE | Starts and follows the batch pipeline (setup → compile → generate → train → run batch & score), step by step. |
| **5** | SYSLOG | Live operator log of every mainframe call, job, run step, connection change and error. |
| **6** | COMMAND | Runs real commands on z/OS over SSH: a UNIX shell, TSO commands and operator console commands. |
| **7** | REPORTS | Results of the last batch run: REXX reconciliation, rejected records, and the COBOL early intervention list. |
| **8** | VSAM | The two VSAM KSDS clusters: their catalog statistics, and any customer read by key with their latest and previous score. |
| **X** | EXIT | Leaves the console (it asks first if a run started here is still active). |

## Keys you will use

| Key / input | Does |
|---|---|
| `0`–`8` or Enter (on the menu) | open an option |
| `=N` on any panel's command line | jump straight to option N |
| `F3` or `Esc` | go back one panel |
| `F5` | refresh |
| `:` | move the cursor to the `COMMAND ===>` line |
| `Tab` | move to the next pane |
| `F1` | help for the current panel |

---

## Before the demo (5 minutes, the day before)

1. **Open a terminal of at least 120×36, then run `cd ~/mainframes/CP && make tui`.** A small window cuts off panels.
2. **Open 1 CONNECT and check that both channels show `■ UP`.** If the password expired, renew it on Z Xplore and log on again on option 0.
3. **Open 4 PIPELINE and run `TRAIN`, then `RUN 20260930`.** This gives REPORTS fresh results; it takes about 4 minutes in total.
4. **Optional: start the web app with `make dev` in a second terminal.** Then you can show that a run started in the console also appears in the dashboard.

---

## Demo flow (about 11 minutes)

### Step 1: Start the console and show the primary menu (0:00)
- **Do:** run `make tui`. The **EWSPRIM** primary option menu opens.
- **Show:** the EWS banner, the 10 options, and the system box on the right (user ID, system S0W1, z/OS level, model, last run).
- **Say:** *"This is the operator's view of the mainframe side, built to look and work like a real 3270 ISPF session."*

### Step 2: Show the status line (0:30)
- **Do:** point at the bottom line: `ZOSMF ■ UP … │ SSH ■ UP … │ Z72230@S0W1 │ NO ACTIVE RUN │ 2026.301 …`.
- **Say:** *"Every panel shows both connections to z/OS, who is logged on, any batch run in progress, and the date in mainframe Julian format."*

### Step 3: Option 0, LOGON (1:00)
- **Do:** press `0`. Show the TSO/E-style fields (Userid, Password, Host, ports, Verify TLS), then press `F3` to go back.
- **Say:** *"Logon is checked against z/OSMF, and the password goes into the OS keyring. Nothing secret is written to a file."*

### Step 4: Option 1, CONNECT (1:30)
- **Do:** press `1`, then type `TEST` and press Enter.
- **Show:**
  - **Channel 1, z/OSMF over HTTPS:** state, latency, checks, availability.
  - **Channel 2, SSH to z/OS UNIX:** the same figures, plus the pinned host key.
  - **The latency sparklines.**
  - **The Z/OS SYSTEM box:** system name, z/OS 3.1, IPL date and volume, and the console clock. Our own agent running on the mainframe reports these.
  - **The connection events log** at the bottom.
- **Say:** *"These are two independent channels, both with our own client code. The system data comes from our agent running on z/OS itself."*

### Step 5: Option 2, DSLIST (2:30)
- **Do:** type `=2`. The data sets `Z72230.EWS.**` are listed.
- **Say:** *"These are the mainframe's files: fixed-length records in EBCDIC, sorted by DFSORT and checked by COBOL."*
- **Do:** move to `Z72230.EWS.CUSTMAST` and press `B`. A browse opens with the `=COLS>` ruler.
- **Do:** type `FIND CUST0166`, then press `F3`.
- **Say:** *"Each line is one customer record, laid out byte by byte by a COBOL copybook."*
- **Do:** on the same data set, press `C`. The message line shows the record count, fetched over SSH.
- **Do:** move to `Z72230.EWS.RUNCTL` and press `D`. The message shows the local file it was downloaded to.
- **Do (optional):** move to `Z72230.EWS.JCL` and press `B` to see the member list, then `B` on `EWSBATCH` to show the batch JCL. Press `F3` twice.

### Step 6: Option 4, PIPELINE (4:00)
- **Do:** type `=4`.
- **Show:** the **ACTIONS** list (1–8) and the **RUN HISTORY** (the `FROM` column says whether a run came from the web app, the TUI or the CLI).
- **Say:** *"This panel drives the whole mainframe batch, and only one run can be active at a time, across the web app and this console."*
- **Do:** press `1` (test connection). It finishes in about 1 second and appears as a new run, `FROM TUI`.
- **Do (main moment):** type `RUN 20260930` and confirm with Enter. Watch it live, about 70 seconds:
  - **Steps turn from `·` to `►` to `✓`.**
  - **The EWSBATCH job appears with its step return codes**, e.g. `STEP010 0000 -> STEP050 0004 -> …`.
  - **The `RECON` line shows the REXX balancing checks**, all `OK`.
  - **The status line shows `RUN #N … EXECUTING`.**
- **Say while it runs:** *"z/OS is now sorting with DFSORT, validating and matching with COBOL, and reconciling counts with REXX. Then Python scores every customer and writes the scores back to the mainframe."*
- **If short on time:** don't wait for the run. Select an earlier `RUN_BATCH` in RUN HISTORY with the arrow keys to show its finished steps.

### Step 7: Option 3, SDSF (5:30)
- **Do:** type `=3`, then `PRE EWS*`.
- **Show:** the EWSBATCH and EWSRPTJ jobs with their `CC 0000` / `CC 0004` return codes.
- **Do:** press `S` on EWSBATCH.
- **Show:** the JOB STEPS flow and the spool data sets.
- **Do:** press `S` on `JESYSMSG`, then type `FIND COND CODE`.
- **Say:** *"This is the job's real system output from JES2. The return codes in the pipeline panel are read from exactly these messages."*
- **Do:** press `F3` twice.

### Step 8: Option 7, REPORTS (6:30)
- **Do:** type `=7`.
- **Show:**
  - **RECONCILIATION:** every `CHK_…` check `OK` and `STATUS OK`.
  - **REJECTS AND EXCEPTIONS:** bad records caught, by reason code (C02 age not numeric, L05 tenure, M02 orphan repayment…).
  - **EARLY INTERVENTION LIST:** the riskiest customers, with risk %, tier, top risk factor and name. The COBOL program read each name by key from VSAM.
- **Say:** *"The batch refuses to score unless every count balances, and the final list is printed by a COBOL program on z/OS from the model's scores."*
- **Do:** type `RPT`. This opens the full 133-column COBOL report. Press `F3`.

### Step 9: Option 8, VSAM (7:30)
- **Do:** type `=8`.
- **Show:** the two clusters and their LISTCAT statistics. `CUSTKSDS` has 1,475 records; `SCORKSDS` has about 1,054 records, and its **UPDATED** column counts in-place updates.
- **Say:** *"The batch uses sequential files because it reads everything. For one customer at a time we use VSAM KSDS clusters, indexed by customer ID."*
- **Do:** type `CUST0166`.
- **Show:**
  - **The customer record** from `CUSTKSDS`.
  - **The score record** from `SCORKSDS`: latest probability, the **previous** score from the earlier run, the change in points, and **TIMES SCORED**.
  - **The raw 100-byte records**, with the key highlighted under the column ruler.
- **Say:** *"COBOL program EWSSUPD reads this record by key on every scoring run, moves the old score to 'previous' and rewrites it in place. No file is rewritten."*
- **Do (optional):** press `Tab`, then `B` on a cluster to browse its records in key order. Press `F3`.

### Step 10: Option 6, COMMAND (8:30)
- **Do:** type `=6`, then run these one at a time:
  - **`/D IPLINFO`:** an operator console command; shows when the system was IPLed and from which volume.
  - **`TSO LISTCAT LEVEL(Z72230.EWS) NAME`:** a TSO command; the catalog entries of our data sets.
  - **`dls 'Z72230.EWS.*'`:** a z/OS UNIX command using ZOAU; the same data sets, listed from the shell.
- **Say:** *"Everything here runs on the real mainframe over SSH: UNIX, TSO and the operator console, from one prompt."*
- **Do:** press Up to show command history.

### Step 11: Option 5, SYSLOG (9:30)
- **Do:** type `=5`.
- **Show:** every line from the demo: `EWS110I JOB … SUBMITTED`, `EWS111I … ENDED CC 0004`, `EWS120I UPLOAD …`, `EWS201I RUN … STEP … OK`, `EWS300I SSH …`, each with its duration in ms.
- **Do:** type `ERR`. Only warnings and errors remain. Then type `ALL`.
- **Say:** *"This is the audit trail: every mainframe call from the web app, this console and the CLI, with z/OS-style message IDs."*

### Step 12: Exit (10:30)
- **Do:** type `=X`, or press `F3` on the menu.
- **Say:** *"The bank staff use the web dashboard; the operator uses this console. Both drive the same mainframe batch."*

---

## If something goes wrong during the demo

| Symptom | Quick fix |
|---|---|
| ZOSMF shows `DOWN` | Z Xplore may be busy. Type `TEST` on option 1; already-finished runs and reports still show. |
| SSH shows `NOKEY` | On option 1 type `SSHKEY`, check the fingerprint, and press Enter. |
| "EWS agent is not installed" | On option 1 type `INSTALL`. |
| "RUN #N IS STILL ACTIVE" | A run is already going (maybe from the web app). Follow it on option 4. |
| F-keys don't work in the terminal | Use `Esc` instead of F3, and type commands (`TOP`, `BOT`) instead of F7/F8. |
