.include "snes.inc"
.include "init.asm"


; This value depends on how long HandleIrq takes to get to the DMA
; See the big comment at HandleIrq
HIRQ_TIME = 201


; Joypad bit numbers
BUTTON_RIGHT    = 1 << 8
BUTTON_LEFT     = 1 << 9
BUTTON_DOWN     = 1 << 10
BUTTON_UP       = 1 << 11


; Order is significant!
.enum ImageFormat
        _2bit
        _4bit
        _8bit
        scan16
.endenum


.segment "ZEROPAGE"

wFrameCounter:  .res 2
wJoyState:      .res 2
wPrevJoyState:  .res 2
wJoyKeyDown:    .res 2
wImageId:       .res 2
pImageInfo:
pImageInfoL:    .res 1
pImageInfoH:    .res 1
bImageFormat:   .res 1

lpPalette:
lpPaletteL:     .res 1
lpPaletteH:     .res 1
lpPaletteB:     .res 1
wPaletteSize:
wPaletteSizeL:  .res 1
wPaletteSizeH:  .res 1


.segment "CODE"

; This is in the CODE segment so we can use near pointers
Images:
        .addr   Lenna2Info
        .addr   Lenna4Info
        .addr   LennaScan16Info
        .addr   Lenna8Info
NUM_IMAGES = (* - Images) / 2

Lenna2Info:
        .byte       ImageFormat::_2bit
        .faraddr    Lenna2Chr
        .word       Lenna2ChrSize
        .faraddr    Lenna2Pal
        .word       Lenna2PalSize

Lenna4Info:
        .byte       ImageFormat::_4bit
        .faraddr    Lenna4Chr
        .word       Lenna4ChrSize
        .faraddr    Lenna4Pal
        .word       Lenna4PalSize

Lenna8Info:
        .byte       ImageFormat::_8bit
        .faraddr    Lenna8Chr
        .word       Lenna8ChrSize
        .faraddr    Lenna8Pal
        .word       Lenna8PalSize

LennaScan16Info:
        .byte       ImageFormat::scan16
        .faraddr    LennaScan16Chr
        .word       LennaScan16ChrSize
        .faraddr    LennaScan16Pal
        .word       LennaScan16PalSize

; These must be in the same order as ImageFormat
; This is the BGMODE for each format
FmtVideoMode:
        .byte   0                           ; 2bit
        .byte   1                           ; 4bit
        .byte   4                           ; 8bit
        .byte   1                           ; scan16


.segment "LOHALF"

.macro BinData name, filename
.ident(name): .incbin filename
.ident(.concat(name, "Size")) = * - .ident(name)
.endmacro


NameData:
        .repeat 32*32, I
            .word I
        .endrepeat
NameDataSize = * - NameData

BinData "LennaScan16Chr", "images/scan16/lenna.chr"


.segment "BANK1"

BinData "LennaScan16Pal", "images/scan16/lenna.pal"
BinData "Lenna2Chr", "images/2bit/lenna.chr"
BinData "Lenna2Pal", "images/2bit/lenna.pal"
BinData "Lenna4Chr", "images/4bit/lenna.chr"
BinData "Lenna4Pal", "images/4bit/lenna.pal"

.segment "BANK2"

BinData "Lenna8Chr", "images/8bit/lenna.chr"
BinData "Lenna8Pal", "images/8bit/lenna.pal"


.segment "CODE"

