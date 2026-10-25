      *----------------------------------------------------------------*
      * CUSTREC  - CUSTOMER MASTER RECORD          DSN: EWS.CUSTMAST    *
      *            RECFM=FB  LRECL=100  KEY=CU-CUST-ID                  *
      *----------------------------------------------------------------*
       01  CUST-REC.
           05  CU-CUST-ID            PIC X(8).
           05  CU-CUST-NAME          PIC X(30).
           05  CU-CITY               PIC X(20).
           05  CU-EMP-TYPE           PIC X.
               88  CU-EMP-VALID      VALUE 'S' 'E' 'B'.
           05  CU-AGE                PIC 9(3).
           05  CU-MONTHLY-INCOME     PIC 9(7)V99.
           05  CU-CREDIT-SCORE       PIC 9(3).
           05  CU-OPEN-DATE          PIC 9(8).
           05  CU-STATUS             PIC X.
               88  CU-STATUS-VALID   VALUE 'A' 'C'.
               88  CU-ACTIVE         VALUE 'A'.
           05  FILLER                PIC X(17).
