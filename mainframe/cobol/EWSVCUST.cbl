       IDENTIFICATION DIVISION.
       PROGRAM-ID. EWSVCUST.
      *================================================================*
      * EWSVCUST - VALIDATE THE CUSTOMER MASTER                        *
      *                                                                *
      *   CUSTIN  : SORTED, DEDUPLICATED CUSTOMERS (EWS.CUST.SRT) FB100*
      *   CUSTOUT : CUSTOMERS THAT PASSED ALL CHECKS (EWS.CUST.VALID)  *
      *   REJECTS : REJREC, ONE PER FAILED RECORD (DISP=MOD)    FB120  *
      *   CTLTOT  : CONTROL TOTALS FOR EWSRECON (DISP=MOD)      FB 80  *
      *                                                                *
      *   REASON CODES (FIRST FAILING CHECK WINS)                      *
      *     C01 CUSTOMER ID BLANK          C05 CREDIT SCORE INVALID    *
      *     C02 AGE NOT NUMERIC            C06 OPEN DATE INVALID       *
      *     C03 AGE OUTSIDE 21-75          C07 EMPLOYMENT TYPE INVALID *
      *     C04 INCOME MISSING OR ZERO     C08 STATUS INVALID          *
      *                                                                *
      *   RETURN CODE  0 ALL VALID   4 SOME REJECTED                   *
      *                8 MORE THAN 10% REJECTED   16 FILE ERROR        *
      *================================================================*
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUST-IN   ASSIGN TO CUSTIN  FILE STATUS IS WS-FS-IN.
           SELECT CUST-OUT  ASSIGN TO CUSTOUT FILE STATUS IS WS-FS-OUT.
           SELECT REJ-FILE  ASSIGN TO REJECTS FILE STATUS IS WS-FS-REJ.
           SELECT CTL-FILE  ASSIGN TO CTLTOT  FILE STATUS IS WS-FS-CTL.

       DATA DIVISION.
       FILE SECTION.
       FD  CUST-IN   RECORDING MODE F.
           COPY CUSTREC.
       FD  CUST-OUT  RECORDING MODE F.
       01  CUST-OUT-REC              PIC X(100).
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
           88  END-OF-CUST                     VALUE 'Y'.
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
           PERFORM UNTIL END-OF-CUST
               PERFORM 3000-VALIDATE
               PERFORM 2000-READ
           END-PERFORM
           PERFORM 8000-TOTALS
           PERFORM 9000-CLOSE
           GOBACK.

       1000-OPEN.
           OPEN INPUT  CUST-IN
                OUTPUT CUST-OUT
                EXTEND REJ-FILE
                EXTEND CTL-FILE
           IF WS-FS-IN  NOT = '00' OR WS-FS-OUT NOT = '00'
           OR WS-FS-REJ NOT = '00' OR WS-FS-CTL NOT = '00'
               DISPLAY 'EWSVCUST OPEN ERROR FS=' WS-FILE-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF.

       2000-READ.
           READ CUST-IN
               AT END SET END-OF-CUST TO TRUE
               NOT AT END ADD 1 TO WS-READ
           END-READ
           IF WS-FS-IN NOT = '00' AND WS-FS-IN NOT = '10'
               DISPLAY 'EWSVCUST READ ERROR FS=' WS-FS-IN
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF.

       3000-VALIDATE.
           MOVE SPACES TO WS-REASON-CODE WS-REASON-TEXT
           EVALUATE TRUE
               WHEN CU-CUST-ID = SPACES
                   MOVE 'C01'  TO WS-REASON-CODE
                   MOVE 'CUSTOMER ID IS BLANK' TO WS-REASON-TEXT
               WHEN CU-AGE NOT NUMERIC
                   MOVE 'C02'  TO WS-REASON-CODE
                   MOVE 'AGE IS NOT NUMERIC' TO WS-REASON-TEXT
               WHEN CU-AGE < 21 OR CU-AGE > 75
                   MOVE 'C03'  TO WS-REASON-CODE
                   MOVE 'AGE OUTSIDE 21-75' TO WS-REASON-TEXT
               WHEN CU-MONTHLY-INCOME NOT NUMERIC
                   MOVE 'C04'  TO WS-REASON-CODE
                   MOVE 'MONTHLY INCOME NOT NUMERIC' TO WS-REASON-TEXT
               WHEN CU-MONTHLY-INCOME = ZERO
                   MOVE 'C04'  TO WS-REASON-CODE
                   MOVE 'MONTHLY INCOME IS ZERO' TO WS-REASON-TEXT
               WHEN CU-CREDIT-SCORE NOT NUMERIC
                   MOVE 'C05'  TO WS-REASON-CODE
                   MOVE 'CREDIT SCORE NOT NUMERIC' TO WS-REASON-TEXT
               WHEN CU-CREDIT-SCORE < 300 OR CU-CREDIT-SCORE > 900
                   MOVE 'C05'  TO WS-REASON-CODE
                   MOVE 'CREDIT SCORE OUTSIDE 300-900'
                     TO WS-REASON-TEXT
               WHEN CU-OPEN-DATE NOT NUMERIC
                   MOVE 'C06'  TO WS-REASON-CODE
                   MOVE 'OPEN DATE NOT NUMERIC' TO WS-REASON-TEXT
               WHEN FUNCTION TEST-DATE-YYYYMMDD(CU-OPEN-DATE) NOT = 0
                   MOVE 'C06'  TO WS-REASON-CODE
                   MOVE 'OPEN DATE IS NOT A VALID DATE'
                     TO WS-REASON-TEXT
               WHEN NOT CU-EMP-VALID
                   MOVE 'C07'  TO WS-REASON-CODE
                   MOVE 'EMPLOYMENT TYPE NOT S/E/B' TO WS-REASON-TEXT
               WHEN NOT CU-STATUS-VALID
                   MOVE 'C08'  TO WS-REASON-CODE
                   MOVE 'CUSTOMER STATUS NOT A/C' TO WS-REASON-TEXT
           END-EVALUATE
           IF WS-REASON-CODE = SPACES
               WRITE CUST-OUT-REC FROM CUST-REC
               ADD 1 TO WS-VALID
           ELSE
               PERFORM 3100-WRITE-REJECT
           END-IF.

       3100-WRITE-REJECT.
           MOVE 'CUSTMAST'       TO RJ-SOURCE
           MOVE CU-CUST-ID       TO RJ-KEY
           MOVE WS-REASON-CODE   TO RJ-REASON-CODE
           MOVE WS-REASON-TEXT   TO RJ-REASON-TEXT
           MOVE CUST-REC(1:58)   TO RJ-DATA
           WRITE REJ-REC
           ADD 1 TO WS-REJECTED.

       8000-TOTALS.
           MOVE 'EWSVCUST'       TO CT-PROGRAM
           MOVE 'CUST-READ'      TO CT-KEY
           MOVE WS-READ          TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'CUST-VALID'     TO CT-KEY
           MOVE WS-VALID         TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           MOVE 'CUST-REJECTED'  TO CT-KEY
           MOVE WS-REJECTED      TO CT-VALUE
           WRITE CTL-FILE-REC FROM CTL-REC
           DISPLAY 'EWSVCUST READ=' WS-READ ' VALID=' WS-VALID
                   ' REJECTED=' WS-REJECTED.

       9000-CLOSE.
           CLOSE CUST-IN CUST-OUT REJ-FILE CTL-FILE
           EVALUATE TRUE
               WHEN WS-REJECTED = 0
                   MOVE 0 TO RETURN-CODE
               WHEN WS-REJECTED * 10 > WS-READ
                   MOVE 8 TO RETURN-CODE
               WHEN OTHER
                   MOVE 4 TO RETURN-CODE
           END-EVALUATE.
