#!/usr/bin/env python
# Syntax: conv16scanline.py in.png
# Written for Python 3.4 with the pillow and scikit-image libraries
import os.path
import struct
import sys

import numpy as np
import scipy.cluster.vq
import skimage.color
import skimage.exposure
import skimage.io


GAMMA_IN = 2.2
GAMMA_OUT = 2.2


# If True, first generate a 16-color palette for the entire image.
# This is used as the estimate passed to kmeans on each line.
# This speeds up processing but may result in fewer total colors.
USE_ESTIMATED_PALETTE = True

# How many surrounding lines to look at when generating palette.
# For example, when generating a palette for line 10, when this is 3, it will
# generate a palette using lines [7..13].
#
# Set to 0 to not look at surrounding lines.
SURROUNDING_LINES = 0

DITHERING = False

FLOYD_STEINBERG = np.array([
    [0,     0,      7/16],
    [3/16,  5/16,   1/16],
])

JARVICE_JUDICE_NINKE = np.array([
    [0,     0,      0,      7/48,   5/48],
    [3/48,  5/48,   7/48,   5/48,   3/48],
    [1/48,  3/48,   5/48,   3/48,   1/48],
])

DITHERING_FILTER = JARVICE_JUDICE_NINKE

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
    height, width, num_channels = img.shape
    if USE_ESTIMATED_PALETTE:
        estimated_palette = genPalette(img.reshape((width*height, num_channels)))
    else:
        estimated_palette = None
    for row_num in range(height//8):
        scanline_rows = []
        for i in range(8):
            scanline_num = row_num*8 + i
            paletted_line, palette = processLine(img, scanline_num, estimated_palette)
            writePalette(palette, pal_file)
            scanline_rows.append(paletted_line)
        writeChrRow(scanline_rows, chr_file)


# NB: modifies img in-place to facilitate dithering
def processLine(img, line_num, estimated_palette):
    height, width, num_channels = img.shape
    line = img[line_num]
    pal_first_line_num = max(0, line_num-SURROUNDING_LINES)
    pal_end_line_num = min(height, line_num + SURROUNDING_LINES + 1)
    pal_num_rows = pal_end_line_num - pal_first_line_num
    pal_lines = img[pal_first_line_num:pal_end_line_num].reshape((width*pal_num_rows, num_channels))
    palette = genPalette(pal_lines, estimated_palette)
    if DITHERING:
        reversed = BOUSTROPHEDON and line_num % 2 != 0
        if reversed:
            filter = DITHERING_FILTER[:,::-1]
            the_range = range(len(line)-1, -1, -1)
        else:
            filter = DITHERING_FILTER
            the_range = range(0, len(line))

        # Reshape filter to number of channels
        # If there are 3 channels, [[a,b,c]] becomes [[[a,a,a],[b,b,b],[c,c,c]]]
        filter_height, filter_width = filter.shape
        filter = np.repeat(filter, num_channels)
        filter = filter.reshape((filter_height, filter_width, num_channels))

        paletted_line = []
        for col in the_range:
            color_idx = scipy.cluster.vq.vq([line[col]], palette)[0][0]
            paletted_line.append(color_idx)
            error = line[col] - palette[color_idx]
            applyDeltas(img, filter*error, line_num, col)
        if reversed:
            paletted_line.reverse()
    else:
        paletted_line, _ = scipy.cluster.vq.vq(line, palette)
    return paletted_line, palette


# Use k-means to generate a 16-color palette
# pixels should be a numpy array
def genPalette(pixels, estimated_palette=None):
    # Make sure all values are 0..1
    # @XXX@ -- not necessarily appropriate in non-RGB colorspaces
    pixels = pixels.clip(0.0, 1.0)
    centroids, _ = scipy.cluster.vq.kmeans(
        pixels,
        estimated_palette if estimated_palette is not None else 16,
        check_finite=False
    )
    # Sometimes fewer than 16 colors are in the list and we have to resize to compensate
    return np.resize(centroids, (16, centroids.shape[1]))


def applyDeltas(img, diffused_error, row, col):
    img_height, img_width, _ = img.shape
    err_height, err_width, _ = diffused_error.shape
    left_col = col - err_width//2
    end_col = col + err_width//2 + 1
    end_row = row + err_height

    # All these conditions just crop diffused_error as needed when
    # adding it to the edge of the image
    if left_col < 0:
        diffused_error = diffused_error[:,-left_col:]
        left_col = 0
    if end_col > img_width:
        diffused_error = diffused_error[:,:img_width - end_col]
        end_col = img_width
    if end_row > img_height:
        diffused_error = diffused_error[:img_height - end_row]
        end_row = img_height
    img_section = img[row:end_row,left_col:end_col]

    # We're modifying img in-place
    img_section += diffused_error


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
