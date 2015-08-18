.include "snes.inc"
.include "init.asm"


; This value depends on how long HandleIrq takes to get to the DMA
; See the big comment at HandleIrq
HIRQ_TIME = 201


.segment "ZEROPAGE"


.segment "LOHALF"

ChrData:
        .incbin "images/scan16/lenna.chr"
ChrDataSize = * - ChrData


NameData:
        .repeat 32*32, I
            .word I
        .endrepeat
NameDataSize = * - NameData

; Palette will appear in another bank since we don't have enough room here


.segment "CODE"

PaletteData:
        .incbin "images/scan16/lenna.pal"


Main:
        SetM8
        SetXY16

        ; Set Data Bank to Program Bank
        phk
        plb

        ; Enable FastROM
        lda     #$01
        sta     MEMSEL

        ; Force blank
        lda     #$80
        sta     INIDISP

        ; Set video mode 1
        lda     #$01
        sta     BGMODE

        ; Set BG1 name table address
        stz     BG1SC                       ; $0000

        ; Set BG1 chr table address
        lda     #$01                        ; $1000
        sta     BG12NBA

        ; Show BG1 only
        lda     #$01
        sta     TM


        ; Prepare DMA for chr data transfer
        ; *********************************
        lda     #$01                        ; 16-bit xfer to single register, incrementing
        sta     DMAP0

        ; DMA source address
        ldx     #.loword(ChrData)
        stx     A1T0L
        lda     #^ChrData
        sta     A1B0

        ; DMA destination register
        lda     #<VMDATAL
        sta     BBAD0

        ; DMA size
        ldx     #ChrDataSize
        stx     DAS0L

        ; Set VRAM destination address
        ldx     #$1000
        stx     VMADDL

        ; Execute DMA
        lda     #$01
        sta     MDMAEN


        ; Prepare DMA for tilemap transfer
        ; ********************************
        ; (here we're reusing a couple regs from the chr data transfer)
        ; DMA source address
        ldx     #.loword(NameData)
        stx     A1T0L
        lda     #^NameData
        sta     A1B0

        ; DMA size
        ldx     #NameDataSize
        stx     DAS0L

        ; Set VRAM destination address to $0000
        stz     VMADDL
        stz     VMADDH

        ; Execute DMA
        lda     #$01
        sta     MDMAEN


        ; Prepare DMA for palette transfer
        ; ********************************
        ; (we won't transfer right away; we'll do it during vblank and hblank)
        stz     DMAP0                       ; 8-bit xfer to single register, incrementing

        ; DMA source bank
        lda     #^PaletteData               ; not auto-updated during DMA
        sta     A1B0

        ; DMA destination register
        lda     #<CGDATA
        sta     BBAD0

        ; End force blank
        lda     #$0f
        sta     INIDISP

        ; Set up IRQ
        ldx     #HIRQ_TIME
        stx     HTIMEL
        ldx     #0                          ; Don't run IRQ until vblank has ended
        stx     VTIMEL
        lda     #$80                        ; NMI only for now
        sta     NMITIMEN

forever:
        wai
        bra     forever


HandleVblank:
        ; Use a long jump to put us in $80xxxx instead of $00xxxx
        ; Thus running from FastROM
        jml     HandleVblankImpl

HandleVblankImpl:
        SetM16
        pha

        ; DMA source address
        lda     #.loword(PaletteData)
        sta     A1T0L

        ; Reset CGRAM address for IRQ DMA
        SetM8
        stz     CGADD

        ; Enable HV-IRQ
        lda     #$30
        sta     NMITIMEN

        SetM16
        pla
        rti
.a8


; Use BSNES debugger to time this function up to the STA MDMAEN instruction.
; The H register in BSNES is the number of master cycles taken for the current
; scanline. hblank begins at H=1096 (according to CPU::mmio_r4212 in higan
; source), so you want the DMA to begin then. I *think* the DMA will begin at
; 24 master cycles after the STA MDAEN instruction completes (16 cycles DMA
; overhead + 8 cycles for 1 DMA channel). So after executing STA MDMAEN, BSNES
; should say H=1072 (it's OK to overshoot by a few cycles, but don't go under).
; H will not be the same on every scanline, so be sure to check the value for
; several iterations.
;
; To control when this function is called, tweak HIRQ_TIME at the top of this
; program. If the STA MDMAEN instruction finishes too early, increase the value;
; if it finishes too late, decrease it. You'll probably have to tweak it a few
; times before it's right, and, again, be sure to test several iterations, not
; just one.
;
; NOTE: Do not use BSNES Plus 0.73+1 to calibrate the timing; its cycle counts
; are wrong when you step through a program in the debugger. BSNES 0.65 gets it
; right, as should later versions of BSNES Plus.
;
; Note that if you run this IRQ on the screen's last scanline, the vblank
; NMI may occur before the IRQ handler finishes (although the NMI will probably
; occur after the IRQ's DMA completes).
HandleIrq:
        ; Use a long jump to put us in $80xxxx instead of $00xxxx
        ; Thus running from FastROM
        jml     HandleIrqImpl

HandleIrqImpl:
        SetM16
        pha

        ; DMA size
        lda     #32                         ; 16-color palettes are 32 bytes
        sta     DAS0L

        ; Write to CGRAM address 0
        SetM8
        stz     CGADD

        ; Execute DMA
        lda     #$01
        sta     MDMAEN

        ; Disable V-IRQ and enable NMI
        ; (Thus we will fire IRQ every scanline until vblank disables it)
        ; NB: Make sure if NMI fires during IRQ, it happens *after* this line!
        ; Yet we want to do it after the DMA because, if we enable it too soon,
        ; it can cause the NMI to fire a second time during vblank.
        lda     #$90
        sta     NMITIMEN

        ; Clear IRQ line
        ; (the value received is irrelevant)
        lda     TIMEUP

        SetM16
        pla
        rti
.a8
