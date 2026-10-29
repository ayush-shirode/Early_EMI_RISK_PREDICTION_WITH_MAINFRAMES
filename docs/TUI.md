# Operator console (TUI)

The dashboard is for bank staff. The operator console is for whoever runs the mainframe side: a terminal UI in the style of a 3270 ISPF session that monitors both connections to z/OS and runs every mainframe task.

```bash
make tui          # = .venv/bin/python -m tui
```

It talks to z/OS directly through `pipeline/zos.py` (z/OSMF) and `pipeline/uss.py` (SSH). It does **not** need the web backend running. The two share the SQLite database, so runs started in the console appear in the dashboard and the other way round, and only one action runs at a time across both.

The terminal should be at least 120×36. The F-keys follow ISPF; if the terminal swallows them, `Esc` also works as F3, and every function has a typed command.

## Panel layout

```
EWSDSL ----------------------- DATA SET LIST UTILITY ----------------------- S0W1   ← panel ID, title, system
COMMAND ===> ______________________________________________ SCROLL ===> CSR        ← primary commands
EWS121I 640 RECORDS DOWNLOADED TO data/downloads/Z72230.EWS.CTLTOT.txt              ← message line
...body...
B=BROWSE  D=DOWNLOAD  U=UPLOAD  C=COUNT(SSH)  F3=END  F5=REFRESH  :=COMMAND        ← keys
 ZOSMF ■ UP  325 MS │ SSH ■ UP 1330 MS │ Z72230@S0W1 │ NO ACTIVE RUN │ 2026.301 22:50:21  ← status line
```

The status line is on every panel. It shows both channels (state and latency from the heartbeat), the logged-on user, any active run (from any process), and the date in z/OS Julian form.

## Navigation

| Input | Effect |
|---|---|
| `0`–`8` or the option name on the primary menu | open that option |
| `=N` on any panel | jump to option N (`=X` exits) |
| `TSO <command>` or `/<console command>` on any panel | run it on z/OS (opens the command shell) |
| `F3` / `Esc` | back one panel; exit on the primary menu |
| `F1` | help for the panel |
| `F5` | refresh |
| `:` | put the cursor on the command line |
| `Tab` | next pane |

## Options

