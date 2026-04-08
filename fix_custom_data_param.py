#!/usr/bin/env python
"""Fix custom_data parameter in instrument_scanner.py"""

with open('src/iatb/scanner/instrument_scanner.py', 'r') as f:
    content = f.read()

# Fix 1: Add custom_data parameter to scan method signature
old_signature = '''    def scan(
        self,
        direction: SortDirection = SortDirection.GAINERS,
    ) -> ScannerResult:'''

new_signature = '''    def scan(
        self,
        direction: SortDirection = SortDirection.GAINERS,
        custom_data: Iterable[MarketData] | None = None,
    ) -> ScannerResult:'''

content = content.replace(old_signature, new_signature)

# Fix 2: Add custom_data handling in scan method body
old_body = '''        scan_timestamp = datetime.now(UTC)
        all_candidates = self._fetch_market_data()'''

new_body = '''        scan_timestamp = datetime.now(UTC)
        if custom_data is not None:
            all_candidates = list(custom_data)
        else:
            all_candidates = self._fetch_market_data()'''

content = content.replace(old_body, new_body)

# Fix 3: Update docstring
old_docstring = '''        """
        Scan instruments using jugaad-data + pandas-ta.

        Args:
            direction: Sort by gainers or losers

        Returns:
            ScannerResult with ranked gainers/losers
        """'''

new_docstring = '''        """
        Scan instruments using jugaad-data + pandas-ta.

        Args:
            direction: Sort by gainers or losers
            custom_data: Optional custom market data for testing (bypasses jugaad-data fetch)

        Returns:
            ScannerResult with ranked gainers/losers
        """'''

content = content.replace(old_docstring, new_docstring)

with open('src/iatb/scanner/instrument_scanner.py', 'w') as f:
    f.write(content)

print("Fixed custom_data parameter in instrument_scanner.py")
