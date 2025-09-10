from log_parser import parse_log_line

test_lines = [
    "[Metric] [Coordinator] 2025-07-29 11:03:42 [INFO]: Function 'init_database' executed in 1.241787 seconds (1241.79 ms) at 2025-07-29 11:03:42",
    "[Console] [Coordinator] 2025-07-29 11:03:42 [INFO]: Coordinator Starting",
]

for line in test_lines:
    result = parse_log_line(line)
    print("Parsed:", result)
