import os
import re

# G8: Check for naive datetime.now()
print("=== G8: Naive datetime check ===")
naive_dt_found = False
for root, dirs, files in os.walk('src/iatb/data'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath) as fp:
                content = fp.read()
                if re.search(r'datetime\.now\(\)', content):
                    print(f'Found datetime.now() in {filepath}')
                    naive_dt_found = True

print('G8 (naive datetime): PASS' if not naive_dt_found else 'G8 (naive datetime): FAIL')
print()

# G9: Check for print() statements
print("=== G9: Print statement check ===")
print_found = False
for root, dirs, files in os.walk('src/iatb/data'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath) as fp:
                content = fp.read()
                if re.search(r'\bprint\(', content):
                    print(f'Found print() in {filepath}')
                    print_found = True

print('G9 (no print): PASS' if not print_found else 'G9 (no print): FAIL')