#!/usr/bin/env python
# Written for Python 3.4
#
# Dependencies
#   scikit-image
#   scikit-learn
#   ...and their dependencies
#
# @TODO@:
#   * implement shared palette
#   * range check numeric command-line arguments
#   * consider click instead of argparse
#   * error out if width or height is not a multiple of 8
#   * check if the image or line already has fewer than N unique colors and not generate a new palette if so
#   * parallel scikit-learn k-means is known to sometimes be broken on OS X
import argparse
import cProfile as profile
import io
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
import sklearn.cluster


# NB: also update setup.py when changing
__version__ = '0.0'


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
    'jjn': JARVIS_JUDICE_NINKE,
    'stucki': STUCKI,
    'atkinson': ATKINSON,
}


# Use Lab instead of RGB
# (@XXX@ -- doesn't work. Some code assumes numeric values are in the range [0..1])
USE_LAB = False


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    options = parseArgs(argv)
    if options.shared_palette:
        if options.format == 'scan16':
            print("--shared-palette cannot be used with scan16 format", file=sys.stderr)
            return 1
        palette = getSharedPalette(options)
        with open(options.shared_palette, 'wb') as pal_file:
            writePalette(palette, pal_file)
    else:
        palette = None
    for filename in options.files:
        if options.verbose:
            print(filename, end=' ', flush=True)
            start_time = time.perf_counter()
        runner = profile.runctx if options.profile else exec
        runner("processFile(filename, palette, options)", globals(), locals())
        if options.verbose:
            print("({:.2f} secs)".format(time.perf_counter() - start_time))


def processFile(filename, palette, options):
    try:
        img = skimage.io.imread(filename)
    except (OSError, IOError) as e:
        print("{}: {}".format(filename, e), file=sys.stderr)
        return 1
    if img.ndim == 2:
        # Grayscale; convert to RGB
        img = skimage.color.gray2rgb(img)
    else:
        # Remove alpha channel if present
        img = img[:,:,:3]
    if USE_LAB:
        img = skimage.color.rgb2lab(img)
    else:
        img = skimage.img_as_float(img)
        img = skimage.exposure.adjust_gamma(img, gamma=options.gamma_in)
    chr_data, pal_data = processImage(img, palette, options)
    chr_filename = genOutFilename(filename, options.out_dir, '.chr')
    with open(chr_filename, 'wb') as chr_file:
        chr_file.write(chr_data.getbuffer())
    if pal_data is not None:
        pal_filename = genOutFilename(filename, options.out_dir, '.pal')
        with open(pal_filename, 'wb') as pal_file:
            pal_file.write(pal_data.getbuffer())


def parseArgs(argv):
    parser = argparse.ArgumentParser(
        prog="snesify",
        description="Converts graphics to SNES format",
    )
    parser.add_argument('files', nargs='*')
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + __version__)
    parser.add_argument('--verbose', '-v', action='count')
    parser.add_argument('--out-dir')
    parser.add_argument('--format', '-f', choices=('2bit', '4bit', '8bit', 'scan16'), default='4bit')
    parser.add_argument('--gamma-in', type=float, default=1.0)
    parser.add_argument('--gamma-out', type=float, default=1.0)
    parser.add_argument('--mini-batch', action='store_true')
    parser.add_argument('--shared-palette')
    #parser.add_argument('--starting-index', type=int, default=0)
    #parser.add_argument('--num-colors', type=int, default=0)
    parser.add_argument('--dither', choices=DITHER_FILTERS.keys())
    parser.add_argument('--no-boustrophedon', action='store_true')
    parser.add_argument('--seed', action='store_true')
    parser.add_argument('--window', type=int, default=0)
    parser.add_argument('--profile', action='store_true')
    options = parser.parse_args(argv)
    # @TODO@ -- some other non-Unix OSes may need this behavior
    # @TODO@ -- more elegant way to do this?
    if platform.system() == 'Windows':
        import glob
        filenames = []
        for filename in options.files:
            # If we don't check for wildcards and just run everything through
            # glob.glob, then nonexistent files will be silently ignored. We
            # want to raise an error if the user tries to convert foo.png and
            # foo.png does not exist.
            if '*' in filename or '?' in filename or '[' in filename:
                filenames += glob.glob(filename)
            else:
                filenames.append(filename)
        options.files = filenames
    options.bpp = {
        '2bit': 2,
        '4bit': 4,
        '8bit': 8,
        'scan16': 4,
    }[options.format]
    options.num_colors = 2**options.bpp
    options.diffusion_filter = DITHER_FILTERS.get(options.dither, None)
    options.boustrophedon = not options.no_boustrophedon
    return options


def genOutFilename(filename, out_path, new_extension):
    if not out_path:
        out_path = os.path.dirname(filename)
        if not out_path:
            out_path = '.'
    basename = os.path.basename(filename)
    return out_path + '/' + os.path.splitext(basename)[0] + new_extension


