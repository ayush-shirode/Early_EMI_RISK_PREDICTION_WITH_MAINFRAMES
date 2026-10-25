      *----------------------------------------------------------------*
      * REJREC   - REJECT / EXCEPTION RECORD                            *
      *            DSN: EWS.REJECTS, EWS.EXCEPT  RECFM=FB  LRECL=120    *
      *----------------------------------------------------------------*
       01  REJ-REC.
           05  RJ-SOURCE             PIC X(8).
           05  RJ-KEY                PIC X(10).
           05  RJ-REASON-CODE        PIC X(4).
           05  RJ-REASON-TEXT        PIC X(40).
           05  RJ-DATA               PIC X(58).
