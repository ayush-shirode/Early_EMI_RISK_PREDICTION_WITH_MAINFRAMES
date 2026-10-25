# Mainframe data store: data sets and record layouts

## 1. What kind of "database" this is

There is no relational database on the mainframe side. The data is stored the way classic z/OS batch systems store it: in **data sets**, cataloged files managed by z/OS (SMS-managed on 3390 disk volumes), with **fixed-length records** whose fields are defined by **COBOL copybooks**.

| Concept | In this project |
|---|---|
| Data set organisation | **PS** (physical sequential, read and written with QSAM) for data; **PO-E / PDS-E** (partitioned, "library") for source code and load modules |
| Record format | **FB** fixed blocked (most), **VB** variable blocked (the CSV), **FBA** fixed with ASA print control (the report), **U** undefined (load modules) |
| Record length (LRECL) | 80, 100, 120, 200 bytes for FB; up to 1024 for VB; 133 for the print report |
| Block size | `BLKSIZE=0` in JCL, so z/OS picks the optimal block size (e.g. 27,920 for LRECL 80) |
| "Schema" | COBOL copybooks in `mainframe/copybooks/` (and `Z72230.EWS.CPY`), mirrored in Python by `ml/layouts.py` |
| "Keys" / ordering | No index: files are sorted by DFSORT on the key fields and processed sequentially, matching on the keys |
| Character set | EBCDIC IBM-1047 on z/OS, ASCII locally (converted by z/OSMF on transfer) |
| Numbers | Zoned decimal `PIC 9(n)V99`: digits as characters with an *implied* decimal point (`000004530000` = 45,300.00). No signs. |
| Not used | VSAM (KSDS/ESDS), DB2, IMS: the planned design was sequential batch only |

This is the "master file + sort + match" pattern that most bank batch systems still use for nightly processing.

## 2. Naming

All project data sets start with the high-level qualifier `Z72230` (the z/OS user ID; the JCL writes it as `&SYSUID`) and the second-level qualifier `EWS` (Early Warning System). Two existing libraries of the user are reused because the site compile procedure requires them.

## 3. Catalogue of data sets

### 3.1 Libraries (PDS-E)

| Data set | RECFM/LRECL | Members | Created by |
|---|---|---|---|
| `Z72230.EWS.JCL` | FB 80 | `EWSBATCH`, `EWSCOMP`, `EWSRPTJ` | Setup |
| `Z72230.EWS.CPY` | FB 80 | `CUSTREC`, `LOANREC`, `REPAYREC`, `TXNREC`, `FEATREC`, `SCOREREC`, `REJREC`, `CTLREC` | Setup |
| `Z72230.EWS.CNTL` | FB 80 | `SRTCUST`, `SRTLOAN`, `SRTREPAY`, `SRTTXN`, `FEAT2CSV`, `SRTSCORE` | Setup |
| `Z72230.EWS.REXX` | FB 80 | `EWSRECON` | Setup |
| `Z72230.CBL` (existing) | FB 80 | `EWSVCUST`, `EWSVLOAN`, `EWSMATCH`, `EWSRPT` (your other members are untouched) | Setup |
| `Z72230.LOAD` (existing) | U | load modules of the 4 programs | `EWSCOMP` (binder) |

### 3.2 Input data (PS) — uploaded by "Generate & upload data"

| Data set | Layout | LRECL | Records (1,500 customers) | Space |
|---|---|---|---|---|
| `Z72230.EWS.CUSTMAST` | CUSTREC | 100 | 1,503 | 15 tracks |
| `Z72230.EWS.LOANMAST` | LOANREC | 80 | 2,381 | 15 tracks |
| `Z72230.EWS.REPAYHST` | REPAYREC | 80 | 37,358 | 150 tracks |
| `Z72230.EWS.TXNSUMM` | TXNREC | 80 | 36,001 | 150 tracks |

### 3.3 Work and output data sets — created by `EWSBATCH` (deleted and recreated every run)

