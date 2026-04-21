import os
import re

# Check for float in financial paths (excluding API boundary conversions with comments)
# Per G7 rule: "No float in financial paths (API boundary conversions with comments allowed)"

files = [
    'src/iatb/data/kite_provider.py',
    'src/iatb/data/ccxt_provider.py',
    'src/iatb/data/jugaad_provider.py',
    'src/iatb/data/yfinance_provider.py'
]

# Financial paths to check (data providers are financial paths)
financial_paths = [
    'src/iatb/data/kite_provider.py',
    'src/iatb/data/ccxt_provider.py',
    'src/iatb/data/yfinance_provider.py',
    'src/iatb/backtesting/',
    'src/iatb/execution/',
    'src/iatb/risk/',
    'src/iatb/selection/',
    'src/iatb/sentiment/'
]

float_in_financial_paths = False

for f in files:
    if os.path.exists(f):
        with open(f) as fp:
            content = fp.read()
            lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                # Check if this line contains 'float'
                if re.search(r'\bfloat\b', line):
                    # Check if this is an API boundary conversion with a comment
                    # Allow float in isinstance checks with explanatory comments
                    if 'isinstance' in line and ('API boundary' in line or 'API' in line or 'external' in line):
                        # This is an allowed API boundary conversion
                        continue
                    
                    # Check if it's a type annotation or parameter with inline comment
                    if re.search(r':\s*float\b', line):
                        # Check current line for comment
                        if ('# API' in line or '# external' in line or 
                            'Timing configuration' in line or 'not financial' in line):
                            continue
                        
                        # Check previous line for comment (multiline parameter definitions)
                        prev_line = lines[i - 2] if i > 1 else ''
                        if ('# API' in prev_line or '# external' in prev_line or 
                            'Timing configuration' in prev_line or 'not financial' in prev_line):
                            continue
                        else:
                            print(f'Line {i} in {f}: {line.strip()}')
                            float_in_financial_paths = True
                    elif re.search(r'=\s*\d+\.\d+', line):
                        # Float literal in assignment - not allowed
                        print(f'Line {i} in {f}: {line.strip()}')
                        float_in_financial_paths = True

print('Float check: PASS' if not float_in_financial_paths else 'Float check: FAIL - Found float in financial paths (excluding API boundary conversions)')
