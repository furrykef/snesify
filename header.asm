.segment "HEADER"

        ; Name (21 bytes, padded with spaces)
        .byte   "16/SCANLINE GFX DEMO "

        ; ROM type
        .byte   $31                         ; HiROM, fast

        ; Cartridge type
        .byte   $00                         ; ROM only

        ; Size of ROM
        .byte   $06                         ; 64 KB

        ; Size of RAM
        .byte   $00                         ; none

        ; Country code
        .byte   $01                         ; North America, NTSC

        ; Licensee code
        .byte   $00

        ; ROM version
        .byte   $00

        ; checksum complement and checksum
        .word   0
        .word   0


.segment "VECTORS"
        ; 65816 mode
        ; ----------
        ; COP
        .addr   DummyInterruptHandler

        ; BRK
        .addr   DummyInterruptHandler

        ; ABORT
        .addr   DummyInterruptHandler

        ; NMI (vblank)
        .addr   HandleVblank

        ; unused
        .res    2

        ; IRQ
        .addr   HandleIrq

        ; Unused
        .res    4

        ; 6502 mode
        ; ---------
        ; COP
        .addr   DummyInterruptHandler

        ; unused
        .res    2

        ; ABORT
        .addr   DummyInterruptHandler

        ; NMI
        .addr   DummyInterruptHandler

        ; RESET
        .addr   Init

        ; IRQ/BRK
        .addr   DummyInterruptHandler
