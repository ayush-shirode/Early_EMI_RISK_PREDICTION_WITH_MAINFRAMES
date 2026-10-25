      *----------------------------------------------------------------*
      * LOANREC  - LOAN MASTER RECORD              DSN: EWS.LOANMAST    *
      *            RECFM=FB  LRECL=80   KEY=LN-CUST-ID + LN-LOAN-ID     *
      *----------------------------------------------------------------*
       01  LOAN-REC.
           05  LN-LOAN-ID            PIC X(10).
           05  LN-CUST-ID            PIC X(8).
           05  LN-LOAN-TYPE          PIC X.
               88  LN-TYPE-VALID     VALUE 'H' 'C' 'P' 'E'.
           05  LN-PRINCIPAL          PIC 9(9)V99.
           05  LN-INT-RATE           PIC 9(2)V99.
           05  LN-TENURE             PIC 9(3).
           05  LN-START-DATE         PIC 9(8).
           05  LN-EMI-AMT            PIC 9(7)V99.
           05  LN-DUE-DAY            PIC 9(2).
           05  LN-OUTSTANDING        PIC 9(9)V99.
           05  LN-STATUS             PIC X.
               88  LN-STATUS-VALID   VALUE 'A' 'C' 'D'.
           05  FILLER                PIC X(12).
