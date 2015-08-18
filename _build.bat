@PATH=C:\MFS\cc65\bin;%PATH%
ca65 -l demo-listing.txt demo.asm
@if errorlevel 1 goto end
ld65 -C demo.cfg -o demo.smc demo.o
@if errorlevel 1 go to end
fix-checksum.py demo.smc demo.smc
:end
@pause
