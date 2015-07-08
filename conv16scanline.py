#!/usr/bin/env python
# Syntax: conv16scanline.py in.png
# Written for Python 3.4 with the pillow library
import struct
import sys

import PIL.Image


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    infilename = argv[0]
    img = PIL.Image.open(infilename)
    chr_filename = infilename + '.chr'
    pal_filename = infilename + '.pal'
    with open(chr_filename, 'wb') as fchr:
        with open(pal_filename, 'wb') as fpal:
            processImage(img, fchr, fpal)


def processImage(img, fchr, fpal):
    width, height = img.size
    for row_num in range(height//8):
        scanline_rows = []
        for i in range(8):
            scanline_num = row_num*8 + i
            pixrow = img.crop((0, scanline_num, width, scanline_num+1))
            pixrow = pixrow.convert("RGB")  # This extra conversion forces the generated palette to be an RGB palette
            pixrow = pixrow.convert("P",
                        dither=PIL.Image.NONE,
                        palette=PIL.Image.ADAPTIVE,
                        colors=16
                     )
            writePalette(pixrow.palette, fpal)
            scanline_rows.append(pixrow.tobytes())
        writeChrRow(scanline_rows, fchr)


def writePalette(palette, fpal):
    palette = palette.getdata()[1][:16*3]   # 16 colors, 3 bytes per color
    # Process the sequence in threes
    for (r, g, b) in zip(palette[::3], palette[1::3], palette[2::3]):
        # Convert to 0bbbbbgggggrrrrr
        snes_color = (b>>3<<10) | (g>>3<<5) | (r>>3)
        fpal.write(struct.pack("<H", snes_color))


def writeChrRow(scanline_rows, fchr):
    width = len(scanline_rows[0])
    for chr_num in range(width//8):
        chr_x = chr_num*8
        for shift in (0, 2):
            shift2 = shift + 1              # shift for bitplane 2
            bitplane_mask = 1 << shift
            bitplane2_mask = 1 << shift2
            for y in range(8):
                word = 0
                for x in range(8):
                    pixel = scanline_rows[y][chr_x+x]
                    bitnum = 7 - x
                    word |= (pixel & bitplane_mask) >> shift << bitnum
                    word |= (pixel & bitplane2_mask) >> shift2 << (bitnum + 8)
                fchr.write(struct.pack("<H", word))


if __name__ == '__main__':
    main()
