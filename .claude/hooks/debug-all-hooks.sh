#!/usr/bin/env bash
# Universal diagnostic hook — logs ALL PreToolUse and PostToolUse events
# Writes to .claude/hooks/all-hooks-debug.log

LOG_FILE="C:/Dev/Projects/klippbok-main/.claude/hooks/all-hooks-debug.log"
INPUT=$(cat)

TIMESTAMP=$(date '+%H:%M:%S.%N' 2>/dev/null || date '+%H:%M:%S')

# Extract fields using regex
TOOL_NAME=""
if [[ "$INPUT" =~ \"tool_name\":\"([^\"]*) ]]; then
    TOOL_NAME="${BASH_REMATCH[1]}"
fi

HOOK_EVENT=""
if [[ "$INPUT" =~ \"hook_event_name\":\"([^\"]*) ]]; then
    HOOK_EVENT="${BASH_REMATCH[1]}"
fi

TOOL_USE_ID=""
if [[ "$INPUT" =~ \"tool_use_id\":\"([^\"]*) ]]; then
    TOOL_USE_ID="${BASH_REMATCH[1]}"
fi

# Extract command if Bash tool
COMMAND=""
if [[ "$INPUT" =~ \"command\":\"([^\"]*) ]]; then
    COMMAND="${BASH_REMATCH[1]}"
fi

# Check for tool_response (PostToolUse)
HAS_RESPONSE="no"
if [[ "$INPUT" =~ \"tool_response\" ]]; then
    HAS_RESPONSE="yes"
fi

# Check for answers
HAS_ANSWERS="no"
ANSWERS_CONTENT=""
if [[ "$INPUT" =~ \"answers\":\{([^\}]*)\} ]]; then
    HAS_ANSWERS="yes"
    ANSWERS_CONTENT="${BASH_REMATCH[1]}"
fi

echo "[$TIMESTAMP] $HOOK_EVENT | $TOOL_NAME | id=${TOOL_USE_ID:0:20} | has_response=$HAS_RESPONSE | has_answers=$HAS_ANSWERS | answers=$ANSWERS_CONTENT | cmd=${COMMAND:0:80}" >> "$LOG_FILE"

# Always allow
exit 0