Main:
        SetM8
        SetXY16

        ; Set Data Bank to Program Bank
        phk
        plb

        ; Enable FastROM
        lda     #$01
        sta     MEMSEL

        ; Init vars
        ldx     #0
        stx     wFrameCounter
        stx     wJoyState
        stx     wPrevJoyState
        stx     wJoyKeyDown
        stx     wImageId

        ; Force blank
        lda     #$80
        sta     INIDISP

        ; Set BG1 name table address
        stz     BG1SC                       ; $0000

        ; Set BG1 chr table address
        lda     #$01                        ; $1000
        sta     BG12NBA

        ; Show BG1 only
        lda     #$01
        sta     TM


        ; Prepare DMA channels
        ; Channel 1 will be used for VRAM transfers
        ; Channel 2 will be used for general CGRAM transfers
        ; Channel 7 will be used for CGRAM transfers during hblank for scan16 graphics
        lda     #$01                        ; 16-bit xfer to single register, incrementing
        sta     DMAP0
        stz     DMAP1                       ; 8-bit xfer to single register, incrementing
        lda     #<VMDATAL
        sta     BBAD0
        lda     #<CGDATA
        sta     BBAD1

        ; Prepare DMA for namedata transfer
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
        ; (we won't transfer right away; we'll do it during hblank)
        stz     DMAP7                       ; 8-bit xfer to single register, incrementing

        ; DMA source bank
        lda     #^LennaScan16Pal            ; not auto-updated during DMA
        sta     A1B7

        ; DMA destination register
        lda     #<CGDATA
        sta     BBAD7

        ; Set up IRQ (but don't enable it yet)
        ldx     #HIRQ_TIME
        stx     HTIMEL
        ldx     #0                          ; Don't run IRQ until vblank has ended
        stx     VTIMEL
        bra     @change_image

@main_loop:
        SetM16
        lda     wFrameCounter
@wait_for_vblank:
        wai
        cmp     wFrameCounter
        beq     @wait_for_vblank
        lda     wJoyKeyDown
        bit     #BUTTON_LEFT
        bne     @left
        bit     #BUTTON_RIGHT
        bne     @right
        bra     @main_loop
@left:
        dec     wImageId
        bpl     @change_image
        stz     wImageId                    ; overflowed to -1; restore to 0
        bra     @main_loop
@right:
        lda     wImageId
        cmp     #NUM_IMAGES - 1
        beq     @main_loop
        inc     a
        sta     wImageId
@change_image:
        ; Load new image
        SetM8
        stz     NMITIMEN                    ; interrupts disabled

        ; Get image info
        SetM16
        lda     wImageId
        asl                                 ; entries are 16-bit
        tax
        SetM8
        lda     Images,x
        sta     pImageInfoL
        inx
        lda     Images,x
        sta     pImageInfoH

        ; Force blank
        lda     #$80
        sta     INIDISP

        ; Get image format
        ldy     #0
        lda     (pImageInfo),y
        sta     bImageFormat
        iny

        ; Get BG mode
        tax
        lda     FmtVideoMode,x
        sta     BGMODE

        ; DMA 0 will be the chr data
        ; chr source address
        lda     (pImageInfo),y
        sta     A1T0L
        iny
        lda     (pImageInfo),y
        sta     A1T0H
        iny
        lda     (pImageInfo),y
        sta     A1B0
        iny

        ; chr size
        lda     (pImageInfo),y
        sta     DAS0L
        iny
        lda     (pImageInfo),y
        sta     DAS0H
        iny

        ; Set VRAM destination address
        ldx     #$1000
        stx     VMADDL

        ; palette source address
        lda     (pImageInfo),y
        sta     lpPaletteL
        iny
        lda     (pImageInfo),y
        sta     lpPaletteH
        iny
        lda     (pImageInfo),y
        sta     lpPaletteB
        iny

        ; palette size
        lda     (pImageInfo),y
        sta     wPaletteSizeL
        iny
        lda     (pImageInfo),y
        sta     wPaletteSizeH
        iny

        ; Set CGRAM destination address
        stz     CGADD

        ; How we handle the palette depends on the format
        lda     bImageFormat
        cmp     #ImageFormat::scan16
        beq     @scan16

        ; Not Scan16 format; load palette now
        ; DMA 1 will be the palette data
        ldx     lpPalette
        stx     A1T1L
        lda     lpPaletteB
        sta     A1B1
        ldx     wPaletteSize
        stx     DAS1L

        ; Execute DMA on channels 1 and 2
        lda     #$03
        sta     MDMAEN
        bra     @end

        ; Scan16 format; load palette later
@scan16:
        ; Execute DMA on channel 1
        lda     #$01
        sta     MDMAEN

@end:
        ; End force blank
        lda     #$0f
        sta     INIDISP

        ; Enable vblank
        lda     #$81                        ; NMI only and auto-read
        sta     NMITIMEN

        ; Done
        jmp     @main_loop

.a8


HandleVblank:
        ; Use a long jump to put us in $80xxxx instead of $00xxxx
        ; Thus running from FastROM
        jml     HandleVblankImpl

HandleVblankImpl:
        SetMXY16
        pha

        inc     wFrameCounter

        ; DMA source address
        ; @XXX@ -- should depend on image
        lda     #.loword(LennaScan16Pal)
        sta     A1T7L

        ; Reset CGRAM address for IRQ DMA
        SetM8
        stz     CGADD

        ; Get controller state
        ; First wait until bit 1 of HVBJOY is clear
@not_ready:
        lda     HVBJOY
        bit     #$01
        bne     @not_ready

        ; Now read the state
        SetM16
        lda     wJoyState
        sta     wPrevJoyState
        lda     JOY1L
        sta     wJoyState
        eor     wPrevJoyState
        and     wJoyState
        sta     wJoyKeyDown

        ; Enable HV-IRQ if image format is scan16
        lda     bImageFormat
        cmp     #ImageFormat::scan16
        bne     @end
        lda     #$31                        ; NMI off, IRQ on, auto-read
        sta     NMITIMEN

@end:
        pla
        rti
.a8


; This implements scan16 rendering
;
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
        sta     DAS7L

        ; Write to CGRAM address 0
        SetM8
        stz     CGADD

        ; Execute DMA
        lda     #$80
        sta     MDMAEN

        ; Disable V-IRQ and enable NMI
        ; (Thus we will fire IRQ every scanline until vblank disables it)
        ; NB: Make sure if NMI fires during IRQ, it happens *after* this line!
        ; Yet we want to do it after the DMA because, if we enable it too soon,
        ; it can cause the NMI to fire a second time during vblank.
        lda     #$91
        sta     NMITIMEN

        ; Clear IRQ line
        ; (the value received is irrelevant)
        lda     TIMEUP

        SetM16
        pla
        rti
.a8
