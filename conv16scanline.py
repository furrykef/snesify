#!/usr/bin/env python
# Written for Python 3.4 with the pillow and scikit-image libraries
# @TODO@ -- range check numeric command-line arguments
# @TODO@ -- consider click instead of argparse
import argparse
import cProfile as profile
import os.path
import platform
import struct
import sys
import time

import numpy as np
import scipy.cluster.vq
import skimage.color
import skimage.exposure
import skimage.io


FLOYD_STEINBERG = np.array([
    [0, 0, 7],
    [3, 5, 1],
]) / 16

JARVIS_JUDICE_NINKE = np.array([
    [0, 0, 0, 7, 5],
    [3, 5, 7, 5, 3],
    [1, 3, 5, 3, 1],
]) / 48

STUCKI = np.array([
    [0, 0, 0, 8, 4],
    [2, 4, 8, 4, 2],
    [1, 2, 4, 2, 1],
]) / 42

ATKINSON = np.array([
    [0, 0, 0, 1, 1],
    [0, 1, 1, 1, 0],
    [0, 0, 1, 0, 0],
]) / 8

DITHER_FILTERS = {
    'fs': FLOYD_STEINBERG,
    'f-s': FLOYD_STEINBERG,
    'floyd-steinberg': FLOYD_STEINBERG,
    'jjn': JARVIS_JUDICE_NINKE,
    'j-j-n': JARVIS_JUDICE_NINKE,
    'jarvis-judice-ninke': JARVIS_JUDICE_NINKE,
    'stucki': STUCKI,
    'atkinson': ATKINSON,
}


# Use Lab instead of RGB
USE_LAB = False


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    options = parseArgs(argv)
    for filename in options.files:
        if options.verbose:
            print(filename, end=' ', flush=True)
            start_time = time.perf_counter()
        runner = profile.runctx if options.profile else exec
        runner("processFile(filename, options)", globals(), locals())
        if options.verbose:
            print("({:.2f} secs)".format(time.perf_counter() - start_time))


def processFile(filename, options):
    try:
        img = skimage.io.imread(filename)[:,:,:3]   # The slice will remove any alpha channel
    except (OSError, IOError) as e:
        print("{}: {}".format(filename, e), file=sys.stderr)
        return 1
    if USE_LAB:
        img = skimage.color.rgb2lab(img)
    else:
        img = skimage.img_as_float(img)
        img = skimage.exposure.adjust_gamma(img, gamma=options.gamma_in)
    chr_filename = changeExtension(filename, '.chr')
    pal_filename = changeExtension(filename, '.pal')
    with open(chr_filename, 'wb') as chr_file:
        with open(pal_filename, 'wb') as pal_file:
            processImage(img, chr_file, pal_file, options)


def parseArgs(argv):
    parser = argparse.ArgumentParser(argv)
    parser.add_argument('files', nargs='+')
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('--gamma-in', type=float, default=1.0)
    parser.add_argument('--gamma-out', type=float, default=1.0)
    parser.add_argument('--seed', action='store_true')
    parser.add_argument('--dither', choices=DITHER_FILTERS.keys())
    parser.add_argument('--no-boustrophedon', action='store_true')
    parser.add_argument('--window', type=int, default=0)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    # @TODO@ -- some other non-Unix OSes may need this behavior
    # @TODO@ -- more elegant way to do this?
    if platform.system() == 'Windows':
        import glob
        filenames = []
        for filename in args.files:
            if '*' in filename or '?' in filename or '[' in filename:
                filenames += glob.glob(filename)
            else:
                filenames.append(filename)
        args.files = filenames
    args.diffusion_filter = DITHER_FILTERS[args.dither] if args.dither else None
    args.boustrophedon = not args.no_boustrophedon
    return args


def changeExtension(filename, new_extension):
    return os.path.splitext(filename)[0] + new_extension


# img should be a 2D numpy array of pixels
# (really a 3D array of color components)
def processImage(img, chr_file, pal_file, options):
    height, width, num_channels = img.shape
    if options.seed:
        estimated_palette = genPalette(img.reshape((width*height, num_channels)))
    else:
        estimated_palette = None
    diffusion_filter = extendFilter(options.diffusion_filter, num_channels)
    for row_num in range(height//8):
        scanline_rows = []
        for i in range(8):
            scanline_num = row_num*8 + i
            paletted_line, palette = processLine(img,
                                                 scanline_num,
                                                 estimated_palette,
                                                 diffusion_filter,
                                                 options)
            writePalette(palette, pal_file, options)
            scanline_rows.append(paletted_line)
        writeChrRow(scanline_rows, chr_file)


# NB: modifies img in-place to facilitate dithering
def processLine(img, line_num, estimated_palette, diffusion_filter, options):
    height, width, num_channels = img.shape
    line = img[line_num]
    pal_window = getWindow(img, line_num, options)
    palette = genPalette(pal_window, estimated_palette)
    if diffusion_filter is not None:
        reversed = options.boustrophedon and line_num % 2 != 0
        if reversed:
            diffusion_filter = diffusion_filter[:,::-1]
            the_range = range(len(line)-1, -1, -1)
        else:
            the_range = range(0, len(line))
        paletted_line = []
        for col in the_range:
            color_idx = scipy.cluster.vq.vq([line[col]], palette, check_finite=False)[0][0]
            paletted_line.append(color_idx)
            error = line[col] - palette[color_idx]
            addDiffusedError(img, diffusion_filter*error, line_num, col)
        if reversed:
            paletted_line.reverse()
    else:
        paletted_line, _ = scipy.cluster.vq.vq(line, palette, check_finite=False)
    return paletted_line, palette

def getWindow(img, line_num, options):
    height, width, num_channels = img.shape
    pal_first_line_num = max(0, line_num - options.window)
    pal_end_line_num = min(height, line_num + options.window + 1)
    pal_num_rows = pal_end_line_num - pal_first_line_num
    return img[pal_first_line_num:pal_end_line_num].reshape((width*pal_num_rows, num_channels))

# Reshape filter to number of channels
# If there are 3 channels, [[a,b,c]] becomes [[[a,a,a],[b,b,b],[c,c,c]]]
def extendFilter(filter, num_channels):
    if filter is None:
        return None
    filter_height, filter_width = filter.shape
    filter = np.repeat(filter, num_channels)
    return filter.reshape((filter_height, filter_width, num_channels))


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


def addDiffusedError(img, diffused_error, row, col):
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


def writePalette(palette, pal_file, options):
    if USE_LAB:
        palette = skimage.color.lab2rgb([palette])[0]
    else:
        palette = skimage.exposure.adjust_gamma(palette, gamma=1.0/options.gamma_out)
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
    sys.exit(main())
