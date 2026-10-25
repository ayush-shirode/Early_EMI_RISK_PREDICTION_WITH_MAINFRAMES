       IDENTIFICATION DIVISION.
       PROGRAM-ID. EWSMATCH.
      *================================================================*
      * EWSMATCH - MATCH CUSTOMERS, LOANS, REPAYMENTS AND ACCOUNT      *
      *            SUMMARIES AND BUILD ONE ML FEATURE RECORD PER       *
      *            ELIGIBLE CUSTOMER (BALANCED-LINE MATCH ON CUST-ID)  *
      *                                                                *
      *   PARM    : YYYYMMDDMODE   E.G. '20260930SCORE'                *
      *             AS-OF DATE - ONLY DATA DUE ON/BEFORE IT IS USED    *
      *             MODE TRAIN - ALSO DERIVE LABEL FROM THE 90 DAYS    *
      *                          AFTER THE AS-OF DATE                  *
      *             MODE SCORE - NO LABEL                              *
      *   CUSTIN  : EWS.CUST.VALID   SORTED BY CUST-ID           FB100 *
      *   LOANIN  : EWS.LOAN.VALID   SORTED BY CUST-ID, LOAN-ID  FB 80 *
      *   REPAYIN : EWS.REPAY.SRT    SORTED BY CUST, LOAN, DUE   FB 80 *
      *   TXNIN   : EWS.TXN.SRT      SORTED BY CUST-ID, YYYYMM   FB 80 *
      *   FEATOUT : EWS.FEATURES     FEATREC                     FB200 *
      *   EXCEPT  : EWS.EXCEPT       REJREC                      FB120 *
      *   CTLTOT  : EWS.CTLTOT       CONTROL TOTALS (DISP=MOD)   FB 80 *
      *                                                                *
      *   EXCEPTION CODES                                              *
      *     M01 LOAN WITHOUT VALID CUSTOMER                            *
      *     M02 REPAYMENT WITHOUT VALID LOAN                           *
      *     M03 ACCOUNT SUMMARY WITHOUT VALID CUSTOMER                 *
      *     M04 REPAYMENT HAS AN INVALID DATE                          *
      *     M05 MORE THAN 20 LOANS FOR ONE CUSTOMER                    *
      *   CUSTOMERS NOT SCORED (COUNTED, NOT EXCEPTIONS)               *
      *     CLOSED CUSTOMER, NO ACTIVE LOAN AT AS-OF, ALREADY IN       *
      *     DEFAULT (AN INSTALLMENT UNPAID FOR 90+ DAYS AT AS-OF)      *
      *                                                                *
      *   RETURN CODE  0 OK   4 EXCEPTIONS WRITTEN   12 BAD PARM       *
      *                16 FILE ERROR                                   *
      *================================================================*
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUST-IN   ASSIGN TO CUSTIN  FILE STATUS IS WS-FS-CUST.
           SELECT LOAN-IN   ASSIGN TO LOANIN  FILE STATUS IS WS-FS-LOAN.
           SELECT REPAY-IN  ASSIGN TO REPAYIN FILE STATUS IS WS-FS-REP.
           SELECT TXN-IN    ASSIGN TO TXNIN   FILE STATUS IS WS-FS-TXN.
           SELECT FEAT-OUT  ASSIGN TO FEATOUT FILE STATUS IS WS-FS-FEAT.
           SELECT EXC-FILE  ASSIGN TO EXCEPT  FILE STATUS IS WS-FS-EXC.
           SELECT CTL-FILE  ASSIGN TO CTLTOT  FILE STATUS IS WS-FS-CTL.

       DATA DIVISION.
       FILE SECTION.
       FD  CUST-IN   RECORDING MODE F.
           COPY CUSTREC.
       FD  LOAN-IN   RECORDING MODE F.
           COPY LOANREC.
       FD  REPAY-IN  RECORDING MODE F.
           COPY REPAYREC.
       FD  TXN-IN    RECORDING MODE F.
           COPY TXNREC.
       FD  FEAT-OUT  RECORDING MODE F.
           COPY FEATREC.
       FD  EXC-FILE  RECORDING MODE F.
           COPY REJREC.
       FD  CTL-FILE  RECORDING MODE F.
       01  CTL-FILE-REC              PIC X(80).

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FS-CUST            PIC XX.
           05  WS-FS-LOAN            PIC XX.
           05  WS-FS-REP             PIC XX.
           05  WS-FS-TXN             PIC XX.
           05  WS-FS-FEAT            PIC XX.
           05  WS-FS-EXC             PIC XX.
           05  WS-FS-CTL             PIC XX.

      *    CURRENT MATCH KEY OF EACH INPUT (HIGH-VALUES AT END OF FILE)
       01  WS-KEYS.
           05  WS-CUST-KEY           PIC X(8).
           05  WS-LOAN-KEY           PIC X(8).
           05  WS-REPAY-KEY          PIC X(8).
           05  WS-TXN-KEY            PIC X(8).

       01  WS-RUN.
           05  WS-ASOF               PIC 9(8).
           05  WS-ASOF-X REDEFINES WS-ASOF.
               10  WS-ASOF-YYYY      PIC 9(4).
               10  WS-ASOF-MM        PIC 99.
               10  WS-ASOF-DD        PIC 99.
           05  WS-MODE               PIC X(5).
               88  MODE-TRAIN                  VALUE 'TRAIN'.
               88  MODE-SCORE                  VALUE 'SCORE'.
           05  WS-ASOF-INT           PIC S9(9) COMP.
           05  WS-ASOF-IDX           PIC S9(9) COMP.
           05  WS-LABEL-END          PIC S9(9) COMP.

       01  WS-DATE-WORK              PIC 9(8).
       01  WS-DATE-WORK-X REDEFINES WS-DATE-WORK.
           05  WS-DW-YYYY            PIC 9(4).
           05  WS-DW-MM              PIC 99.
           05  WS-DW-DD              PIC 99.
       01  WS-YM-WORK                PIC 9(6).
       01  WS-YM-WORK-X REDEFINES WS-YM-WORK.
           05  WS-YM-YYYY            PIC 9(4).
           05  WS-YM-MM              PIC 99.

      *    LOANS OF THE CURRENT CUSTOMER
       01  WS-LOAN-TABLE.
           05  WS-LOAN-CNT           PIC S9(4) COMP VALUE 0.
           05  WS-LOAN-ENTRY OCCURS 20 TIMES.
               10  WT-LOAN-ID        PIC X(10).
       01  WS-I                      PIC S9(4) COMP.
       01  WS-FOUND                  PIC X.

      *    PER-CUSTOMER ACCUMULATORS (RESET FOR EVERY CUSTOMER)
       01  WS-ACC.
           05  WS-ACTIVE-LOANS       PIC S9(4)       COMP-3.
           05  WS-TOTAL-EMI          PIC S9(9)V99    COMP-3.
           05  WS-TENURE-MAX         PIC S9(4)       COMP-3.
           05  WS-INST-12M           PIC S9(4)       COMP-3.
           05  WS-LATE-3M            PIC S9(4)       COMP-3.
           05  WS-LATE-12M           PIC S9(4)       COMP-3.
           05  WS-MISSED-12M         PIC S9(4)       COMP-3.
           05  WS-PARTIAL-12M        PIC S9(4)       COMP-3.
           05  WS-EMI-BOUNCE-6M      PIC S9(4)       COMP-3.
           05  WS-MAX-DPD            PIC S9(4)       COMP-3.
           05  WS-DPD-SUM-6          PIC S9(7)       COMP-3.
           05  WS-DPD-N-6            PIC S9(4)       COMP-3.
           05  WS-DPD-SUM-R          PIC S9(7)       COMP-3.
           05  WS-DPD-N-R            PIC S9(4)       COMP-3.
           05  WS-DPD-SUM-P          PIC S9(7)       COMP-3.
           05  WS-DPD-N-P            PIC S9(4)       COMP-3.
           05  WS-IN-DEFAULT         PIC X.
           05  WS-LABEL              PIC X.
           05  WS-TX-N-R             PIC S9(4)       COMP-3.
           05  WS-TX-N-P             PIC S9(4)       COMP-3.
           05  WS-BAL-SUM-R          PIC S9(11)V99   COMP-3.
           05  WS-BAL-SUM-P          PIC S9(11)V99   COMP-3.
           05  WS-CRED-R             PIC S9(11)V99   COMP-3.
           05  WS-DEB-R              PIC S9(11)V99   COMP-3.
           05  WS-DEB-P              PIC S9(11)V99   COMP-3.
           05  WS-CC-SUM             PIC S9(7)V99    COMP-3.
           05  WS-MIN-BAL            PIC S9(9)V99    COMP-3.
           05  WS-TXN-BOUNCE         PIC S9(4)       COMP-3.
           05  WS-SALARY-MISS        PIC S9(4)       COMP-3.

      *    SCRATCH FIELDS
       01  WS-CALC.
           05  WS-ELAPSED            PIC S9(9)       COMP.
           05  WS-M-AGO              PIC S9(9)       COMP.
           05  WS-DUE-INT            PIC S9(9)       COMP.
           05  WS-EFF-DPD            PIC S9(9)       COMP.
           05  WS-EFF-STATUS         PIC X.
           05  WS-AVG-R              PIC S9(9)V9(6)  COMP-3.
           05  WS-AVG-P              PIC S9(9)V9(6)  COMP-3.
           05  WS-VAL2               PIC S9(11)V99   COMP-3.
           05  WS-VAL4               PIC S9(9)V9(4)  COMP-3.

       01  WS-TOTALS.
           05  WS-CNT-CUST           PIC 9(9) VALUE 0.
           05  WS-CNT-LOAN           PIC 9(9) VALUE 0.
           05  WS-CNT-REPAY          PIC 9(9) VALUE 0.
           05  WS-CNT-TXN            PIC 9(9) VALUE 0.
           05  WS-CNT-FEAT           PIC 9(9) VALUE 0.
           05  WS-CNT-EXC            PIC 9(9) VALUE 0.
           05  WS-CNT-CLOSED         PIC 9(9) VALUE 0.
           05  WS-CNT-NOLOAN         PIC 9(9) VALUE 0.
           05  WS-CNT-DEFAULT        PIC 9(9) VALUE 0.
           05  WS-CNT-POSITIVE       PIC 9(9) VALUE 0.
           COPY CTLREC.

       LINKAGE SECTION.
       01  PARM-AREA.
           05  PARM-LEN              PIC S9(4) COMP.
           05  PARM-ASOF             PIC X(8).
           05  PARM-MODE             PIC X(5).

       PROCEDURE DIVISION USING PARM-AREA.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2100-READ-CUST
           PERFORM 2200-READ-LOAN
           PERFORM 2300-READ-REPAY
           PERFORM 2400-READ-TXN
           PERFORM UNTIL WS-CUST-KEY = HIGH-VALUES
               PERFORM 3000-PROCESS-CUSTOMER
               PERFORM 2100-READ-CUST
           END-PERFORM
      *    WHATEVER IS LEFT HAS NO VALID CUSTOMER
           PERFORM UNTIL WS-LOAN-KEY = HIGH-VALUES
               PERFORM 3110-LOAN-ORPHAN
           END-PERFORM
           PERFORM UNTIL WS-REPAY-KEY = HIGH-VALUES
               PERFORM 3210-REPAY-ORPHAN
           END-PERFORM
           PERFORM UNTIL WS-TXN-KEY = HIGH-VALUES
               PERFORM 3310-TXN-ORPHAN
           END-PERFORM
           PERFORM 8000-TOTALS
           PERFORM 9000-CLOSE
           GOBACK.

      *----------------------------------------------------------------*
       1000-INIT.
           IF PARM-LEN < 13 OR PARM-ASOF NOT NUMERIC
               DISPLAY 'EWSMATCH PARM MUST BE YYYYMMDDSCORE|TRAIN'
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           MOVE PARM-ASOF TO WS-ASOF
           MOVE PARM-MODE TO WS-MODE
           IF FUNCTION TEST-DATE-YYYYMMDD(WS-ASOF) NOT = 0
           OR NOT (MODE-TRAIN OR MODE-SCORE)
               DISPLAY 'EWSMATCH INVALID PARM: ' PARM-ASOF PARM-MODE
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           COMPUTE WS-ASOF-INT = FUNCTION INTEGER-OF-DATE(WS-ASOF)
           COMPUTE WS-ASOF-IDX = WS-ASOF-YYYY * 12 + WS-ASOF-MM
           COMPUTE WS-LABEL-END = WS-ASOF-INT + 90
           DISPLAY 'EWSMATCH AS-OF=' WS-ASOF ' MODE=' WS-MODE
           OPEN INPUT  CUST-IN LOAN-IN REPAY-IN TXN-IN
                OUTPUT FEAT-OUT EXC-FILE
                EXTEND CTL-FILE
           IF WS-FS-CUST NOT = '00' OR WS-FS-LOAN NOT = '00'
           OR WS-FS-REP  NOT = '00' OR WS-FS-TXN  NOT = '00'
           OR WS-FS-FEAT NOT = '00' OR WS-FS-EXC  NOT = '00'
           OR WS-FS-CTL  NOT = '00'
               DISPLAY 'EWSMATCH OPEN ERROR FS=' WS-FILE-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF.

      *----------------------------------------------------------------*
       2100-READ-CUST.
           READ CUST-IN
               AT END MOVE HIGH-VALUES TO WS-CUST-KEY
               NOT AT END
                   MOVE CU-CUST-ID TO WS-CUST-KEY
                   ADD 1 TO WS-CNT-CUST
           END-READ.

       2200-READ-LOAN.
           READ LOAN-IN
               AT END MOVE HIGH-VALUES TO WS-LOAN-KEY
               NOT AT END
                   MOVE LN-CUST-ID TO WS-LOAN-KEY
                   ADD 1 TO WS-CNT-LOAN
           END-READ.

       2300-READ-REPAY.
           READ REPAY-IN
               AT END MOVE HIGH-VALUES TO WS-REPAY-KEY
               NOT AT END
                   MOVE RP-CUST-ID TO WS-REPAY-KEY
                   ADD 1 TO WS-CNT-REPAY
           END-READ.

       2400-READ-TXN.
           READ TXN-IN
               AT END MOVE HIGH-VALUES TO WS-TXN-KEY
               NOT AT END
                   MOVE TX-CUST-ID TO WS-TXN-KEY
                   ADD 1 TO WS-CNT-TXN
           END-READ.

      *----------------------------------------------------------------*
      * ONE CUSTOMER: CONSUME ITS LOANS, REPAYMENTS AND SUMMARIES      *
      *----------------------------------------------------------------*
       3000-PROCESS-CUSTOMER.
           INITIALIZE WS-ACC
           MOVE 'N' TO WS-IN-DEFAULT
           IF MODE-TRAIN
               MOVE '0' TO WS-LABEL
           ELSE
               MOVE SPACE TO WS-LABEL
           END-IF
           MOVE 0 TO WS-LOAN-CNT

           PERFORM UNTIL WS-LOAN-KEY >= WS-CUST-KEY
               PERFORM 3110-LOAN-ORPHAN
           END-PERFORM
           PERFORM UNTIL WS-LOAN-KEY NOT = WS-CUST-KEY
               PERFORM 3100-ADD-LOAN
               PERFORM 2200-READ-LOAN
           END-PERFORM

           PERFORM UNTIL WS-REPAY-KEY >= WS-CUST-KEY
               PERFORM 3210-REPAY-ORPHAN
           END-PERFORM
           PERFORM UNTIL WS-REPAY-KEY NOT = WS-CUST-KEY
               PERFORM 3200-ADD-REPAY
               PERFORM 2300-READ-REPAY
           END-PERFORM

           PERFORM UNTIL WS-TXN-KEY >= WS-CUST-KEY
               PERFORM 3310-TXN-ORPHAN
           END-PERFORM
           PERFORM UNTIL WS-TXN-KEY NOT = WS-CUST-KEY
               PERFORM 3300-ADD-TXN
               PERFORM 2400-READ-TXN
           END-PERFORM

           EVALUATE TRUE
               WHEN NOT CU-ACTIVE
                   ADD 1 TO WS-CNT-CLOSED
               WHEN WS-ACTIVE-LOANS = 0
                   ADD 1 TO WS-CNT-NOLOAN
               WHEN WS-IN-DEFAULT = 'Y'
                   ADD 1 TO WS-CNT-DEFAULT
               WHEN OTHER
                   PERFORM 3600-WRITE-FEATURES
           END-EVALUATE.

      *----------------------------------------------------------------*
       3100-ADD-LOAN.
           IF WS-LOAN-CNT >= 20
               MOVE 'LOANMAST' TO RJ-SOURCE
               MOVE LN-LOAN-ID TO RJ-KEY
               MOVE 'M05'      TO RJ-REASON-CODE
               MOVE 'MORE THAN 20 LOANS FOR ONE CUSTOMER'
                 TO RJ-REASON-TEXT
               MOVE LOAN-REC(1:58) TO RJ-DATA
               PERFORM 3900-WRITE-EXCEPTION
           ELSE
               ADD 1 TO WS-LOAN-CNT
               MOVE LN-LOAN-ID TO WT-LOAN-ID(WS-LOAN-CNT)
               MOVE LN-START-DATE TO WS-DATE-WORK
               COMPUTE WS-ELAPSED = WS-ASOF-IDX
                                  - (WS-DW-YYYY * 12 + WS-DW-MM)
      *        ACTIVE = STARTED BY AS-OF AND INSTALLMENTS STILL TO PAY
               IF LN-START-DATE <= WS-ASOF
               AND WS-ELAPSED < LN-TENURE
                   ADD 1 TO WS-ACTIVE-LOANS
                   ADD LN-EMI-AMT TO WS-TOTAL-EMI
                   IF LN-TENURE - WS-ELAPSED > WS-TENURE-MAX
                       COMPUTE WS-TENURE-MAX = LN-TENURE - WS-ELAPSED
                   END-IF
               END-IF
           END-IF.

       3110-LOAN-ORPHAN.
           MOVE 'LOANMAST'     TO RJ-SOURCE
           MOVE LN-LOAN-ID     TO RJ-KEY
           MOVE 'M01'          TO RJ-REASON-CODE
           MOVE 'LOAN WITHOUT VALID CUSTOMER' TO RJ-REASON-TEXT
           MOVE LOAN-REC(1:58) TO RJ-DATA
           PERFORM 3900-WRITE-EXCEPTION
           PERFORM 2200-READ-LOAN.

      *----------------------------------------------------------------*
       3200-ADD-REPAY.
           MOVE 'N' TO WS-FOUND
           PERFORM VARYING WS-I FROM 1 BY 1
                   UNTIL WS-I > WS-LOAN-CNT OR WS-FOUND = 'Y'
               IF WT-LOAN-ID(WS-I) = RP-LOAN-ID
                   MOVE 'Y' TO WS-FOUND
               END-IF
           END-PERFORM
           EVALUATE TRUE
               WHEN WS-FOUND = 'N'
                   MOVE 'M02' TO RJ-REASON-CODE
                   MOVE 'REPAYMENT WITHOUT VALID LOAN'
                     TO RJ-REASON-TEXT
                   PERFORM 3220-REPAY-EXCEPTION
               WHEN FUNCTION TEST-DATE-YYYYMMDD(RP-DUE-DATE) NOT = 0
                   MOVE 'M04' TO RJ-REASON-CODE
                   MOVE 'REPAYMENT DUE DATE INVALID' TO RJ-REASON-TEXT
                   PERFORM 3220-REPAY-EXCEPTION
               WHEN RP-PAID-DATE NOT = 0 AND
                    FUNCTION TEST-DATE-YYYYMMDD(RP-PAID-DATE) NOT = 0
                   MOVE 'M04' TO RJ-REASON-CODE
                   MOVE 'REPAYMENT PAID DATE INVALID' TO RJ-REASON-TEXT
                   PERFORM 3220-REPAY-EXCEPTION
               WHEN OTHER
                   PERFORM 3230-ACCUMULATE-REPAY
           END-EVALUATE.

       3210-REPAY-ORPHAN.
           MOVE 'M02' TO RJ-REASON-CODE
           MOVE 'REPAYMENT WITHOUT VALID LOAN' TO RJ-REASON-TEXT
           PERFORM 3220-REPAY-EXCEPTION
           PERFORM 2300-READ-REPAY.

       3220-REPAY-EXCEPTION.
           MOVE 'REPAYHST'      TO RJ-SOURCE
           MOVE RP-LOAN-ID      TO RJ-KEY
           MOVE REPAY-REC(1:58) TO RJ-DATA
           PERFORM 3900-WRITE-EXCEPTION.

       3230-ACCUMULATE-REPAY.
           MOVE RP-DUE-DATE TO WS-DATE-WORK
           COMPUTE WS-DUE-INT = FUNCTION INTEGER-OF-DATE(RP-DUE-DATE)
           COMPUTE WS-M-AGO = WS-ASOF-IDX
                            - (WS-DW-YYYY * 12 + WS-DW-MM)
           IF RP-DUE-DATE <= WS-ASOF
      *        STATUS AS IT WAS KNOWN ON THE AS-OF DATE
               IF RP-PAID-DATE > 0 AND RP-PAID-DATE <= WS-ASOF
                   MOVE RP-DPD    TO WS-EFF-DPD
                   MOVE RP-STATUS TO WS-EFF-STATUS
               ELSE
                   COMPUTE WS-EFF-DPD = WS-ASOF-INT - WS-DUE-INT
                   EVALUATE TRUE
                       WHEN WS-EFF-DPD > 30
                           MOVE 'M' TO WS-EFF-STATUS
                       WHEN WS-EFF-DPD > 0
                           MOVE 'L' TO WS-EFF-STATUS
                       WHEN OTHER
                           MOVE 'P' TO WS-EFF-STATUS
                   END-EVALUATE
                   IF WS-EFF-DPD >= 90
                       MOVE 'Y' TO WS-IN-DEFAULT
                   END-IF
               END-IF
               IF WS-EFF-DPD > 999
                   MOVE 999 TO WS-EFF-DPD
               END-IF
               IF WS-M-AGO <= 11
                   ADD 1 TO WS-INST-12M
                   IF WS-EFF-DPD > WS-MAX-DPD
                       MOVE WS-EFF-DPD TO WS-MAX-DPD
                   END-IF
                   EVALUATE WS-EFF-STATUS
                       WHEN 'L'
                           ADD 1 TO WS-LATE-12M
                           IF WS-M-AGO <= 2
                               ADD 1 TO WS-LATE-3M
                           END-IF
                       WHEN 'M'
                           ADD 1 TO WS-MISSED-12M
                       WHEN 'R'
                           ADD 1 TO WS-PARTIAL-12M
                       WHEN 'B'
                           IF WS-M-AGO <= 5
                               ADD 1 TO WS-EMI-BOUNCE-6M
                           END-IF
                   END-EVALUATE
               END-IF
               IF WS-M-AGO <= 5
                   ADD WS-EFF-DPD TO WS-DPD-SUM-6
                   ADD 1          TO WS-DPD-N-6
                   IF WS-M-AGO <= 2
                       ADD WS-EFF-DPD TO WS-DPD-SUM-R
                       ADD 1          TO WS-DPD-N-R
                   ELSE
                       ADD WS-EFF-DPD TO WS-DPD-SUM-P
                       ADD 1          TO WS-DPD-N-P
                   END-IF
               END-IF
           ELSE
      *        FUTURE INSTALLMENT: ONLY USED FOR THE TRAINING LABEL
               IF MODE-TRAIN AND WS-DUE-INT <= WS-LABEL-END
                   IF RP-MISSED OR RP-BOUNCED OR RP-DPD >= 30
                       MOVE '1' TO WS-LABEL
                   END-IF
               END-IF
           END-IF.

      *----------------------------------------------------------------*
       3300-ADD-TXN.
           MOVE TX-YYYYMM TO WS-YM-WORK
           COMPUTE WS-M-AGO = WS-ASOF-IDX
                            - (WS-YM-YYYY * 12 + WS-YM-MM)
           IF WS-M-AGO >= 0 AND WS-M-AGO <= 5
               ADD TX-BOUNCES TO WS-TXN-BOUNCE
               IF TX-SALARY = 0
                   ADD 1 TO WS-SALARY-MISS
               END-IF
               IF WS-M-AGO <= 2
                   ADD 1          TO WS-TX-N-R
                   ADD TX-AVG-BAL TO WS-BAL-SUM-R
                   ADD TX-CREDITS TO WS-CRED-R
                   ADD TX-DEBITS  TO WS-DEB-R
                   ADD TX-CC-UTIL TO WS-CC-SUM
                   IF WS-TX-N-R = 1 OR TX-MIN-BAL < WS-MIN-BAL
                       MOVE TX-MIN-BAL TO WS-MIN-BAL
                   END-IF
               ELSE
                   ADD 1          TO WS-TX-N-P
                   ADD TX-AVG-BAL TO WS-BAL-SUM-P
                   ADD TX-DEBITS  TO WS-DEB-P
               END-IF
           END-IF.

       3310-TXN-ORPHAN.
           MOVE 'TXNSUMM'      TO RJ-SOURCE
           MOVE TX-CUST-ID     TO RJ-KEY
           MOVE 'M03'          TO RJ-REASON-CODE
           MOVE 'ACCOUNT SUMMARY WITHOUT VALID CUSTOMER'
             TO RJ-REASON-TEXT
           MOVE TXN-REC(1:58)  TO RJ-DATA
           PERFORM 3900-WRITE-EXCEPTION
           PERFORM 2400-READ-TXN.

      *----------------------------------------------------------------*
      * BUILD THE FEATURE RECORD. RATIOS ARE CLAMPED TO THE PIC RANGE. *
      *----------------------------------------------------------------*
       3600-WRITE-FEATURES.
           MOVE SPACES             TO FEAT-REC
           MOVE CU-CUST-ID         TO FT-CUST-ID
           MOVE WS-ASOF            TO FT-ASOF
           MOVE CU-EMP-TYPE        TO FT-EMP-TYPE
           MOVE CU-AGE             TO FT-AGE
           MOVE CU-MONTHLY-INCOME  TO FT-INCOME
           MOVE CU-CREDIT-SCORE    TO FT-CREDIT-SCORE
           MOVE WS-ACTIVE-LOANS    TO FT-ACTIVE-LOANS
           MOVE WS-TOTAL-EMI       TO FT-TOTAL-EMI
           COMPUTE WS-VAL4 ROUNDED = WS-TOTAL-EMI / CU-MONTHLY-INCOME
           IF WS-VAL4 > 99.9999
               MOVE 99.9999 TO WS-VAL4
           END-IF
           MOVE WS-VAL4            TO FT-EMI-TO-INCOME
           MOVE WS-TENURE-MAX      TO FT-TENURE-REM
           MOVE WS-INST-12M        TO FT-INST-DUE-12M
           MOVE WS-LATE-3M         TO FT-LATE-3M
           MOVE WS-LATE-12M        TO FT-LATE-12M
           MOVE WS-MISSED-12M      TO FT-MISSED-12M
           MOVE WS-PARTIAL-12M     TO FT-PARTIAL-12M
           MOVE WS-EMI-BOUNCE-6M   TO FT-EMI-BOUNCE-6M
           IF WS-TXN-BOUNCE > 99
               MOVE 99 TO WS-TXN-BOUNCE
           END-IF
           MOVE WS-TXN-BOUNCE      TO FT-TXN-BOUNCE-6M
           MOVE WS-MAX-DPD         TO FT-MAX-DPD-12M

           MOVE 0 TO WS-VAL2
           IF WS-DPD-N-6 > 0
               COMPUTE WS-VAL2 ROUNDED = WS-DPD-SUM-6 / WS-DPD-N-6
           END-IF
           MOVE WS-VAL2            TO FT-AVG-DPD-6M

           MOVE 0 TO WS-AVG-R WS-AVG-P
           IF WS-DPD-N-R > 0
               COMPUTE WS-AVG-R = WS-DPD-SUM-R / WS-DPD-N-R
           END-IF
           IF WS-DPD-N-P > 0
               COMPUTE WS-AVG-P = WS-DPD-SUM-P / WS-DPD-N-P
           END-IF
           COMPUTE WS-VAL2 ROUNDED = WS-AVG-R - WS-AVG-P
           MOVE WS-VAL2            TO FT-DPD-TREND

      *    BALANCE: AVERAGE OF LAST 3 MONTHS VS THE 3 MONTHS BEFORE
           MOVE 0 TO WS-AVG-R WS-AVG-P
           IF WS-TX-N-R > 0
               COMPUTE WS-AVG-R = WS-BAL-SUM-R / WS-TX-N-R
           END-IF
           IF WS-TX-N-P > 0
               COMPUTE WS-AVG-P = WS-BAL-SUM-P / WS-TX-N-P
           END-IF
           COMPUTE WS-VAL2 ROUNDED = WS-AVG-R
           MOVE WS-VAL2            TO FT-AVG-BAL-3M
           MOVE WS-MIN-BAL         TO FT-MIN-BAL-3M
           MOVE 0 TO WS-VAL2
           IF WS-AVG-P > 0
               COMPUTE WS-VAL2 ROUNDED =
                   (WS-AVG-R - WS-AVG-P) / WS-AVG-P * 100
           END-IF
           PERFORM 3610-CLAMP-PCT
           MOVE WS-VAL2            TO FT-BAL-TREND-PCT
           COMPUTE WS-VAL2 ROUNDED = WS-AVG-R / WS-TOTAL-EMI
           IF WS-VAL2 > 9999.99
               MOVE 9999.99 TO WS-VAL2
           END-IF
           MOVE WS-VAL2            TO FT-SAVINGS-TO-EMI
           MOVE WS-SALARY-MISS     TO FT-SALARY-MISS-6M

           EVALUATE TRUE
               WHEN WS-CRED-R > 0
                   COMPUTE WS-VAL4 ROUNDED = WS-DEB-R / WS-CRED-R
               WHEN WS-DEB-R > 0
                   MOVE 999.9999 TO WS-VAL4
               WHEN OTHER
                   MOVE 0 TO WS-VAL4
           END-EVALUATE
           IF WS-VAL4 > 999.9999
               MOVE 999.9999 TO WS-VAL4
           END-IF
           MOVE WS-VAL4            TO FT-DEBIT-CREDIT-3M

      *    SPENDING: AVERAGE MONTHLY DEBITS, LAST 3 VS PREVIOUS 3
           MOVE 0 TO WS-AVG-R WS-AVG-P WS-VAL2
           IF WS-TX-N-R > 0
               COMPUTE WS-AVG-R = WS-DEB-R / WS-TX-N-R
           END-IF
           IF WS-TX-N-P > 0
               COMPUTE WS-AVG-P = WS-DEB-P / WS-TX-N-P
           END-IF
           IF WS-AVG-P > 0
               COMPUTE WS-VAL2 ROUNDED =
                   (WS-AVG-R - WS-AVG-P) / WS-AVG-P * 100
           END-IF
           PERFORM 3610-CLAMP-PCT
           MOVE WS-VAL2            TO FT-SPEND-TREND-PCT

           MOVE 0 TO WS-VAL2
           IF WS-TX-N-R > 0
               COMPUTE WS-VAL2 ROUNDED = WS-CC-SUM / WS-TX-N-R
           END-IF
           MOVE WS-VAL2            TO FT-CC-UTIL-3M
           MOVE WS-LABEL           TO FT-LABEL

           WRITE FEAT-REC
           ADD 1 TO WS-CNT-FEAT
           IF WS-LABEL = '1'
               ADD 1 TO WS-CNT-POSITIVE
           END-IF.

       3610-CLAMP-PCT.
           IF WS-VAL2 > 9999.99
               MOVE 9999.99 TO WS-VAL2
           END-IF
           IF WS-VAL2 < -9999.99
               MOVE -9999.99 TO WS-VAL2
           END-IF.

       3900-WRITE-EXCEPTION.
           WRITE REJ-REC
           ADD 1 TO WS-CNT-EXC.

      *----------------------------------------------------------------*
       8000-TOTALS.
           MOVE 'EWSMATCH'          TO CT-PROGRAM
           MOVE 'CUST-READ'         TO CT-KEY
           MOVE WS-CNT-CUST         TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'LOAN-READ'         TO CT-KEY
           MOVE WS-CNT-LOAN         TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'REPAY-READ'        TO CT-KEY
           MOVE WS-CNT-REPAY        TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'TXN-READ'          TO CT-KEY
           MOVE WS-CNT-TXN          TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'FEATURES-WRITTEN'  TO CT-KEY
           MOVE WS-CNT-FEAT         TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'EXCL-CLOSED'       TO CT-KEY
           MOVE WS-CNT-CLOSED       TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'EXCL-NO-LOAN'      TO CT-KEY
           MOVE WS-CNT-NOLOAN       TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'EXCL-DEFAULT'      TO CT-KEY
           MOVE WS-CNT-DEFAULT      TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'EXCEPTIONS'        TO CT-KEY
           MOVE WS-CNT-EXC          TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'LABEL-POSITIVE'    TO CT-KEY
           MOVE WS-CNT-POSITIVE     TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           DISPLAY 'EWSMATCH CUSTOMERS=' WS-CNT-CUST
                   ' FEATURES=' WS-CNT-FEAT
                   ' EXCEPTIONS=' WS-CNT-EXC
           DISPLAY 'EWSMATCH EXCLUDED CLOSED=' WS-CNT-CLOSED
                   ' NO-LOAN=' WS-CNT-NOLOAN
                   ' DEFAULT=' WS-CNT-DEFAULT
           IF MODE-TRAIN
               DISPLAY 'EWSMATCH POSITIVE LABELS=' WS-CNT-POSITIVE
           END-IF.

       9000-CLOSE.
           CLOSE CUST-IN LOAN-IN REPAY-IN TXN-IN
                 FEAT-OUT EXC-FILE CTL-FILE
           IF WS-CNT-EXC > 0
               MOVE 4 TO RETURN-CODE
           ELSE
               MOVE 0 TO RETURN-CODE
           END-IF.
