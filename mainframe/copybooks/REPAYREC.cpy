      *----------------------------------------------------------------*
      * REPAYREC - EMI INSTALLMENT HISTORY         DSN: EWS.REPAYHST    *
      *            RECFM=FB  LRECL=80                                   *
      *            KEY=RP-CUST-ID + RP-LOAN-ID + RP-DUE-DATE            *
      *  RP-STATUS  P=PAID ON TIME  L=LATE  R=PARTIAL                   *
      *             B=BOUNCED (NACH/CHEQUE) THEN PAID  M=MISSED         *
      *----------------------------------------------------------------*
       01  REPAY-REC.
           05  RP-LOAN-ID            PIC X(10).
           05  RP-CUST-ID            PIC X(8).
           05  RP-INST-NO            PIC 9(3).
           05  RP-DUE-DATE           PIC 9(8).
           05  RP-PAID-DATE          PIC 9(8).
           05  RP-DUE-AMT            PIC 9(7)V99.
           05  RP-PAID-AMT           PIC 9(7)V99.
           05  RP-DPD                PIC 9(3).
           05  RP-STATUS             PIC X.
               88  RP-ON-TIME        VALUE 'P'.
               88  RP-LATE           VALUE 'L'.
               88  RP-PARTIAL        VALUE 'R'.
               88  RP-BOUNCED        VALUE 'B'.
               88  RP-MISSED         VALUE 'M'.
           05  FILLER                PIC X(21).
