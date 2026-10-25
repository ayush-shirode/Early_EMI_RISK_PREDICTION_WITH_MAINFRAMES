       IDENTIFICATION DIVISION.
       PROGRAM-ID. EWSRPT.
      *================================================================*
      * EWSRPT  - EARLY INTERVENTION LIST                              *
      *           PRINTS THE MODEL SCORES WRITTEN BACK FROM PYTHON,    *
      *           HIGHEST RISK FIRST, WITH TOTALS PER RISK TIER.       *
      *                                                                *
      *   SCOREIN : EWS.SCORES.SRT  SCOREREC SORTED BY PROB DESC FB 80 *
      *   RPTOUT  : EWS.RISKRPT     PRINT LINES WITH ASA CTL   FBA 133 *
      *                                                                *
      *   RETURN CODE  0 OK   4 NO SCORES   16 FILE ERROR              *
      *================================================================*
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SCORE-IN  ASSIGN TO SCOREIN FILE STATUS IS WS-FS-IN.
           SELECT RPT-OUT   ASSIGN TO RPTOUT  FILE STATUS IS WS-FS-OUT.

       DATA DIVISION.
       FILE SECTION.
       FD  SCORE-IN  RECORDING MODE F.
           COPY SCOREREC.
       FD  RPT-OUT   RECORDING MODE F.
       01  RPT-LINE                  PIC X(133).

       WORKING-STORAGE SECTION.
       01  WS-FS-IN                  PIC XX.
       01  WS-FS-OUT                 PIC XX.
       01  WS-EOF                    PIC X     VALUE 'N'.
           88  END-OF-SCORES                   VALUE 'Y'.
       01  WS-LINES-ON-PAGE          PIC 9(3)  VALUE 99.
       01  WS-PAGE                   PIC 9(4)  VALUE 0.
       01  WS-RANK                   PIC 9(7)  VALUE 0.
       01  WS-ASOF-SAVE              PIC 9(8)  VALUE 0.
       01  WS-ASOF-X REDEFINES WS-ASOF-SAVE.
           05  WS-AS-YYYY            PIC 9(4).
           05  WS-AS-MM              PIC 99.
           05  WS-AS-DD              PIC 99.
       01  WS-TIER-TOTALS.
           05  WS-CNT-HIGH           PIC 9(7)  VALUE 0.
           05  WS-CNT-MEDIUM         PIC 9(7)  VALUE 0.
           05  WS-CNT-LOW            PIC 9(7)  VALUE 0.
           05  WS-EMI-HIGH           PIC 9(11)V99 VALUE 0.
           05  WS-EMI-MEDIUM         PIC 9(11)V99 VALUE 0.
           05  WS-EMI-LOW            PIC 9(11)V99 VALUE 0.
           05  WS-PROB-SUM           PIC 9(7)V9999 VALUE 0.
       01  WS-PCT                    PIC 9(3)V99.

       01  HDR-1.
           05  FILLER                PIC X     VALUE '1'.
           05  FILLER                PIC X(46) VALUE
               'EWS - EARLY WARNING CREDIT RISK SYSTEM'.
           05  FILLER                PIC X(30) VALUE
               'EARLY INTERVENTION LIST'.
           05  FILLER                PIC X(7)  VALUE 'AS-OF '.
           05  H1-YYYY               PIC 9(4).
           05  FILLER                PIC X     VALUE '-'.
           05  H1-MM                 PIC 99.
           05  FILLER                PIC X     VALUE '-'.
           05  H1-DD                 PIC 99.
           05  FILLER                PIC X(10) VALUE SPACES.
           05  FILLER                PIC X(5)  VALUE 'PAGE '.
           05  H1-PAGE               PIC ZZZ9.
           05  FILLER                PIC X(20) VALUE SPACES.
       01  HDR-2.
           05  FILLER                PIC X     VALUE '0'.
           05  FILLER                PIC X(46) VALUE
               '   RANK  CUSTOMER  RISK %  TIER    ACTN'.
           05  FILLER                PIC X(86) VALUE
               '   TOTAL EMI INR  TOP RISK FACTOR'.
       01  HDR-3.
           05  FILLER                PIC X     VALUE ' '.
           05  FILLER                PIC X(132) VALUE ALL '-'.
       01  DTL-LINE.
           05  FILLER                PIC X     VALUE ' '.
           05  DT-RANK               PIC Z(6)9.
           05  FILLER                PIC XX    VALUE SPACES.
           05  DT-CUST               PIC X(8).
           05  FILLER                PIC XX    VALUE SPACES.
           05  DT-PCT                PIC ZZ9.99.
           05  FILLER                PIC XX    VALUE SPACES.
           05  DT-TIER               PIC X(6).
           05  FILLER                PIC XX    VALUE SPACES.
           05  DT-ACTION             PIC X(4).
           05  FILLER                PIC XX    VALUE SPACES.
           05  DT-EMI                PIC Z,ZZZ,ZZ9.99.
           05  FILLER                PIC X(5)  VALUE SPACES.
           05  DT-FACTOR             PIC X(30).
           05  FILLER                PIC X(44) VALUE SPACES.
       01  TOT-LINE.
           05  FILLER                PIC X     VALUE '0'.
           05  TL-LABEL              PIC X(20).
           05  TL-COUNT              PIC Z,ZZZ,ZZ9.
           05  FILLER                PIC X(4)  VALUE SPACES.
           05  FILLER                PIC X(16) VALUE 'EMI AT RISK INR '.
           05  TL-EMI                PIC ZZZ,ZZZ,ZZZ,ZZ9.99.
           05  FILLER                PIC X(65) VALUE SPACES.

       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT SCORE-IN OUTPUT RPT-OUT
           IF WS-FS-IN NOT = '00' OR WS-FS-OUT NOT = '00'
               DISPLAY 'EWSRPT OPEN ERROR FS=' WS-FS-IN '/' WS-FS-OUT
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 2000-READ
           PERFORM UNTIL END-OF-SCORES
               PERFORM 3000-DETAIL
               PERFORM 2000-READ
           END-PERFORM
           PERFORM 8000-TOTALS
           CLOSE SCORE-IN RPT-OUT
           IF WS-RANK = 0
               MOVE 4 TO RETURN-CODE
           ELSE
               MOVE 0 TO RETURN-CODE
           END-IF
           GOBACK.

       2000-READ.
           READ SCORE-IN
               AT END SET END-OF-SCORES TO TRUE
           END-READ.

       3000-DETAIL.
           IF WS-RANK = 0
               MOVE SC-ASOF TO WS-ASOF-SAVE
           END-IF
           IF WS-LINES-ON-PAGE >= 55
               PERFORM 3100-HEADINGS
           END-IF
           ADD 1 TO WS-RANK
           MOVE WS-RANK        TO DT-RANK
           MOVE SC-CUST-ID     TO DT-CUST
           COMPUTE WS-PCT = SC-PROB * 100
           MOVE WS-PCT         TO DT-PCT
           MOVE SC-TIER        TO DT-TIER
           MOVE SC-ACTION      TO DT-ACTION
           MOVE SC-TOTAL-EMI   TO DT-EMI
           MOVE SC-TOP-FACTOR  TO DT-FACTOR
           WRITE RPT-LINE FROM DTL-LINE
           ADD 1 TO WS-LINES-ON-PAGE
           ADD SC-PROB TO WS-PROB-SUM
           EVALUATE TRUE
               WHEN SC-HIGH
                   ADD 1 TO WS-CNT-HIGH
                   ADD SC-TOTAL-EMI TO WS-EMI-HIGH
               WHEN SC-MEDIUM
                   ADD 1 TO WS-CNT-MEDIUM
                   ADD SC-TOTAL-EMI TO WS-EMI-MEDIUM
               WHEN OTHER
                   ADD 1 TO WS-CNT-LOW
                   ADD SC-TOTAL-EMI TO WS-EMI-LOW
           END-EVALUATE.

       3100-HEADINGS.
           ADD 1 TO WS-PAGE
           MOVE WS-AS-YYYY TO H1-YYYY
           MOVE WS-AS-MM   TO H1-MM
           MOVE WS-AS-DD   TO H1-DD
           MOVE WS-PAGE    TO H1-PAGE
           WRITE RPT-LINE FROM HDR-1
           WRITE RPT-LINE FROM HDR-2
           WRITE RPT-LINE FROM HDR-3
           MOVE 3 TO WS-LINES-ON-PAGE.

       8000-TOTALS.
           IF WS-LINES-ON-PAGE >= 50
               PERFORM 3100-HEADINGS
           END-IF
           WRITE RPT-LINE FROM HDR-3
           MOVE 'HIGH RISK      '  TO TL-LABEL
           MOVE WS-CNT-HIGH        TO TL-COUNT
           MOVE WS-EMI-HIGH        TO TL-EMI
           WRITE RPT-LINE FROM TOT-LINE
           MOVE 'MEDIUM RISK    '  TO TL-LABEL
           MOVE WS-CNT-MEDIUM      TO TL-COUNT
           MOVE WS-EMI-MEDIUM      TO TL-EMI
           WRITE RPT-LINE FROM TOT-LINE
           MOVE 'LOW RISK       '  TO TL-LABEL
           MOVE WS-CNT-LOW         TO TL-COUNT
           MOVE WS-EMI-LOW         TO TL-EMI
           WRITE RPT-LINE FROM TOT-LINE
           DISPLAY 'EWSRPT CUSTOMERS LISTED  ' WS-RANK
           DISPLAY 'EWSRPT HIGH RISK         ' WS-CNT-HIGH
           DISPLAY 'EWSRPT MEDIUM RISK       ' WS-CNT-MEDIUM
           DISPLAY 'EWSRPT LOW RISK          ' WS-CNT-LOW.
