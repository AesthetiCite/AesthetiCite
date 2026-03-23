# AesthetiCite Android Build Guide (Windows 11)

## Prerequisites

### 1. Install Android Studio

Download and install Android Studio from:
https://developer.android.com/studio

During installation, make sure to include:
- Android SDK
- Android SDK Platform
- Android Virtual Device (AVD)

### 2. Install Node.js

Download Node.js 18+ from:
https://nodejs.org/

### 3. Set Environment Variables

Add these to your system PATH:
- `C:\Users\YOUR_USERNAME\AppData\Local\Android\Sdk\platform-tools`
- `C:\Users\YOUR_USERNAME\AppData\Local\Android\Sdk\tools`

## Build Steps

### Step 1: Clone the Project

```powershell
git clone <your-repo-url>
cd aestheticite
```

### Step 2: Install Dependencies

```powershell
npm install
```

### Step 3: Build Web Assets

```powershell
cd client
npm run build
cd ..
```

### Step 4: Sync to Android

```powershell
npx cap sync android
```

### Step 5: Open in Android Studio

```powershell
npx cap open android
```

This opens Android Studio with the project.

### Step 6: Build APK

In Android Studio:

1. Wait for Gradle sync to complete (may take a few minutes first time)
2. Click **Build** menu > **Build Bundle(s) / APK(s)** > **Build APK(s)**
3. APK will be at: `android/app/build/outputs/apk/debug/app-debug.apk`

### Step 7: Install on Device

**Option A: USB Cable**
1. Enable Developer Options on your Android phone
2. Enable USB Debugging
3. Connect phone via USB
4. Run: `adb install android/app/build/outputs/apk/debug/app-debug.apk`

**Option B: Direct Transfer**
1. Copy the APK to your phone
2. Open it with a file manager
3. Enable "Install from unknown sources" when prompted
4. Install the app

## Build for Release (Play Store)

### Generate Signing Key

```powershell
keytool -genkey -v -keystore aestheticite-release.keystore -alias aestheticite -keyalg RSA -keysize 2048 -validity 10000
```

### Configure Signing

Edit `android/app/build.gradle`, add inside `android {}`:

```gradle
signingConfigs {
    release {
        storeFile file('path/to/aestheticite-release.keystore')
        storePassword 'your-store-password'
        keyAlias 'aestheticite'
        keyPassword 'your-key-password'
    }
}

buildTypes {
    release {
        signingConfig signingConfigs.release
        minifyEnabled true
        proguardFiles getDefaultProguardFile('proguard-android.txt'), 'proguard-rules.pro'
    }
}
```

### Build Release APK

In Android Studio:
1. **Build** > **Generate Signed Bundle / APK**
2. Select **APK**
3. Choose your keystore
4. Select **release** build variant
5. APK generated at: `android/app/build/outputs/apk/release/app-release.apk`

## App Configuration

| Setting | Value |
|---------|-------|
| Package Name | `com.aestheticite.app` |
| App Name | AesthetiCite |
| Min SDK | 22 (Android 5.1) |
| Target SDK | 34 (Android 14) |
| Theme Color | #0F172A |

## Troubleshooting

### Gradle Sync Failed
1. File > Invalidate Caches > Restart
2. Delete `android/.gradle` folder
3. Re-sync

### SDK Not Found
1. Open SDK Manager in Android Studio
2. Install Android 14 (API 34)
3. Accept licenses

### ADB Not Found
Add Android SDK to PATH:
```powershell
$env:PATH += ";C:\Users\YOUR_USERNAME\AppData\Local\Android\Sdk\platform-tools"
```

## Quick Test

Install and run on connected device:
```powershell
npx cap run android
```
