@echo off

set outname=%1
set arch=%2
set vc_version=%3
set winsdk_version=%4

call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" %arch% %winsdk_version% -vcvars_ver=%vc_version%

where cl > %outname%
where rc >> %outname%
where mt >> %outname%
set LIB >> %outname%
set INCLUDE >> %outname%
