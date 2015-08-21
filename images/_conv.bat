@echo off
snesify -v --format=2bit --seed --out-dir=2bit lenna.png
if errorlevel 1 goto end
snesify -v --format=4bit --seed --out-dir=4bit lenna.png
if errorlevel 1 goto end
snesify -v --format=8bit --seed --out-dir=8bit lenna.png
if errorlevel 1 goto end
snesify -v --format=scan16 --seed --out-dir=scan16 lenna.png
:end
pause
