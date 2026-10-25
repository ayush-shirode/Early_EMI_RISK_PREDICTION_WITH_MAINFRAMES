       IDENTIFICATION DIVISION.
       PROGRAM-ID. EWSVLOAN.
      *================================================================*
      * EWSVLOAN - VALIDATE THE LOAN MASTER                            *
      *                                                                *
      *   LOANIN  : LOANS SORTED BY CUST-ID + LOAN-ID (EWS.LOAN.SRT)   *
      *   LOANOUT : LOANS THAT PASSED ALL CHECKS (EWS.LOAN.VALID)      *
      *   REJECTS : REJREC, ONE PER FAILED RECORD (DISP=MOD)    FB120  *
      *   CTLTOT  : CONTROL TOTALS FOR EWSRECON (DISP=MOD)      FB 80  *
      *                                                                *
      *   REASON CODES (FIRST FAILING CHECK WINS)                      *
      *     L01 LOAN OR CUSTOMER ID BLANK  L06 START DATE INVALID      *
      *     L02 LOAN TYPE NOT H/C/P/E      L07 DUE DAY OUTSIDE 1-28    *
      *     L03 PRINCIPAL MISSING OR ZERO  L08 LOAN STATUS NOT A/C/D   *
      *     L04 EMI MISSING OR ZERO        L09 RATE/OUTSTANDING INVALID*
      *     L05 TENURE OUTSIDE 1-360                                   *
      *                                                                *
      *   RETURN CODE  0 ALL VALID   4 SOME REJECTED                   *
      *                8 MORE THAN 10% REJECTED   16 FILE ERROR        *
      *================================================================*
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LOAN-IN   ASSIGN TO LOANIN  FILE STATUS IS WS-FS-IN.
           SELECT LOAN-OUT  ASSIGN TO LOANOUT FILE STATUS IS WS-FS-OUT.
           SELECT REJ-FILE  ASSIGN TO REJECTS FILE STATUS IS WS-FS-REJ.
           SELECT CTL-FILE  ASSIGN TO CTLTOT  FILE STATUS IS WS-FS-CTL.

       DATA DIVISION.
       FILE SECTION.
       FD  LOAN-IN   RECORDING MODE F.
           COPY LOANREC.
       FD  LOAN-OUT  RECORDING MODE F.
       01  LOAN-OUT-REC              PIC X(80).
       FD  REJ-FILE  RECORDING MODE F.
           COPY REJREC.
       FD  CTL-FILE  RECORDING MODE F.
       01  CTL-FILE-REC              PIC X(80).

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FS-IN              PIC XX.
           05  WS-FS-OUT             PIC XX.
           05  WS-FS-REJ             PIC XX.
           05  WS-FS-CTL             PIC XX.
       01  WS-EOF                    PIC X     VALUE 'N'.
           88  END-OF-LOAN                     VALUE 'Y'.
       01  WS-COUNTS.
           05  WS-READ               PIC 9(9)  VALUE 0.
           05  WS-VALID              PIC 9(9)  VALUE 0.
           05  WS-REJECTED           PIC 9(9)  VALUE 0.
       01  WS-REASON-CODE            PIC X(4).
       01  WS-REASON-TEXT            PIC X(40).
           COPY CTLREC.

       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-OPEN
           PERFORM 2000-READ
           PERFORM UNTIL END-OF-LOAN
               PERFORM 3000-VALIDATE
               PERFORM 2000-READ
           END-PERFORM
           PERFORM 8000-TOTALS
           PERFORM 9000-CLOSE
           GOBACK.

       1000-OPEN.
           OPEN INPUT  LOAN-IN
                OUTPUT LOAN-OUT
                EXTEND REJ-FILE
                EXTEND CTL-FILE
           IF WS-FS-IN  NOT = '00' OR WS-FS-OUT NOT = '00'
           OR WS-FS-REJ NOT = '00' OR WS-FS-CTL NOT = '00'
               DISPLAY 'EWSVLOAN OPEN ERROR FS=' WS-FILE-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF.

       2000-READ.
           READ LOAN-IN
               AT END SET END-OF-LOAN TO TRUE
               NOT AT END ADD 1 TO WS-READ
           END-READ
           IF WS-FS-IN NOT = '00' AND WS-FS-IN NOT = '10'
               DISPLAY 'EWSVLOAN READ ERROR FS=' WS-FS-IN
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF.

       3000-VALIDATE.
           MOVE SPACES TO WS-REASON-CODE WS-REASON-TEXT
           EVALUATE TRUE
               WHEN LN-LOAN-ID = SPACES OR LN-CUST-ID = SPACES
                   MOVE 'L01'  TO WS-REASON-CODE
                   MOVE 'LOAN OR CUSTOMER ID IS BLANK' TO WS-REASON-TEXT
               WHEN NOT LN-TYPE-VALID
                   MOVE 'L02'  TO WS-REASON-CODE
                   MOVE 'LOAN TYPE NOT H/C/P/E' TO WS-REASON-TEXT
               WHEN LN-PRINCIPAL NOT NUMERIC
                   MOVE 'L03'  TO WS-REASON-CODE
                   MOVE 'PRINCIPAL NOT NUMERIC' TO WS-REASON-TEXT
               WHEN LN-PRINCIPAL = ZERO
                   MOVE 'L03'  TO WS-REASON-CODE
                   MOVE 'PRINCIPAL IS ZERO' TO WS-REASON-TEXT
               WHEN LN-EMI-AMT NOT NUMERIC
                   MOVE 'L04'  TO WS-REASON-CODE
                   MOVE 'EMI AMOUNT NOT NUMERIC' TO WS-REASON-TEXT
               WHEN LN-EMI-AMT = ZERO
                   MOVE 'L04'  TO WS-REASON-CODE
                   MOVE 'EMI AMOUNT IS ZERO' TO WS-REASON-TEXT
               WHEN LN-TENURE NOT NUMERIC
                   MOVE 'L05'  TO WS-REASON-CODE
                   MOVE 'TENURE NOT NUMERIC' TO WS-REASON-TEXT
               WHEN LN-TENURE < 1 OR LN-TENURE > 360
                   MOVE 'L05'  TO WS-REASON-CODE
                   MOVE 'TENURE OUTSIDE 1-360 MONTHS' TO WS-REASON-TEXT
               WHEN LN-START-DATE NOT NUMERIC
                   MOVE 'L06'  TO WS-REASON-CODE
                   MOVE 'START DATE NOT NUMERIC' TO WS-REASON-TEXT
               WHEN FUNCTION TEST-DATE-YYYYMMDD(LN-START-DATE) NOT = 0
                   MOVE 'L06'  TO WS-REASON-CODE
                   MOVE 'START DATE IS NOT A VALID DATE'
                     TO WS-REASON-TEXT
               WHEN LN-DUE-DAY NOT NUMERIC
                   MOVE 'L07'  TO WS-REASON-CODE
                   MOVE 'DUE DAY NOT NUMERIC' TO WS-REASON-TEXT
               WHEN LN-DUE-DAY < 1 OR LN-DUE-DAY > 28
                   MOVE 'L07'  TO WS-REASON-CODE
                   MOVE 'DUE DAY OUTSIDE 1-28' TO WS-REASON-TEXT
               WHEN NOT LN-STATUS-VALID
                   MOVE 'L08'  TO WS-REASON-CODE
                   MOVE 'LOAN STATUS NOT A/C/D' TO WS-REASON-TEXT
               WHEN LN-INT-RATE NOT NUMERIC
                 OR LN-OUTSTANDING NOT NUMERIC
                   MOVE 'L09'  TO WS-REASON-CODE
                   MOVE 'RATE OR OUTSTANDING NOT NUMERIC'
                     TO WS-REASON-TEXT
           END-EVALUATE
           IF WS-REASON-CODE = SPACES
               WRITE LOAN-OUT-REC FROM LOAN-REC
               ADD 1 TO WS-VALID
           ELSE
               PERFORM 3100-WRITE-REJECT
           END-IF.

       3100-WRITE-REJECT.
           MOVE 'LOANMAST'       TO RJ-SOURCE
           MOVE LN-LOAN-ID       TO RJ-KEY
           MOVE WS-REASON-CODE   TO RJ-REASON-CODE
           MOVE WS-REASON-TEXT   TO RJ-REASON-TEXT
           MOVE LOAN-REC(1:58)   TO RJ-DATA
           WRITE REJ-REC
           ADD 1 TO WS-REJECTED.

       8000-TOTALS.
           MOVE 'EWSVLOAN'       TO CT-PROGRAM
           MOVE 'LOAN-READ'      TO CT-KEY
           MOVE WS-READ          TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'LOAN-VALID'     TO CT-KEY
           MOVE WS-VALID         TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'LOAN-REJECTED'  TO CT-KEY
           MOVE WS-REJECTED      TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           DISPLAY 'EWSVLOAN READ=' WS-READ ' VALID=' WS-VALID
                   ' REJECTED=' WS-REJECTED.

       9000-CLOSE.
           CLOSE LOAN-IN LOAN-OUT REJ-FILE CTL-FILE
           EVALUATE TRUE
               WHEN WS-REJECTED = 0
                   MOVE 0 TO RETURN-CODE
               WHEN WS-REJECTED * 10 > WS-READ
                   MOVE 8 TO RETURN-CODE
               WHEN OTHER
                   MOVE 4 TO RETURN-CODE
           END-EVALUATE.
