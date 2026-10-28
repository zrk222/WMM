#!/bin/bash
set -euo pipefail
cd "$PROJECT_DIR"
case "${ARCHS:-}" in
  arm64|x86_64) ;;
  *) echo 'error: CPython runtime packaging requires one supported architecture per build.' >&2; exit 1 ;;
esac
test -f Python.xcframework/build/utils.sh || {
  echo 'error: Missing built Python.xcframework. Runtime packaging is required, not optional.' >&2
  exit 1
}
mkdir -p "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/app"
# Copy tracked application sources only, never a workstation database or account state.
rsync -a --include='*/' --include='*.py' --exclude='*' \
  ../mission_control/ "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/app/mission_control/"
mkdir -p "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/app/package"
# Shared offline acquisition arithmetic; exclude profiles/research/account files.
cp ../package/acquisition_analysis.py "$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/app/package/acquisition_analysis.py"
if [ "${CODE_SIGNING_ALLOWED:-YES}" = "NO" ] && [ "${EFFECTIVE_PLATFORM_NAME:-}" = "-iphonesimulator" ]; then
  export EXPANDED_CODE_SIGN_IDENTITY="-"
  export EXPANDED_CODE_SIGN_IDENTITY_NAME="Ad Hoc Simulator"
fi
source Python.xcframework/build/utils.sh
install_python Python.xcframework app
