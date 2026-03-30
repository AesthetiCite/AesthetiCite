#!/bin/sh
# Custom npm script-shell.
# Invoked by npm as: build-runner.sh -c "<script>"
# The cwd when npm calls this varies — it's the package root for top-level
# npm run scripts, but it's the package's own directory for postinstall hooks.
# Using an absolute path in .npmrc ensures this script is found regardless of cwd.
#
# In the production VM, node_modules is absent so npm run build cannot find tsx.
# This wrapper installs ALL dependencies first (if missing), then runs the script.
#
# BUILD_RUNNER_LOCK prevents infinite recursion when npm install triggers postinstall
# hooks that would route back through this script. We also use --ignore-scripts on
# the inner npm install to avoid the script-shell being called recursively for
# package postinstalls (esbuild 0.25+ gets its native binary via @esbuild/linux-x64
# optional dependency, not via postinstall, so --ignore-scripts is safe).

WORKSPACE="/home/runner/workspace"

if [ -z "$BUILD_RUNNER_LOCK" ] && [ ! -f "$WORKSPACE/node_modules/.bin/tsx" ]; then
  export BUILD_RUNNER_LOCK=1
  echo "[build-runner] node_modules/.bin/tsx not found – running npm install..."
  cd "$WORKSPACE" && npm install --ignore-scripts --no-audit --no-fund --loglevel=error
fi

export PATH="$WORKSPACE/node_modules/.bin:$PATH"
exec /bin/sh "$@"
