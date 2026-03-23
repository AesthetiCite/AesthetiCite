#!/bin/bash
# AesthetiCite iOS Build Script
# Run this on a macOS machine with Xcode installed

set -e

echo "=== AesthetiCite iOS Build ==="

# 1. Build web assets
echo "Building web assets..."
cd client && npm run build && cd ..

# 2. Sync to iOS
echo "Syncing to iOS..."
npx cap sync ios

# 3. Open in Xcode (for signing and building)
echo "Opening Xcode..."
npx cap open ios

echo ""
echo "=== Next Steps ==="
echo "1. In Xcode, select your Team for code signing"
echo "2. Update Bundle Identifier if needed: com.aestheticite.app"
echo "3. Build (Cmd+B) and run on simulator or device"
echo "4. For App Store: Product > Archive"
