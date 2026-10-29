# Batch jobs on z/OS: JCL, DFSORT/ICETOOL, COBOL, REXX

Sources live in `CP/mainframe/` and are uploaded by **Set up mainframe** to the libraries listed in [MAINFRAME_DATASETS.md](MAINFRAME_DATASETS.md). All jobs run in `CLASS=7` (the class used by the existing Z Xplore jobs) and refer to data sets through `&SYSUID`, so they work under any user ID.

| Job | Member | Purpose | Submitted by |
|---|---|---|---|
| EWSCOMP | `EWS.JCL(EWSCOMP)` | compile and link the 4 COBOL programs | Set up / Recompile |
| EWSBATCH | `EWS.JCL(EWSBATCH)` | sort, validate, match, build features, reconcile | Train model (×4, `MODE=TRAIN`), Run batch (`MODE=SCORE`) |
| EWSRPTJ | `EWS.JCL(EWSRPTJ)` | sort the written-back scores and print the intervention list | Run batch (last step) |

## 1. EWSCOMP — compile and link

```jcl
//CVCUST   EXEC IGYWCL,SRC=EWSVCUST
//COBOL.SYSLIB DD DSN=&SYSUID..EWS.CPY,DISP=SHR
   ... same for EWSVLOAN, EWSMATCH, EWSRPT
```

`IGYWCL` is the site's catalogued procedure (`VENDOR.PROCLIB`) for Enterprise COBOL 6.5 (`IGY650.SIGYCOMP`): step `COBOL` runs the compiler on `&SYSUID..CBL(&SRC)`, step `LKED` runs the binder into `&SYSUID..LOAD(&SRC)` if the compile RC < 8. The added `COBOL.SYSLIB` DD lets `COPY CUSTREC.` etc. find the copybooks. All four programs compile with RC 0.

## 2. EWSBATCH — the main batch

Symbols (sent as `X-IBM-JCL-Symbol-*` headers on the z/OSMF submit): `ASOFDT` = as-of date `YYYYMMDD`, `MODE` = `SCORE` or `TRAIN`.

| Step | Program | Input → Output | Control | Normal RC |
|---|---|---|---|---|
| STEP005 | IEFBR14 | deletes the 13 outputs of the previous run (`DISP=(MOD,DELETE,DELETE)` works whether or not they exist) | | 0 |
| STEP006 | IEFBR14 | allocates `REJECTS` (FB 120) and `CTLTOT` (FB 80), which later steps extend with `DISP=MOD` | | 0 |
| STEP010 | ICETOOL | `CUSTMAST` → `CUST.SRT` + `CUST.DUPS` | `CNTL(SRTCUST)` | 0 |
| STEP020 | DFSORT | `LOANMAST` → `LOAN.SRT` | `CNTL(SRTLOAN)` | 0 |
| STEP030 | DFSORT | `REPAYHST` → `REPAY.SRT`, bad → `REJECTS` | `CNTL(SRTREPAY)` | 0 |
| STEP040 | DFSORT | `TXNSUMM` → `TXN.SRT`, bad → `REJECTS` | `CNTL(SRTTXN)` | 0 |
| STEP050 | EWSVCUST | `CUST.SRT` → `CUST.VALID`, bad → `REJECTS`, totals → `CTLTOT` | | 0 or 4 |
| STEP060 | EWSVLOAN | `LOAN.SRT` → `LOAN.VALID`, bad → `REJECTS`, totals → `CTLTOT` | | 0 or 4 |
| STEP070 | EWSMATCH | `CUST.VALID` + `LOAN.VALID` + `REPAY.SRT` + `TXN.SRT` → `FEATURES`, `EXCEPT`, `CTLTOT` | `PARM='&ASOFDT.&MODE'` | 0 or 4 |
| STEP080 | DFSORT | `FEATURES` → `FEATCSV` | `CNTL(FEAT2CSV)` | 0 |
| STEP090 | IKJEFT1B (TSO batch) | runs REXX `EWSRECON` over all files → `RUNCTL` | `PARM='%EWSRECON &ASOFDT &MODE'` | 0 (8 if out of balance) |

