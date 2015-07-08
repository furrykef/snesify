#!/usr/bin/env python
# Syntax: fix-checksum.py infile.smc outfile.smc
# Only works for HiROM games (not including ExHiROM)
# Written for Python 3.4
import struct
import sys

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    infilename, outfilename = argv
    with open(infilename, 'rb') as f:
        romdata = bytearray(f.read())
    romdata[0xffdc:0xffe0] = b'\xff\xff\0\0'
    sum = 0
    for byte in romdata:
        sum += byte
        sum &= 0xffff
    romdata[0xffde:0xffe0] = struct.pack('<H', sum)
    romdata[0xffdc:0xffde] = struct.pack('<H', ~sum & 0xffff)
    with open(outfilename, 'wb') as f:
        f.write(romdata)

if __name__ == '__main__':
    main()