| Data set | Layout | RECFM/LRECL | Written by | Content |
|---|---|---|---|---|
| `EWS.CUST.SRT` | CUSTREC | FB 100 | STEP010 ICETOOL | customers sorted by ID, first record of each ID |
| `EWS.CUST.DUPS` | CUSTREC | FB 100 | STEP010 ICETOOL | the duplicate IDs that were dropped |
| `EWS.LOAN.SRT` | LOANREC | FB 80 | STEP020 DFSORT | loans sorted by customer, loan |
| `EWS.REPAY.SRT` | REPAYREC | FB 80 | STEP030 DFSORT | repayments sorted by customer, loan, due date; numeric fields verified |
| `EWS.TXN.SRT` | TXNREC | FB 80 | STEP040 DFSORT | account summaries sorted by customer, month; numeric fields verified |
| `EWS.CUST.VALID` | CUSTREC | FB 100 | STEP050 EWSVCUST | customers that passed validation |
| `EWS.LOAN.VALID` | LOANREC | FB 80 | STEP060 EWSVLOAN | loans that passed validation |
| `EWS.REJECTS` | REJREC | FB 120 | STEP030/040/050/060 (`DISP=MOD`, appended) | every rejected record with a reason code |
| `EWS.EXCEPT` | REJREC | FB 120 | STEP070 EWSMATCH | records that could not be matched |
| `EWS.CTLTOT` | CTLREC | FB 80 | STEP050/060/070 (`DISP=MOD`) | control totals `PROGRAM KEY=VALUE` |
| `EWS.FEATURES` | FEATREC | FB 200 | STEP070 EWSMATCH | one feature record per eligible customer |
| `EWS.FEATCSV` | CSV text | VB 1024 | STEP080 DFSORT | the same features as comma-separated values with a header |
| `EWS.RUNCTL` | `KEY=VALUE` text | FB 80 | STEP090 REXX | reconciliation result, `STATUS=OK` or `OUT_OF_BALANCE` |

### 3.4 Write-back data sets

| Data set | Layout | RECFM/LRECL | Written by | Content |
|---|---|---|---|---|
| `EWS.SCORES` | SCOREREC | FB 80 | backend (upload) | probability, tier, action code, top factor per customer |
| `EWS.SCORES.SRT` | SCOREREC | FB 80 | EWSRPTJ STEP010 DFSORT | sorted by probability, highest first |
| `EWS.RISKRPT` | print lines | FBA 133 | EWSRPTJ STEP020 EWSRPT | the paginated early intervention list |

Total footprint for 1,500 customers is a few MB (roughly 400 tracks).

## 4. Record layouts

Positions are 1-based, as DFSORT uses them. `9(7)V99` means 9 stored digits with 2 implied decimals.

### CUSTREC — customer master (LRECL 100, key `CU-CUST-ID`)

| Pos | Len | Field | PIC | Valid values |
|---|---|---|---|---|
| 1 | 8 | CU-CUST-ID | X(8) | `CUST0001` … |
| 9 | 30 | CU-CUST-NAME | X(30) | |
| 39 | 20 | CU-CITY | X(20) | |
| 59 | 1 | CU-EMP-TYPE | X | `S` salaried, `E` self-employed, `B` business |
| 60 | 3 | CU-AGE | 9(3) | 21–75 |
| 63 | 9 | CU-MONTHLY-INCOME | 9(7)V99 | > 0 |
| 72 | 3 | CU-CREDIT-SCORE | 9(3) | 300–900 |
| 75 | 8 | CU-OPEN-DATE | 9(8) | valid YYYYMMDD |
| 83 | 1 | CU-STATUS | X | `A` active, `C` closed |
| 84 | 17 | FILLER | X(17) | |

### LOANREC — loan master (LRECL 80, key `LN-CUST-ID` + `LN-LOAN-ID`)

| Pos | Len | Field | PIC | Valid values |
|---|---|---|---|---|
| 1 | 10 | LN-LOAN-ID | X(10) | `LN00001001` |
| 11 | 8 | LN-CUST-ID | X(8) | |
| 19 | 1 | LN-LOAN-TYPE | X | `H` home, `C` car, `P` personal, `E` education |
| 20 | 11 | LN-PRINCIPAL | 9(9)V99 | > 0 |
| 31 | 4 | LN-INT-RATE | 9(2)V99 | annual % |
| 35 | 3 | LN-TENURE | 9(3) | 1–360 months |
| 38 | 8 | LN-START-DATE | 9(8) | valid date |
| 46 | 9 | LN-EMI-AMT | 9(7)V99 | > 0 |
| 55 | 2 | LN-DUE-DAY | 9(2) | 1–28 |
| 57 | 11 | LN-OUTSTANDING | 9(9)V99 | |
| 68 | 1 | LN-STATUS | X | `A` active, `C` closed, `D` defaulted |
| 69 | 12 | FILLER | | |

