#!/bin/bash
# Extract changelog section for a specific version
# Usage: ./extract-changelog.sh v0.2.1

VERSION="${1#v}"  # Remove leading 'v' if present

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    exit 1
fi

# Extract content between version header and next version header (or EOF)
awk -v ver="$VERSION" '
    BEGIN { found=0; printing=0 }
    /^## \[/ {
        if (printing) exit
        if ($0 ~ "\\[" ver "\\]") {
            found=1
            printing=1
            next
        }
    }
    printing { print }
    END { if (!found) exit 1 }
' CHANGELOG.md
