#!/usr/bin/env bash
# Block Secrets Hook — PreToolUse
# Prevents Claude from reading or editing sensitive files.
# Exit code 2 = block operation and tell Claude why.
#
# Based on Claude Code Mastery Guides V1-V5 by TheDecipherist

INPUT=$(cat)

# Extract tool_name and file_path from hook JSON using bash built-in regex (no external processes)
TOOL_NAME=""
if [[ "$INPUT" =~ \"tool_name\":\"([^\"]*) ]]; then
    TOOL_NAME="${BASH_REMATCH[1]}"
fi

FILE_PATH=""
if [[ "$INPUT" =~ \"file_path\":\"([^\"]*) ]]; then
    FILE_PATH="${BASH_REMATCH[1]}"
fi

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Extract just the filename from the path
FILENAME="${FILE_PATH##*/}"

# Allow Write to .env files (needed for /new-project scaffolding).
# Only block Read/Edit which could leak existing secrets.
if [ "$TOOL_NAME" = "Write" ]; then
    case "$FILENAME" in
        .env*) exit 0 ;;
    esac
fi

# Files that should NEVER be read or edited by Claude
case "$FILENAME" in
    .env|.env.local|.env.production|.env.staging|.env.development|\
    secrets.json|secrets.yaml|id_rsa|id_ed25519|\
    .npmrc|.pypirc|credentials.json|service-account.json|config.json)
        # config.json only blocked under .docker/
        if [ "$FILENAME" = "config.json" ]; then
            if [[ "$FILE_PATH" != *".docker/config.json"* ]]; then
                # Not under .docker/ — allow
                :
            else
                echo "BLOCKED: Access to '$FILE_PATH' denied. This is a sensitive file." >&2
                exit 2
            fi
        else
            echo "BLOCKED: Access to '$FILE_PATH' denied. This is a sensitive file." >&2
            exit 2
        fi
        ;;
esac

# Check path patterns that indicate sensitive content
for PATTERN in "aws/credentials" ".ssh/" "private_key" "secret_key"; do
    if [[ "$FILE_PATH" == *"$PATTERN"* ]]; then
        echo "BLOCKED: Access to '$FILE_PATH' denied. Path matches sensitive pattern '$PATTERN'." >&2
        exit 2
    fi
done

exit 0
