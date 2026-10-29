       IDENTIFICATION DIVISION.
       PROGRAM-ID. EWSSUPD.
      *================================================================*
      * EWSSUPD - KEEP THE LATEST SCORE OF EVERY CUSTOMER IN A VSAM    *
      *           KSDS, UPDATED IN PLACE BY KEY (RANDOM ACCESS)        *
      *                                                                *
      *   SCOREIN : EWS.SCORES     SCOREREC FROM PYTHON         FB 80  *
      *   SCOREKS : EWS.SCORKSDS   SCOREVS, KSDS KEY SV-CUST-ID    100 *
      *                                                                *
      *   FOR EVERY SCORE: READ THE KSDS BY CUSTOMER ID                *
      *     FOUND     - KEEP THE OLD SCORE AS PREVIOUS, REWRITE        *
      *     NOT FOUND - WRITE A NEW RECORD                             *
      *   A CLUSTER THAT HAS NEVER HELD A RECORD CANNOT BE OPENED      *
      *   I-O; IT IS THEN OPENED OUTPUT AND LOADED (FIRST RUN).        *
      *                                                                *
      *   RETURN CODE  0 OK   16 FILE ERROR (STOPS AT THE FIRST ONE)   *
      *================================================================*
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SCORE-IN  ASSIGN TO SCOREIN FILE STATUS IS WS-FS-IN.
           SELECT SCORE-KS  ASSIGN TO SCOREKS
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS DYNAMIC
                  RECORD KEY IS SV-CUST-ID
                  FILE STATUS IS WS-FS-KS.

       DATA DIVISION.
       FILE SECTION.
       FD  SCORE-IN  RECORDING MODE F.
           COPY SCOREREC.
       FD  SCORE-KS.
           COPY SCOREVS.

       WORKING-STORAGE SECTION.
       01  WS-FS-IN                  PIC XX.
       01  WS-FS-KS                  PIC XX.
       01  WS-EOF                    PIC X     VALUE 'N'.
           88  END-OF-SCORES                   VALUE 'Y'.
       01  WS-MODE                   PIC X     VALUE 'U'.
           88  LOAD-MODE                       VALUE 'L'.
       01  WS-ERROR                  PIC X     VALUE 'N'.
           88  IO-FAILED                       VALUE 'Y'.
       01  WS-COUNTS.
           05  WS-READ               PIC 9(9)  VALUE 0.
           05  WS-ADDED              PIC 9(9)  VALUE 0.
           05  WS-UPDATED            PIC 9(9)  VALUE 0.
           05  WS-TIER-CHANGED       PIC 9(9)  VALUE 0.

       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-OPEN
           PERFORM 2000-READ
           PERFORM UNTIL END-OF-SCORES
               PERFORM 3000-UPDATE
               IF NOT IO-FAILED
                   PERFORM 2000-READ
               END-IF
           END-PERFORM
           PERFORM 8000-TOTALS
           CLOSE SCORE-IN SCORE-KS
           IF IO-FAILED
               MOVE 16 TO RETURN-CODE
           ELSE
               MOVE 0 TO RETURN-CODE
           END-IF
           GOBACK.

       1000-OPEN.
           OPEN INPUT SCORE-IN
           IF WS-FS-IN NOT = '00'
               DISPLAY 'EWSSUPD OPEN ERROR SCOREIN FS ' WS-FS-IN
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN I-O SCORE-KS
           IF WS-FS-KS NOT = '00' AND WS-FS-KS NOT = '97'
               DISPLAY 'EWSSUPD SCOREKS EMPTY OR NEW (FS ' WS-FS-KS
                       ') - LOADING'
               SET LOAD-MODE TO TRUE
               OPEN OUTPUT SCORE-KS
               IF WS-FS-KS NOT = '00' AND WS-FS-KS NOT = '97'
                   DISPLAY 'EWSSUPD OPEN ERROR SCOREKS FS ' WS-FS-KS
                   MOVE 16 TO RETURN-CODE
                   STOP RUN
               END-IF
           END-IF.

       2000-READ.
           READ SCORE-IN
               AT END SET END-OF-SCORES TO TRUE
           END-READ.

       3000-UPDATE.
           ADD 1 TO WS-READ
           IF LOAD-MODE
               PERFORM 3200-ADD
           ELSE
               MOVE SC-CUST-ID TO SV-CUST-ID
               READ SCORE-KS
                   INVALID KEY CONTINUE
               END-READ
               EVALUATE WS-FS-KS
                   WHEN '00'
                       PERFORM 3100-CHANGE
                   WHEN '23'
                       PERFORM 3200-ADD
                   WHEN OTHER
                       PERFORM 9000-IO-ERROR
               END-EVALUATE
           END-IF.

       3100-CHANGE.
           IF SV-TIER NOT = SC-TIER
               ADD 1 TO WS-TIER-CHANGED
           END-IF
           MOVE SV-ASOF        TO SV-PREV-ASOF
           MOVE SV-PROB        TO SV-PREV-PROB
           MOVE SV-TIER        TO SV-PREV-TIER
           PERFORM 3300-MOVE-SCORE
           ADD 1 TO SV-TIMES-SCORED
           REWRITE SCOREVS-REC
               INVALID KEY CONTINUE
           END-REWRITE
           IF WS-FS-KS = '00'
               ADD 1 TO WS-UPDATED
           ELSE
               PERFORM 9000-IO-ERROR
           END-IF.

       3200-ADD.
           MOVE SPACES         TO SCOREVS-REC
           MOVE SC-CUST-ID     TO SV-CUST-ID
           MOVE ZERO           TO SV-PREV-ASOF SV-PREV-PROB
           MOVE 1              TO SV-TIMES-SCORED
           PERFORM 3300-MOVE-SCORE
           WRITE SCOREVS-REC
               INVALID KEY CONTINUE
           END-WRITE
           IF WS-FS-KS = '00'
               ADD 1 TO WS-ADDED
           ELSE
               PERFORM 9000-IO-ERROR
           END-IF.

       3300-MOVE-SCORE.
           MOVE SC-ASOF        TO SV-ASOF
           MOVE SC-PROB        TO SV-PROB
           MOVE SC-TIER        TO SV-TIER
           MOVE SC-ACTION      TO SV-ACTION
           MOVE SC-TOP-FACTOR  TO SV-TOP-FACTOR
           MOVE SC-TOTAL-EMI   TO SV-TOTAL-EMI.

       8000-TOTALS.
           DISPLAY 'EWSSUPD READ         ' WS-READ
           DISPLAY 'EWSSUPD ADDED        ' WS-ADDED
           DISPLAY 'EWSSUPD UPDATED      ' WS-UPDATED
           DISPLAY 'EWSSUPD TIER-CHANGED ' WS-TIER-CHANGED.

       9000-IO-ERROR.
           DISPLAY 'EWSSUPD VSAM ERROR FS ' WS-FS-KS
                   ' KEY ' SC-CUST-ID
           SET IO-FAILED TO TRUE
           SET END-OF-SCORES TO TRUE.
