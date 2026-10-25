      *----------------------------------------------------------------*
      * FEATREC  - ML FEATURE RECORD (ONE PER ELIGIBLE CUSTOMER)        *
      *            DSN: EWS.FEATURES   RECFM=FB  LRECL=200              *
      *            NUMERIC-EDITED FIELDS SO DFSORT CAN TURN THE RECORD  *
      *            INTO CSV WITHOUT ANY NUMERIC CONVERSION.             *
      *            ALL WINDOWS END AT THE AS-OF DATE (NO LEAKAGE).      *
      *----------------------------------------------------------------*
       01  FEAT-REC.
           05  FT-CUST-ID            PIC X(8).
           05  FT-ASOF               PIC 9(8).
           05  FT-EMP-TYPE           PIC X.
           05  FT-AGE                PIC ZZ9.
           05  FT-INCOME             PIC Z(6)9.99.
           05  FT-CREDIT-SCORE       PIC ZZ9.
           05  FT-ACTIVE-LOANS       PIC Z9.
           05  FT-TOTAL-EMI          PIC Z(6)9.99.
           05  FT-EMI-TO-INCOME      PIC Z9.9999.
           05  FT-TENURE-REM         PIC ZZ9.
           05  FT-INST-DUE-12M       PIC ZZ9.
           05  FT-LATE-3M            PIC Z9.
           05  FT-LATE-12M           PIC Z9.
           05  FT-MISSED-12M         PIC Z9.
           05  FT-PARTIAL-12M        PIC Z9.
           05  FT-EMI-BOUNCE-6M      PIC Z9.
           05  FT-TXN-BOUNCE-6M      PIC Z9.
           05  FT-MAX-DPD-12M        PIC ZZ9.
           05  FT-AVG-DPD-6M         PIC ZZ9.99.
           05  FT-DPD-TREND          PIC -ZZ9.99.
           05  FT-AVG-BAL-3M         PIC Z(6)9.99.
           05  FT-MIN-BAL-3M         PIC Z(6)9.99.
           05  FT-BAL-TREND-PCT      PIC -ZZZ9.99.
           05  FT-SAVINGS-TO-EMI     PIC ZZZ9.99.
           05  FT-SALARY-MISS-6M     PIC 9.
           05  FT-DEBIT-CREDIT-3M    PIC ZZ9.9999.
           05  FT-SPEND-TREND-PCT    PIC -ZZZ9.99.
           05  FT-CC-UTIL-3M         PIC ZZ9.99.
           05  FT-LABEL              PIC X.
           05  FILLER                PIC X(55).
