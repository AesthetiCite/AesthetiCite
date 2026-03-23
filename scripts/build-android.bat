@echo off
REM AesthetiCite Android Build Script for Windows

echo === AesthetiCite Android Build ===

REM 1. Build web assets
echo Building web assets...
cd client
call npm run build
cd ..

REM 2. Sync to Android
echo Syncing to Android...
call npx cap sync android

REM 3. Open in Android Studio
echo Opening Android Studio...
call npx cap open android

echo.
echo === Next Steps ===
echo 1. Wait for Gradle sync to complete
echo 2. Build ^> Build Bundle(s) / APK(s) ^> Build APK(s)
echo 3. APK location: android\app\build\outputs\apk\debug\app-debug.apk
