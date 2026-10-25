      *----------------------------------------------------------------*
      * CTLREC   - CONTROL TOTAL RECORD  (KEY=VALUE TEXT)               *
      *            DSN: EWS.CTLTOT     RECFM=FB  LRECL=80               *
      *----------------------------------------------------------------*
       01  CTL-REC.
           05  CT-PROGRAM            PIC X(8).
           05  FILLER                PIC X     VALUE SPACE.
           05  CT-KEY                PIC X(20).
           05  FILLER                PIC X     VALUE '='.
           05  CT-VALUE              PIC 9(9).
           05  FILLER                PIC X(41) VALUE SPACES.