### REPAYREC — EMI installment history (LRECL 80, key customer + loan + due date)

| Pos | Len | Field | PIC | Meaning |
|---|---|---|---|---|
| 1 | 10 | RP-LOAN-ID | X(10) | |
| 11 | 8 | RP-CUST-ID | X(8) | |
| 19 | 3 | RP-INST-NO | 9(3) | installment number |
| 22 | 8 | RP-DUE-DATE | 9(8) | |
| 30 | 8 | RP-PAID-DATE | 9(8) | `00000000` = not paid (yet) |
| 38 | 9 | RP-DUE-AMT | 9(7)V99 | |
| 47 | 9 | RP-PAID-AMT | 9(7)V99 | |
| 56 | 3 | RP-DPD | 9(3) | days past due |
| 59 | 1 | RP-STATUS | X | `P` on time, `L` late, `R` partial, `B` bounced then paid, `M` missed |
| 60 | 21 | FILLER | | |

### TXNREC — monthly account summary (LRECL 80, key customer + month)

| Pos | Len | Field | PIC | Meaning |
|---|---|---|---|---|
| 1 | 8 | TX-CUST-ID | X(8) | |
| 9 | 6 | TX-YYYYMM | 9(6) | month |
| 15 | 9 | TX-CREDITS | 9(7)V99 | all money in |
| 24 | 9 | TX-DEBITS | 9(7)V99 | all money out (spend + EMIs) |
| 33 | 9 | TX-SALARY | 9(7)V99 | salary / regular income credit (0 = missing) |
| 42 | 9 | TX-MIN-BAL | 9(7)V99 | lowest balance in the month |
| 51 | 9 | TX-AVG-BAL | 9(7)V99 | average balance |
| 60 | 2 | TX-BOUNCES | 9(2) | failed auto-debits / cheques |
| 62 | 5 | TX-CC-UTIL | 9(3)V99 | credit-card utilisation % |
| 67 | 14 | FILLER | | |

### FEATREC — ML features (LRECL 200)

Numeric fields are **numeric-edited** (`ZZ9.99`, `-ZZZ9.99`), so the record is readable and DFSORT can build the CSV by copying characters. Field order equals the CSV column order (`ml/layouts.py: FEATURE_FIELDS`).

| Pos | Len | Field / CSV column | PIC |
|---|---|---|---|
| 1 | 8 | cust_id | X(8) |
| 9 | 8 | as_of_date | 9(8) |
| 17 | 1 | emp_type | X |
| 18 | 3 | age | ZZ9 |
| 21 | 10 | monthly_income | Z(6)9.99 |
| 31 | 3 | credit_score | ZZ9 |
| 34 | 2 | active_loans | Z9 |
| 36 | 10 | total_emi | Z(6)9.99 |
| 46 | 7 | emi_to_income | Z9.9999 |
| 53 | 3 | tenure_remaining | ZZ9 |
| 56 | 3 | inst_due_12m | ZZ9 |
| 59 | 2 | late_cnt_3m | Z9 |
| 61 | 2 | late_cnt_12m | Z9 |
| 63 | 2 | missed_cnt_12m | Z9 |
| 65 | 2 | partial_cnt_12m | Z9 |
| 67 | 2 | emi_bounce_6m | Z9 |
| 69 | 2 | txn_bounce_6m | Z9 |
| 71 | 3 | max_dpd_12m | ZZ9 |
| 74 | 6 | avg_dpd_6m | ZZ9.99 |
| 80 | 7 | dpd_trend | -ZZ9.99 |
| 87 | 10 | avg_balance_3m | Z(6)9.99 |
| 97 | 10 | min_balance_3m | Z(6)9.99 |
| 107 | 8 | balance_trend_pct | -ZZZ9.99 |
| 115 | 7 | savings_to_emi | ZZZ9.99 |
| 122 | 1 | salary_missing_6m | 9 |
| 123 | 8 | debit_credit_ratio_3m | ZZ9.9999 |
| 131 | 8 | spend_trend_pct | -ZZZ9.99 |
| 139 | 6 | cc_util_avg_3m | ZZ9.99 |
| 145 | 1 | label_stress_90d | X (`0`/`1` in TRAIN mode, blank in SCORE mode) |
| 146 | 55 | FILLER | |

