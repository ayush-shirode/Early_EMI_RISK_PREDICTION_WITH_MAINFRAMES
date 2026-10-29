      *----------------------------------------------------------------*
      * SCOREVS  - LATEST SCORE OF EVERY CUSTOMER                       *
      *            DSN: EWS.SCORKSDS   VSAM KSDS  RECORDSIZE(100 100)   *
      *            KEY: SV-CUST-ID, KEYS(8 0)                           *
      *            UPDATED IN PLACE BY EWSSUPD ON EVERY SCORING RUN;    *
      *            THE SCORE BEFORE THE RUN IS KEPT IN SV-PREV-*.       *
      *----------------------------------------------------------------*
       01  SCOREVS-REC.
           05  SV-CUST-ID            PIC X(8).
           05  SV-ASOF               PIC 9(8).
           05  SV-PROB               PIC 9V9999.
           05  SV-TIER               PIC X(6).
           05  SV-ACTION             PIC X(4).
           05  SV-TOP-FACTOR         PIC X(30).
           05  SV-TOTAL-EMI          PIC 9(7)V99.
           05  SV-PREV-ASOF          PIC 9(8).
           05  SV-PREV-PROB          PIC 9V9999.
           05  SV-PREV-TIER          PIC X(6).
           05  SV-TIMES-SCORED       PIC 9(4).
           05  FILLER                PIC X(7).
