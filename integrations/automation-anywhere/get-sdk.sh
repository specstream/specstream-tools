#!/usr/bin/env bash
# Fetch the Automation Anywhere Package SDK 2.13.0 (the link is on
# https://docs.automationanywhere.com/r/automation-360/cloud-create-package-overview) and take from it
# what the build needs: its two jars and its Gradle wrapper. They are Automation Anywhere's files, so
# they stay out of this repository.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .sdk libs gradle
curl -fsSL -o .sdk/sdk.zip "https://aai.widen.net/content/l73qmay0p3/original/A360-package-sdk-2.13.0.zip"
unzip -q -o .sdk/sdk.zip -d .sdk
cp .sdk/libs/*.jar libs/
cp -r .sdk/gradle/wrapper gradle/
cp .sdk/gradlew .sdk/gradlew.bat .
chmod +x gradlew
echo "SDK ready. Build with JDK 11: ./gradlew clean build shadowJar"
