@PATH=C:\MFS\cc65\bin;%PATH%
ca65 -l scan16-listing.txt scan16.asm
@if errorlevel 1 goto end
ld65 -C scan16.cfg -o scan16.smc scan16.o
@if errorlevel 1 go to end
fix-checksum.py scan16.smc scan16.smc
:end
@pause