Every step from STEP010 on is wrapped in `// IF (RC <= 4) THEN ... // ENDIF`. `RC` in a JCL `IF` is the highest return code of all steps so far, so after any step ends with RC ≥ 8 (or abends), all later steps are skipped (`IEF272I ... NOT EXECUTED`) and no features are produced. A typical successful run ends `CC 0004` because the synthetic data always contains a few bad records.

### 2.1 DFSORT / ICETOOL control statements

**SRTCUST (ICETOOL)** — sort and remove duplicate customer IDs, keeping the first occurrence and saving the rest for reconciliation:
```
  SELECT FROM(IN) TO(OUT) ON(1,8,CH) FIRST DISCARD(DUPS)
```
(DFSORT's `SUM FIELDS=NONE,XSUM` is not supported on this system, `ICE172A`.)

**SRTLOAN** — `SORT FIELDS=(11,8,CH,A,1,10,CH,A)` (customer, loan).

**SRTREPAY** — sort, and split good from bad records with a numeric test on every numeric field (`ZD,EQ,NUM` is true when the bytes are valid zoned-decimal digits):
```
  SORT FIELDS=(11,8,CH,A,1,10,CH,A,22,8,CH,A)
  OUTFIL FNAMES=SORTOUT,
    INCLUDE=(19,3,ZD,EQ,NUM,AND,22,8,ZD,EQ,NUM,AND,30,8,ZD,EQ,NUM,AND,
             38,9,ZD,EQ,NUM,AND,47,9,ZD,EQ,NUM,AND,56,3,ZD,EQ,NUM)
  OUTFIL FNAMES=BADREC,
    OMIT=(...same condition...),
    BUILD=(C'REPAYHST',1,10,C'S01 ',
           C'NON-NUMERIC FIELD IN REPAYMENT',10X,1,58)
```
The second `OUTFIL` reformats each bad record into the 120-byte REJREC layout, so DFSORT rejects and COBOL rejects share one file.

**SRTTXN** — the same pattern for account summaries (reason `S02`).

**FEAT2CSV** — generated from `ml/layouts.py` (`feat2csv_control()`; a test checks the member equals the generated text):
```
  OPTION COPY
  INREC BUILD=(1,8,C',',9,8,C',',17,1,C',',18,3,C',', ... ,145,1)
  OUTFIL FNAMES=SORTOUT,FTOV,VLTRIM=C' ',REMOVECC,
    HEADER1=(C'cust_id,as_of_date,emp_type,...,label_stress_90d'),
    BUILD=(1,173,SQZ=(SHIFT=LEFT),300X)
```
`INREC` inserts a comma after each field; `SQZ` removes the blanks left by numeric editing (`   45.20` → `45.20`); `FTOV` + `VLTRIM` write variable-length records without trailing blanks; `HEADER1` adds the column names. The result is a standard CSV that pandas reads directly.

**SRTSCORE** (EWSRPTJ) — `SORT FIELDS=(17,5,ZD,D,1,8,CH,A)`: highest probability first.

### 2.2 COBOL program EWSVCUST — validate customers

Reads `CUSTIN` sequentially. For each record, an `EVALUATE TRUE` applies the checks in order; the first failing check writes one REJREC (`OPEN EXTEND REJECTS`), otherwise the record is copied to `CUSTOUT`.

| Code | Check |
|---|---|
| C01 | customer ID blank |
| C02 | age not numeric (`CU-AGE NOT NUMERIC`) |
| C03 | age outside 21–75 |
| C04 | income not numeric or zero |
| C05 | credit score not numeric or outside 300–900 |
| C06 | open date not numeric or `FUNCTION TEST-DATE-YYYYMMDD(...) NOT = 0` |
| C07 | employment type not S/E/B (88-level `CU-EMP-VALID`) |
| C08 | status not A/C |

Writes `CUST-READ`, `CUST-VALID`, `CUST-REJECTED` to `CTLTOT`. Return code: 0 if nothing rejected, 4 if some, **8 if more than 10%** (which stops the batch), 16 on a file error.

### 2.3 COBOL program EWSVLOAN — validate loans

Same structure. Codes: L01 IDs blank, L02 type not H/C/P/E, L03 principal, L04 EMI, L05 tenure 1–360, L06 start date, L07 due day 1–28, L08 status A/C/D, L09 rate/outstanding not numeric.

### 2.4 COBOL program EWSMATCH — match files and build features

**Input order.** All four inputs are sorted by customer ID first (DFSORT steps), which allows a single sequential pass.

**Balanced-line match.** The program keeps the current key of each file (`HIGH-VALUES` at end of file). For each customer:

```
read next customer C
while loan.key  < C.id : write exception M01, read next loan          (loan without customer)
while loan.key  = C.id : add loan to a 20-entry table, read next
while repay.key < C.id : write exception M02, read next repayment
while repay.key = C.id : accumulate repayment (if its loan is in the table, else M02), read next
while txn.key   < C.id : write exception M03, read next summary
while txn.key   = C.id : accumulate summary, read next
decide: closed customer → skip | no active loan → skip | in default → skip | else write FEATREC
after the last customer, everything left in the other files is an exception
```

This is the classic sequential "match/merge" used in batch COBOL: no indexes, one read of every file, memory independent of file size.

**As-of logic (no look-ahead).** `PARM` gives the as-of date. Using `FUNCTION INTEGER-OF-DATE` for day arithmetic and `year*12+month` for month arithmetic:

* A loan is *active* if it started on/before the as-of date and `months elapsed < tenure`.
* For an installment due on/before the as-of date, the status *as known on that date* is used: if it was paid on/before the as-of date, its recorded status and DPD; otherwise DPD = as-of − due date and status M (> 30 days), L (> 0) or P. An installment unpaid for 90+ days marks the customer as **already in default**; those customers are excluded (no longer an *early* warning).
* Windows: last 3 / 6 / 12 months before the as-of date.
* **TRAIN mode only**: installments due in the 90 days after the as-of date set the label to 1 if missed, bounced or 30+ days late.

**Features computed** (per customer; details in [ML_MODEL.md](ML_MODEL.md)): active loans, total EMI, EMI-to-income, longest remaining tenure, installments due in 12 months, late/missed/partial counts, EMI bounces, max and average days past due, DPD trend (last 3 vs previous 3 months), 3-month average/minimum balance and balance trend, savings-to-EMI, months without salary, debit-to-credit ratio, spending trend, credit-card utilisation. Ratios are computed with `COMPUTE ... ROUNDED` in packed decimal and clamped to the range of their edited PIC.

**Exception codes:** M01 loan without valid customer, M02 repayment without valid loan, M03 account summary without valid customer, M04 invalid repayment date, M05 more than 20 loans for one customer.

**Control totals:** `CUST-READ`, `LOAN-READ`, `REPAY-READ`, `TXN-READ`, `FEATURES-WRITTEN`, `EXCL-CLOSED`, `EXCL-NO-LOAN`, `EXCL-DEFAULT`, `EXCEPTIONS`, `LABEL-POSITIVE`.

RC 0, or 4 when exceptions were written; 12 for a bad PARM; 16 for a file error.

### 2.5 REXX exec EWSRECON — reconciliation

Runs under TSO in batch (`IKJEFT1B`, which passes the exec's return code back as the step RC). It:

1. counts every input and intermediate file with `EXECIO 2000 DISKR` in a loop (so large files are not loaded into memory at once);
2. reads `REJECTS` and counts rejects per source file and per reason code;
3. reads the `CTLTOT` totals written by the three COBOL programs;
4. applies seven balancing rules:

| Check | Rule |
|---|---|
| CHK_CUST_SORT | CUSTMAST records = CUST.SRT + CUST.DUPS |
| CHK_CUST_VALID | CUST.SRT = valid + rejected (EWSVCUST), and rejected = CUSTMAST rejects in REJECTS |
| CHK_LOAN | LOANMAST = LOAN.SRT = valid + rejected (EWSVLOAN) |
| CHK_REPAY | REPAYHST = REPAY.SRT + S01 rejects, and REPAY.SRT = records EWSMATCH read |
| CHK_TXN | TXNSUMM = TXN.SRT + S02 rejects, and TXN.SRT = records EWSMATCH read |
| CHK_MATCH | EWSMATCH read exactly the valid customers and valid loans |
| CHK_FEATURES | FEATURES records = written total = customers − closed − no loan − in default |

5. writes all counts and checks as `KEY=VALUE` lines to `RUNCTL`, ending with `STATUS=OK` or `STATUS=OUT_OF_BALANCE` (RC 8).

The backend downloads `RUNCTL` and **refuses to train or score unless `STATUS=OK`**. A real RUNCTL from the 1,500-customer run:

```
ASOF=20260930  MODE=SCORE  CUSTMAST_IN=1503  CUST_DUPLICATES=3  CUST_VALID=1475  CUST_REJECTED=25
LOANMAST_IN=2381  LOAN_VALID=2352  LOAN_REJECTED=29  REPAYHST_IN=37358  REPAY_REJECTED=149
TXNSUMM_IN=36001  TXN_REJECTED=144  MATCH_CUSTOMERS=1475  MATCH_EXCEPTIONS=1624
EXCL_CLOSED=16  EXCL_NO_LOAN=371  EXCL_DEFAULT=65  FEATURES=1023
CHK_CUST_SORT=OK ... CHK_FEATURES=OK  STATUS=OK
```
(1475 − 16 − 371 − 65 = 1023.)

## 3. EWSRPTJ — intervention report

| Step | Program | Action |
|---|---|---|
| STEP005 | IEFBR14 | delete the previous `SCORES.SRT` and `RISKRPT` |
| STEP010 | DFSORT `SRTSCORE` | `SCORES` → `SCORES.SRT`, highest probability first |
| STEP020 | EWSRPT (only if STEP010 RC = 0) | prints `RISKRPT` (FBA 133): page headings with as-of date and page number, one line per customer (rank, ID, risk %, tier, action, total EMI, top risk factor), and totals per tier with the EMI amount at risk |

```
EWS - EARLY WARNING CREDIT RISK SYSTEM        EARLY INTERVENTION LIST       AS-OF  2026-09-30          PAGE    1
   RANK  CUSTOMER  RISK %  TIER    ACTN          TOTAL EMI INR  TOP RISK FACTOR
 ------------------------------------------------------------------------------------------------------------
       1  CUST0166   88.11  HIGH    INTV     13,312.41     SPEND-TO-INCOME (3 M)
       2  CUST1155   87.83  HIGH    INTV     12,034.72     SPEND-TO-INCOME (3 M)
 ...
 HIGH RISK                  44    EMI AT RISK INR         799,147.67
 MEDIUM RISK                40    EMI AT RISK INR         681,323.63
 LOW RISK                  939    EMI AT RISK INR      15,335,473.92
```

## 4. Return code policy

| Program | 0 | 4 | 8 | 12 | 16 |
|---|---|---|---|---|---|
| EWSVCUST / EWSVLOAN | all valid | some rejected | > 10% rejected (stops batch) | | file error |
| EWSMATCH | ok | exceptions written | | bad PARM | file error |
| EWSRECON | in balance | | out of balance | | |
| EWSRPT | ok | no scores | | | file error |

The backend treats RC ≤ 4 as success for EWSBATCH and EWSCOMP and RC 0 for EWSRPTJ.

## 5. Changing the mainframe code

1. Edit the file in `CP/mainframe/...` (keep COBOL code in columns 8–72, JCL/DFSORT lines ≤ 71 columns, ASCII only; `make test` checks this).
2. If a record layout changes, change the copybook **and** `ml/layouts.py` (and `ml/features_ref.py` for rule changes). For FEATREC, regenerate the DFSORT member: `python -c "from ml.layouts import feat2csv_control; open('mainframe/sortcntl/FEAT2CSV','w').write(feat2csv_control())"`.
3. In the dashboard: **Recompile COBOL** (copybooks + COBOL) or **Run setup again** (everything).
4. Run a batch and `make test`: the golden test compares the new mainframe output with the Python rules.

## 6. Reason codes

| Code | Source | Meaning |
|---|---|---|
| S01 | DFSORT SRTREPAY | non-numeric field in a repayment record |
| S02 | DFSORT SRTTXN | non-numeric field in an account summary |
| C01–C08 | EWSVCUST | customer validation, see 2.2 |
| L01–L09 | EWSVLOAN | loan validation, see 2.3 |
| M01–M05 | EWSMATCH | matching exceptions, see 2.4 |
| DUP | ICETOOL SRTCUST | duplicate customer ID (in `CUST.DUPS`, not in REJECTS) |
