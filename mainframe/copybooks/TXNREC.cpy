      *----------------------------------------------------------------*
      * TXNREC   - MONTHLY ACCOUNT SUMMARY         DSN: EWS.TXNSUMM     *
      *            RECFM=FB  LRECL=80   KEY=TX-CUST-ID + TX-YYYYMM      *
      *----------------------------------------------------------------*
       01  TXN-REC.
           05  TX-CUST-ID            PIC X(8).
           05  TX-YYYYMM             PIC 9(6).
           05  TX-CREDITS            PIC 9(7)V99.
           05  TX-DEBITS             PIC 9(7)V99.
           05  TX-SALARY             PIC 9(7)V99.
           05  TX-MIN-BAL            PIC 9(7)V99.
           05  TX-AVG-BAL            PIC 9(7)V99.
           05  TX-BOUNCES            PIC 9(2).
           05  TX-CC-UTIL            PIC 9(3)V99.
           05  FILLER                PIC X(14).