What each feature means is in [ML_MODEL.md](ML_MODEL.md#2-features).

### SCOREREC — scores written back (LRECL 80)

| Pos | Len | Field | PIC | Example |
|---|---|---|---|---|
| 1 | 8 | SC-CUST-ID | X(8) | `CUST0166` |
| 9 | 8 | SC-ASOF | 9(8) | `20260930` |
| 17 | 5 | SC-PROB | 9V9999 | `08811` = 0.8811 |
| 22 | 6 | SC-TIER | X(6) | `HIGH  `, `MEDIUM`, `LOW   ` |
| 28 | 4 | SC-ACTION | X(4) | `INTV` intervene, `REVW` review, `MON` monitor |
| 32 | 30 | SC-TOP-FACTOR | X(30) | `SPEND-TO-INCOME (3 M)` |
| 62 | 9 | SC-TOTAL-EMI | 9(7)V99 | |
| 71 | 10 | FILLER | | |

### REJREC — rejects and exceptions (LRECL 120)

| Pos | Len | Field | Content |
|---|---|---|---|
| 1 | 8 | RJ-SOURCE | `CUSTMAST`, `LOANMAST`, `REPAYHST`, `TXNSUMM` |
| 9 | 10 | RJ-KEY | customer or loan ID |
| 19 | 4 | RJ-REASON-CODE | see [BATCH_JOBS.md](BATCH_JOBS.md#6-reason-codes) |
| 23 | 40 | RJ-REASON-TEXT | readable reason |
| 63 | 58 | RJ-DATA | first 58 bytes of the original record |

### CTLREC — control totals (LRECL 80)

`EWSVCUST CUST-READ            =000001478` → program (8), blank, key (20), `=`, value 9(9).

## 5. Example records (as stored, shown in ASCII)

```
CUSTMAST  CUST1326Lakshmi Nair                  Mumbai              S03900588000067920180809A
```
`CUST1326` · name · city · `S` salaried · age `039` · income `005880000` = 0058800.00 → ₹58,800.00 · credit score `679` · opened `20180809` · status `A`.

```
SCORES    CUST01662026093008811HIGH  INTVSPEND-TO-INCOME (3 M)         001331241
```
`CUST0166` · as-of `20260930` · probability `08811` = 0.8811 · tier `HIGH  ` · action `INTV` · top factor · total EMI `001331241` = ₹13,312.41.

## 6. Who reads and writes what

```
                    upload (Zowe)                                     download (Zowe)
local generator ──► CUSTMAST LOANMAST REPAYHST TXNSUMM
                        │        │        │        │
                   ICETOOL  DFSORT   DFSORT   DFSORT
                        ▼        ▼        ▼        ▼
                    CUST.SRT LOAN.SRT REPAY.SRT TXN.SRT ─────────────────────► SQLite (history)
                        │        │        │        │
                  EWSVCUST EWSVLOAN       │        │      REJECTS ◄─ all four ─► UI Reports
                        ▼        ▼        │        │
                  CUST.VALID LOAN.VALID ──┼────────┼──────────────────────────► SQLite (customers, loans)
                        └────────┴───► EWSMATCH ◄──┘      EXCEPT ───────────────► UI Reports
                                          ▼
                                       FEATURES ─► DFSORT ─► FEATCSV ──────────► Python model
                                          │                                       │
                       CTLTOT ──► REXX EWSRECON ─► RUNCTL ──────────────────────► gate (STATUS=OK)
                                                                                  ▼
                                    RISKRPT ◄── EWSRPT ◄── DFSORT ◄── SCORES ◄─── upload (Zowe)
                                       └──────────────────────────────────────────► UI Reports
```