# img should be a 2D numpy array of pixels
# (really a 3D array of color components)
def processImage(img, shared_palette, options):
    chr_file = io.BytesIO()
    pal_file = None if options.shared_palette else io.BytesIO()
    height, width, num_channels = img.shape
    if shared_palette is not None:
        palette = shared_palette
    elif options.format != 'scan16' or options.seed:
        pixels = img.reshape((width*height, num_channels))
        if options.seed:
            seed = genPaletteMedianCut(pixels, options.bpp)
        else:
            seed = None
        palette, _ = genPaletteKmeans(pixels, options, seed=seed)
        if options.format != 'scan16':
            writePalette(palette, pal_file, options)
    else:
        assert options.format == 'scan16' and not options.seed
        palette = None
    diffusion_filter = extendFilter(options.diffusion_filter, num_channels)
    for row_num in range(height//8):
        scanline_rows = []
        for i in range(8):
            scanline_num = row_num*8 + i
            paletted_line, line_palette = processLine(img,
                                                      scanline_num,
                                                      palette,
                                                      diffusion_filter,
                                                      options)
            if options.format == 'scan16':
                writePalette(line_palette, pal_file, options)
            scanline_rows.append(paletted_line)
        writeChrRow(scanline_rows, chr_file, options)
    return chr_file, pal_file

# Reshape filter to number of channels
# If there are 3 channels, [[a,b,c]] becomes [[[a,a,a],[b,b,b],[c,c,c]]]
def extendFilter(filter, num_channels):
    if filter is None:
        return None
    filter_height, filter_width = filter.shape
    filter = np.repeat(filter, num_channels)
    return filter.reshape((filter_height, filter_width, num_channels))


# NB: modifies img in-place to facilitate dithering
# If format is scan16, palette is the seed palette if any, else None
def processLine(img, line_num, palette, diffusion_filter, options):
    height, width, num_channels = img.shape
    line = img[line_num]
    if options.format == 'scan16':
        pal_window = getWindow(img, line_num, options)
        palette, _ = genPaletteKmeans(pal_window, options, seed=palette)
    if diffusion_filter is not None:
        reversed = options.boustrophedon and line_num % 2 != 0
        if reversed:
            diffusion_filter = diffusion_filter[:,::-1]
            the_range = range(len(line)-1, -1, -1)
        else:
            the_range = range(0, len(line))
        paletted_line = []
        for col in the_range:
            # @TODO@ -- clipping may not be appropriate in non-RGB spaces
            line[col] = line[col].clip(0.0, 1.0)
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

# Use k-means to generate a palette
# pixels should be a numpy array
def genPaletteKmeans(pixels, options, seed=None):
    # Make sure all values are 0..1
    # @XXX@ -- not necessarily appropriate in non-RGB colorspaces
    pixels = pixels.clip(0.0, 1.0)
    if options.mini_batch:
        KMeans = sklearn.cluster.MiniBatchKMeans
    else:
        KMeans = sklearn.cluster.KMeans
    kmeans = KMeans(n_clusters=options.num_colors,
                    init=seed if seed is not None else 'k-means++',
                    n_init=1 if seed is not None else 10)
    kmeans.fit(pixels)
    # @XXX@ -- clipping not necessarily appropriate in non-RGB colorspaces
    centroids = kmeans.cluster_centers_.clip(0.0, 1.0)
    labels = kmeans.labels_
    return centroids, labels


# Use median cut to generate a 16-color palette
# Used to generate a seed palette for k-means
# pixels should be a numpy array
def genPaletteMedianCut(pixels, bpp):
    return np.array(getMedianCut(pixels, bpp))

# Return value is list, not array!
def getMedianCut(pixels, depth):
    if depth == 0:
        return [np.mean(pixels, axis=0)]
    channel_num = findChannelWithGreatestRange(pixels)
    sorted_pixels = np.array(sorted(pixels, key=lambda pixel: pixel[channel_num]))
    median = len(sorted_pixels)//2
    lesser = sorted_pixels[:median]
    greater = sorted_pixels[median:]
    return getMedianCut(lesser, depth - 1) + getMedianCut(greater, depth - 1)

def findChannelWithGreatestRange(pixels):
    _, num_channels = pixels.shape
    channel_ranges = [max(pixels[:,i]) - min(pixels[:,i]) for i in range(num_channels)]
    return channel_ranges.index(max(channel_ranges))


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


def writeChrRow(scanline_rows, chr_file, options):
    width = len(scanline_rows[0])
    for chr_num in range(width//8):
        chr_x = chr_num*8
        for shift in range(0, options.bpp, 2):
            shift2 = shift + 1              # shift for second bitplane in pair
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
