#!/usr/bin/env python
# Syntax: conv16scanline.py in.png
# Written for Python 3.4 with the pillow and scikit-image libraries
import os.path
import struct
import sys

import numpy
import skimage
import skimage.color
import skimage.exposure
import skimage.io


GAMMA_IN = 2.2
GAMMA_OUT = 2.2


NO_DITHERING = []

FLOYD_STEINBERG = [
    [0,     0,      7/16],
    [3/16,  5/16,   1/16],
]

JARVICE_JUDICE_NINKE = [
    [0,     0,      0,      7/48,   5/48],
    [3/48,  5/48,   7/48,   5/48,   3/48],
    [1/48,  3/48,   5/48,   3/48,   1/48],
]

DITHERING = JARVICE_JUDICE_NINKE

# If true, dither lines scanning them alternating between left-to-right and
# right-to-left. Also called "serpentine" scanning.
BOUSTROPHEDON = True

# Use Lab instead of RGB
USE_LAB = False


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    infilename = argv[0]
    img = skimage.io.imread(infilename)[:,:,:3] # The slice will remove any alpha channel
    if USE_LAB:
        img = skimage.color.rgb2lab(img)
    else:
        img = skimage.img_as_float(img)
        img = skimage.exposure.adjust_gamma(img, gamma=GAMMA_IN)
    chr_filename = changeExtension(infilename, '.chr')
    pal_filename = changeExtension(infilename, '.pal')
    with open(chr_filename, 'wb') as chr_file:
        with open(pal_filename, 'wb') as pal_file:
            processImage(img, chr_file, pal_file)


def changeExtension(filename, new_extension):
    return os.path.splitext(filename)[0] + new_extension


# img should be a 2D numpy array of pixels
# (really a 3D array of color components)
def processImage(img, chr_file, pal_file):
    height, width, _ = img.shape
    for row_num in range(height//8):
        scanline_rows = []
        for i in range(8):
            scanline_num = row_num*8 + i
            paletted_line, palette = processLine(img, scanline_num)
            writePalette(palette, pal_file)
            scanline_rows.append(paletted_line)
        writeChrRow(scanline_rows, chr_file)


# NB: modifies img in-place to facilitate dithering
# @TODO@ -- dithering
def processLine(img, line_num):
    line = img[line_num]
    pixels = line.copy()
    palette = genPalette(pixels)
    paletted_line = [findClosestColor(x, palette) for x in line]
    return paletted_line, palette


# Use median cut to generate a 16-color palette
# pixels should be a numpy array
def genPalette(pixels):
    # 4 iterations will result in 16 colors
    return numpy.array(getMedianCut(pixels, 4))

# Return value is list, not array!
def getMedianCut(pixels, depth):
    if depth == 0:
        return [numpy.mean(pixels, axis=0)]
    channel_num = findChannelWithGreatestRange(pixels)
    sorted_pixels = numpy.array(sorted(pixels, key=lambda pixel: pixel[channel_num]))
    median = len(sorted_pixels)//2
    lesser = sorted_pixels[:median]
    greater = sorted_pixels[median:]
    return getMedianCut(lesser, depth - 1) + getMedianCut(greater, depth - 1)

def findChannelWithGreatestRange(pixels):
    _, num_channels = pixels.shape
    channel_ranges = [max(pixels[:,i]) - min(pixels[:,i]) for i in range(num_channels)]
    return channel_ranges.index(max(channel_ranges))


# Thanks to http://stackoverflow.com/questions/1401712/how-can-the-euclidean-distance-be-calculated-with-numpy
def findClosestColor(color, palette):
    distances = [numpy.linalg.norm(pal_color - color) for pal_color in palette]
    return distances.index(min(distances))


def writePalette(palette, pal_file):
    if USE_LAB:
        palette = skimage.color.lab2rgb([palette])[0]
    else:
        palette = skimage.exposure.adjust_gamma(palette, gamma=1.0/GAMMA_OUT)
    palette = scaleColors(palette, 31)
    for (r, g, b) in palette:
        # Convert to 0bbbbbgggggrrrrr
        snes_color = (b<<10) | (g<<5) | r
        pal_file.write(struct.pack("<H", snes_color))

def scaleColors(palette, max):
    # We add 0.5 to have proper rounding when truncating to int
    return [[int(x*max + 0.5) for x in color] for color in palette]


def writeChrRow(scanline_rows, chr_file):
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
                chr_file.write(struct.pack("<H", word))


if __name__ == '__main__':
    main()
