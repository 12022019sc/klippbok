#!/usr/bin/env bash
# Diagnostic hook — logs AskUserQuestion PreToolUse and PostToolUse events
# Writes to .claude/hooks/askuser-debug.log

LOG_FILE="C:/Dev/Projects/klippbok-main/.claude/hooks/askuser-debug.log"
INPUT=$(cat)

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S.%N' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')

# Detect which hook event this is
TOOL_NAME=""
if [[ "$INPUT" =~ \"tool_name\":\"([^\"]*) ]]; then
    TOOL_NAME="${BASH_REMATCH[1]}"
fi

HOOK_EVENT=""
if [[ "$INPUT" =~ \"hook_event\":\"([^\"]*) ]]; then
    HOOK_EVENT="${BASH_REMATCH[1]}"
fi

echo "========================================" >> "$LOG_FILE"
echo "[$TIMESTAMP] Tool: $TOOL_NAME | Event: $HOOK_EVENT" >> "$LOG_FILE"
echo "--- RAW INPUT (first 2000 chars) ---" >> "$LOG_FILE"
echo "$INPUT" | head -c 2000 >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Log tool_input.questions if present (PreToolUse)
if [[ "$INPUT" =~ \"questions\" ]]; then
    echo "--- QUESTIONS DETECTED (PreToolUse) ---" >> "$LOG_FILE"
fi

# Log tool_result if present (PostToolUse)
if [[ "$INPUT" =~ \"tool_result\" ]]; then
    echo "--- TOOL RESULT DETECTED (PostToolUse) ---" >> "$LOG_FILE"
fi

# Log answers if present
if [[ "$INPUT" =~ \"answers\" ]]; then
    echo "--- ANSWERS FIELD PRESENT ---" >> "$LOG_FILE"
else
    echo "--- NO ANSWERS FIELD ---" >> "$LOG_FILE"
fi

echo "========================================" >> "$LOG_FILE"

# Always allow — this is just logging
exit 0
