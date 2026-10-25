/* REXX ************************************************************/
/* EWSRECON - RECONCILE THE CONTROL TOTALS OF EWSBATCH             */
/*                                                                 */
/*  ARGS   : ASOF MODE           E.G. 20260930 SCORE               */
/*  DDS IN : CUSTIN LOANIN REPAYIN TXNIN   (ORIGINAL INPUT FILES)  */
/*           CUSTSRT CUSTDUP LOANSRT REPAYSRT TXNSRT (DFSORT OUT)  */
/*           REJECTS (REJREC)  CTLTOT (PROGRAM CONTROL TOTALS)     */
/*           FEATOUT (FEATURE RECORDS)                             */
/*  DD OUT : RUNCTL - ONE KEY=VALUE PER LINE, READ BY THE PYTHON   */
/*           BACKEND. STATUS=OK MEANS EVERY RECORD IS ACCOUNTED    */
/*           FOR AND THE FEATURES CAN BE SCORED.                   */
/*  RC     : 0 IN BALANCE   8 OUT OF BALANCE                       */
/*******************************************************************/
parse upper arg asof mode .
out.0 = 0
call put 'ASOF='asof
call put 'MODE='mode
call put 'RUN_TS='date('S') time()

/* 1. RECORD COUNTS OF EVERY INPUT AND INTERMEDIATE FILE           */
cust_in   = count('CUSTIN')
loan_in   = count('LOANIN')
repay_in  = count('REPAYIN')
txn_in    = count('TXNIN')
cust_srt  = count('CUSTSRT')
cust_dup  = count('CUSTDUP')
loan_srt  = count('LOANSRT')
repay_srt = count('REPAYSRT')
txn_srt   = count('TXNSRT')
feat_out  = count('FEATOUT')

/* 2. REJECTS BY SOURCE FILE AND BY REASON CODE                    */
rej. = 0
rej_code. = 0
codes = ''
"EXECIO * DISKR REJECTS (STEM r. FINIS"
do i = 1 to r.0
  src  = strip(substr(r.i, 1, 8))
  code = strip(substr(r.i, 19, 4))
  rej.src = rej.src + 1
  if wordpos(code, codes) = 0 then codes = codes code
  rej_code.code = rej_code.code + 1
end

/* 3. CONTROL TOTALS WRITTEN BY THE COBOL PROGRAMS                 */
ctl. = 0
"EXECIO * DISKR CTLTOT (STEM c. FINIS"
do i = 1 to c.0
  prog = strip(substr(c.i, 1, 8))
  key  = translate(strip(substr(c.i, 10, 20)), '_', '-')
  ctl.prog.key = strip(substr(c.i, 31, 9)) + 0
end

call put 'CUSTMAST_IN='cust_in
call put 'CUST_DUPLICATES='cust_dup
call put 'CUST_VALID='ctl.EWSVCUST.CUST_VALID
call put 'CUST_REJECTED='ctl.EWSVCUST.CUST_REJECTED
call put 'LOANMAST_IN='loan_in
call put 'LOAN_VALID='ctl.EWSVLOAN.LOAN_VALID
call put 'LOAN_REJECTED='ctl.EWSVLOAN.LOAN_REJECTED
call put 'REPAYHST_IN='repay_in
call put 'REPAY_REJECTED='rej.REPAYHST
call put 'TXNSUMM_IN='txn_in
call put 'TXN_REJECTED='rej.TXNSUMM
call put 'MATCH_CUSTOMERS='ctl.EWSMATCH.CUST_READ
call put 'MATCH_EXCEPTIONS='ctl.EWSMATCH.EXCEPTIONS
call put 'EXCL_CLOSED='ctl.EWSMATCH.EXCL_CLOSED
call put 'EXCL_NO_LOAN='ctl.EWSMATCH.EXCL_NO_LOAN
call put 'EXCL_DEFAULT='ctl.EWSMATCH.EXCL_DEFAULT
call put 'FEATURES='feat_out
call put 'LABEL_POSITIVE='ctl.EWSMATCH.LABEL_POSITIVE
do i = 1 to words(codes)
  code = word(codes, i)
  call put 'REJECT_'code'='rej_code.code
end

/* 4. BALANCING RULES - EVERY INPUT RECORD MUST BE ACCOUNTED FOR   */
bad = 0
call check 'CHK_CUST_SORT',  cust_in = cust_srt + cust_dup
call check 'CHK_CUST_VALID', cust_srt = ctl.EWSVCUST.CUST_VALID +,
                             ctl.EWSVCUST.CUST_REJECTED &,
                             ctl.EWSVCUST.CUST_REJECTED = rej.CUSTMAST
call check 'CHK_LOAN',       loan_in = loan_srt &,
                             loan_srt = ctl.EWSVLOAN.LOAN_VALID +,
                             ctl.EWSVLOAN.LOAN_REJECTED
call check 'CHK_REPAY',      repay_in = repay_srt + rej.REPAYHST &,
                             repay_srt = ctl.EWSMATCH.REPAY_READ
call check 'CHK_TXN',        txn_in = txn_srt + rej.TXNSUMM &,
                             txn_srt = ctl.EWSMATCH.TXN_READ
call check 'CHK_MATCH',      ctl.EWSMATCH.CUST_READ =,
                             ctl.EWSVCUST.CUST_VALID &,
                             ctl.EWSMATCH.LOAN_READ =,
                             ctl.EWSVLOAN.LOAN_VALID
call check 'CHK_FEATURES',   feat_out = ctl.EWSMATCH.FEATURES_WRITTEN &,
                             feat_out = ctl.EWSMATCH.CUST_READ -,
                             ctl.EWSMATCH.EXCL_CLOSED -,
                             ctl.EWSMATCH.EXCL_NO_LOAN -,
                             ctl.EWSMATCH.EXCL_DEFAULT

if bad = 0 then call put 'STATUS=OK'
else call put 'STATUS=OUT_OF_BALANCE'

"EXECIO" out.0 "DISKW RUNCTL (STEM out. FINIS"
do i = 1 to out.0
  say out.i
end
if bad = 0 then exit 0
exit 8

/*-----------------------------------------------------------------*/
count: procedure
  parse arg dd
  n = 0
  do forever
    "EXECIO 2000 DISKR" dd "(STEM rec."
    erc = rc
    n = n + rec.0
    if erc <> 0 then leave          /* RC 2 = END OF FILE          */
  end
  "EXECIO 0 DISKR" dd "(FINIS"
  return n

put: procedure expose out.
  parse arg line
  n = out.0 + 1
  out.n = line
  out.0 = n
  return

check: procedure expose out. bad
  parse arg name, ok
  if ok then call put name'=OK'
  else do
    call put name'=FAIL'
    bad = bad + 1
  end
  return
