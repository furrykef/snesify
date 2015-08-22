@echo off
snesify -v --format=2bit --out-dir=2bit lenna.png
if errorlevel 1 goto end
snesify -v --format=4bit --mini-batch --out-dir=4bit lenna.png
if errorlevel 1 goto end
snesify -v --format=8bit --mini-batch --out-dir=8bit lenna.png
if errorlevel 1 goto end
snesify -v --format=scan16 --seed --mini-batch --out-dir=scan16 lenna.png
:end
pause
