      *----------------------------------------------------------------*
      * SCOREREC - MODEL SCORE WRITTEN BACK FROM PYTHON                 *
      *            DSN: EWS.SCORES     RECFM=FB  LRECL=80               *
      *----------------------------------------------------------------*
       01  SCORE-REC.
           05  SC-CUST-ID            PIC X(8).
           05  SC-ASOF               PIC 9(8).
           05  SC-PROB               PIC 9V9999.
           05  SC-TIER               PIC X(6).
               88  SC-HIGH           VALUE 'HIGH  '.
               88  SC-MEDIUM         VALUE 'MEDIUM'.
               88  SC-LOW            VALUE 'LOW   '.
           05  SC-ACTION             PIC X(4).
           05  SC-TOP-FACTOR         PIC X(30).
           05  SC-TOTAL-EMI          PIC 9(7)V99.
           05  FILLER                PIC X(10).
