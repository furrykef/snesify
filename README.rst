=========
 snesify
=========
-------------------------------------------
 A conversion tool to create SNES graphics
-------------------------------------------

This tool is in alpha and all documentation is tentative. Features and functionality may change at random. Use at your own risk.


A note on performance
=====================
snesify uses the scipy library, which can sometimes take a few seconds to start. Subsequent uses of snesify in a single session should be much faster because the program can be loaded from cache.

Using snesify from an SSD can alleviate this issue.


Formats
=======
4bit is the default since it's the most common format on the SNES. Sprites always use 4-bit color, and most backgrounds do too.


2bit, 4bit, 8bit
----------------
These are straightforward enough: these produce ordinary 2-bit, 4-bit, and 8-bit images, with up to 4, 16, and 256 colors, respectively.


scan16
------
This special format is the reason this tool exists; it grew into a more general-purpose tool after it was implemented.

This format has 16 colors per scanline. This results in an image whose quality is in between 4-bit and 8-bit color. The motivation for this format is it can be transferred into VRAM in half the time as 8-bit color and use half the amount of VRAM, yet it's often much better than 4-bit color. This is what makes the large, colorful animations in the SNES port of Five Nights at Freddy's possible.


Quantization
============
Quantization, in this context, is the process of finding a palette that suits the image. If the image already has few enough unique colors, no quantization needs to be done, but if you have too many colors in your image, snesify will need to quantize it. There is a tradeoff here between performance and quality; generating a maximum-quality palette for an 8-bit 256x224 image can take well over a minute. But you can also generate one that's almost as good in a fraction of a second. snesify tries to be smart and strike a balance between performance and quality by default.

For example, a 2-bit image can be quantized very fast even at maximum quality settings, so the other settings default to their maximum when quantizing a 2-bit image. An 8-bit image, however, is very slow to quantize at the highest settings, but the palette is so large that the quality won't affect the palette too much, so snesify defaults to the fastest settings when quantizing an 8-bit image.
