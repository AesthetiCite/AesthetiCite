# AesthetiCite iOS App Build Guide

## Prerequisites

1. **macOS** with Xcode 15+ installed
2. **Apple Developer Account** (for App Store distribution)
3. **Node.js 18+** and npm
4. **CocoaPods**: `sudo gem install cocoapods`

## Quick Start

### 1. Clone and Setup

```bash
git clone <your-repo>
cd aestheticite
npm install
```

### 2. Build Web Assets

```bash
cd client && npm run build && cd ..
```

### 3. Sync to iOS

```bash
npx cap sync ios
```

### 4. Open in Xcode

```bash
npx cap open ios
```

### 5. Configure Signing

In Xcode:
1. Select the "App" target
2. Go to "Signing & Capabilities" tab
3. Select your Team
4. Xcode will automatically manage signing

### 6. Build and Run

- **Simulator**: Select a simulator, press Cmd+R
- **Device**: Connect iPhone, select it, press Cmd+R
- **Archive**: Product > Archive (for App Store)

## App Configuration

| Setting | Value |
|---------|-------|
| Bundle ID | `com.aestheticite.app` |
| App Name | AesthetiCite |
| Min iOS | 13.0 |
| Orientation | Portrait (primary) |

## API Configuration

The app connects to your backend API. Update `capacitor.config.ts` if needed:

```typescript
server: {
  url: 'https://your-api-domain.com',
  cleartext: false
}
```

## App Store Submission Checklist

- [ ] App icon (1024x1024) - Done
- [ ] Splash screen - Done
- [ ] Privacy policy URL
- [ ] App description
- [ ] Screenshots (6.5" and 5.5")
- [ ] Keywords
- [ ] Support URL
- [ ] Age rating questionnaire

## Troubleshooting

### Pod Install Fails
```bash
cd ios/App && pod install --repo-update
```

### Build Errors
```bash
cd ios/App && pod deintegrate && pod install
```

### Clear Cache
```bash
npx cap sync ios --force
```