| Opt | Panel | What it does |
|---|---|---|
| 0 | **LOGON** (`EWSLOGON`) | TSO/E-style logon: user ID, password, host, z/OSMF and SSH ports, verify TLS. Checks the logon against z/OSMF and stores the password in the OS keyring. Shown automatically on first start. |
| 1 | **CONNECT** (`EWSCONN`) | Connection monitor. Two boxes, one per channel: endpoint, state and since when, latency (last/average/maximum), checks ok/failed and availability, last error, plus a latency sparkline. Below them, live z/OS data from the EWS agent: system name, release, IPL date and volume, console clock, home file system, ZOAU/Python versions. At the bottom, connection events. Commands: `TEST`, `SSHKEY` (show the host-key fingerprint, then trust it), `INSTALL` (copy the agent to USS), `RECONNECT`, `LOGOFF`. |
| 2 | **DSLIST** (`EWSDSL`) | Like ISPF 3.4: the `Z72230.EWS.**` data sets with DSORG, RECFM, LRECL, block size, use, volume and dates. Line keys: `B`/Enter browse (libraries show their members), `D` download to `data/downloads/<DSN>.txt`, `U` upload a local file (default: the matching generated input file; lines longer than the LRECL are refused before anything is sent), `C` count records on z/OS through the SSH agent. `L <pattern>` lists other data sets. |
| — | **BROWSE** (`EWSBRW`) | Records with line numbers and the `=COLS>` ruler, *Top of Data* / *Bottom of Data*. `FIND text`, `TOP`, `BOT`, F7/F8 page, F10/F11 left/right. Used for data sets, members, spool files and local report copies. |
| 3 | **SDSF** (`EWSSDSF`) | Job queue: job name, ID, owner, type, class, status, phase, return code (green 0, yellow 4, red otherwise), auto-refresh every 20 s. `S`/Enter opens the job: its step return codes as a flow (`STEP010 0000 -> STEP020 0004 -> ...`) and its spool data sets (JESMSGLG, JESJCL, JESYSMSG, SYSOUT, SYSPRINT…), which open in BROWSE. `P` purges a job (asks first). `PRE EWS*`, `OWNER *`. |
| 4 | **PIPELINE** (`EWSPIPE`) | The batch pipeline. Actions 1–8 (test, setup, compile, sources, generate, train, run batch, reset), started with their number, Enter, or a command (`RUN 20260930`, `TRAIN`, `GEN 1500 42`, `RESET`). Each asks for its parameters or for confirmation; RESET needs the word RESET typed. Next to them is the run history from every process (with `FROM` = API, TUI or CLI). Below, the selected run's steps with status, start, duration and detail; for steps that ran a job, its JCL step return codes as a flow; for EWSBATCH, the REXX reconciliation checks. Refreshes every 1.5 s. |
| 5 | **SYSLOG** (`EWSLOG`) | The operator log, live: every z/OSMF request with HTTP status and duration, uploads/downloads with record counts, job submit/end, run steps, SSH commands, channel up/down, logon. Errors red, warnings yellow. `ERR` shows only warnings and errors, `ALL` everything, `CLEAR` empties the display. |
| 6 | **COMMAND** (`EWSCMD`) | Command shell on z/OS over SSH. Plain text runs in the USS shell (ZOAU on the PATH: `dls`, `jls`, `dcat`…), `TSO <cmd>` runs a TSO/E command (`TSO LISTCAT LEVEL(Z72230.EWS)`), `/<cmd>` an operator console command (`/D IPLINFO`, `/D T`, `/D A,L`). Shows the output, the RC and the time; Up/Down recall earlier commands. |
| 7 | **REPORTS** (`EWSRPT`) | For the last scoring run (or `RUN n`): the REXX reconciliation (RUNCTL) with every check (including `CHK_VSAM`), rejects and matching exceptions by reason code, and the COBOL early intervention list with the customer names EWSRPT read by key from VSAM. `RPT`, `REJ`, `EXC` open the full text. |
| 8 | **VSAM** (`EWSVSAM`) | The two VSAM KSDS clusters (`CUSTKSDS`, `SCORKSDS`) with their `LISTCAT` statistics: records, inserted, updated, deleted, retrieved, CI/CA splits, CI size, key, volume. Type a customer ID (`CUST0166`, or `KEY CUST0166`) to read both records by key: the customer master, and the latest and previous score with the change and how often it was scored, plus the raw 100-byte records under a column ruler with the key highlighted. `B` browses a cluster's first 500 records in key order. VSAM clusters in DSLIST open the same browse. |

## Runs started from the console

An action started here runs in a thread of the console process, exactly like one started from the dashboard runs in the backend. The run lock lives in SQLite: before starting, every process checks for a `running` run whose process is still alive, so the dashboard shows "Run #N is still active (started from the TUI)" and the console refuses to start a second one. If the console exits during its own run, it asks first; the run is then marked failed the next time anyone starts an action or the backend starts.

## Message IDs

| ID | Meaning | ID | Meaning |
|---|---|---|---|
| `EWS100I` | z/OSMF request ok | `EWS200I` | run started |
| `EWS101E` | z/OSMF request failed | `EWS201I` / `EWS202E` | run step ok / failed |
| `EWS102W` | z/OSMF request retried | `EWS203I` / `EWS204E` | run ended ok / failed |
| `EWS110I` | job submitted / purged | `EWS300I` / `EWS301E` | SSH command ok / failed |
| `EWS111I` / `EWS112E` | job ended ok / with an error | `EWS302I` | SSH connected |
| `EWS120I` / `EWS121I` | upload / download | `EWS400I` / `EWS401E` | channel up / down |
| `EWS000E` | unknown command | `EWS500I` | logon, host key trusted, agent installed |

## Code

| File | Content |
|---|---|
| `tui/app.py` | the app: navigation, command routing, status line, heartbeats (z/OSMF every 15 s, SSH every 30 s, agent every 5 min) |
| `tui/panels.py` | the ISPF panel frame, colours, dialogs (confirm, form, text) |
| `tui/screens.py` | the panels |
| `tui/monitor.py` | channel state, latency history, availability |
| `tui/ews.tcss` | the 3270 look |

Built with [Textual](https://textual.textualize.io/).
