import re

# Matches: [Type] [Source] YYYY-MM-DD HH:MM:SS [LEVEL]: Message
LOG_PATTERN = re.compile(
    r"""
    ^\s*                                 # Optional leading spaces
    [\'\"]?                              # Optional quote
    \[(?P<type>\w+)\]                    # [Console] or [Metric]
    \s+
    \[(?P<source>[\w\s]+)\]
    \s+
    (?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})
    \s+
    \[(?P<level>\w+)\]:
    \s*
    (?P<message>.+?)                     # Actual message
    [\'\"]?\s*$                          # Optional trailing quote
    """, re.VERBOSE
)

def parse_log_line(line: str):
    line = line.strip()
    match = LOG_PATTERN.match(line)
    if match:
        parsed = match.groupdict()
        print("[Parser] MATCHED:", parsed)  # <-- Diagnostic
        return parsed
    else:
        print("[Parser] NO MATCH for line:", repr(line))  # <-- Diagnostic
        return None
