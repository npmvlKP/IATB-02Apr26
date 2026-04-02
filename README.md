# IATB - Interactive Algorithmic Trading Bot

A Python-based algorithmic trading system with support for multiple brokerage platforms and comprehensive quality gates.

## Features

- Multi-broker support (Interactive Brokers, Alpaca, TD Ameritrade, Binance, Coinbase, Kraken)
- Comprehensive data provider integrations (Alpha Vantage, Polygon.io, Quandl, IEX Cloud, Finnhub)
- Structured logging with UTC-aware timestamps
- Decimal precision for all financial calculations
- Notification services (Slack, Telegram, Email)
- Risk management and position sizing
- Quality gates with 90% code coverage requirement

## Project Structure

```
IATB/
├── src/
│   └── iatb/           # Main application code
├── tests/              # Test suite (90%+ coverage required)
├── scripts/            # Utility scripts
│   ├── setup.ps1       # Project setup
│   ├── quality_gate.ps1 # Quality checks
│   └── git_sync.ps1    # Git and GitHub setup
├── .github/workflows/  # CI/CD pipelines
├── .env.example        # Environment variable template
└── pyproject.toml      # Project configuration
```

## Setup

### Prerequisites

- Python 3.12+
- Poetry
- Git
- GitHub CLI (optional, for GitHub integration)

### Installation

1. Clone the repository
2. Run the setup script:
   ```powershell
   .\scripts\setup.ps1
   ```

3. Copy `.env.example` to `.env` and fill in your API keys:
   ```powershell
   Copy-Item .env.example .env
   # Edit .env with your credentials
   ```

## Quality Gates

This project enforces strict quality standards:

- **Ruff**: Linting and formatting
- **MyPy**: Strict type checking
- **Bandit**: Security analysis
- **Pytest**: 90%+ code coverage
- **Gitleaks**: Secret detection

Run quality gates:
```powershell
.\scripts\quality_gate.ps1
```

## Development Guidelines

- All functions must be ≤ 50 LOC
- Use `Decimal` for all financial data
- Use UTC-aware datetime only
- Use structured logging (no print statements)
- Follow PEP 8 style guide (enforced by Ruff)

## Git & GitHub Setup

Initialize Git and create a private GitHub repository:
```powershell
.\scripts\git_sync.ps1
```

## Testing

Run tests with coverage:
```powershell
poetry run pytest
```

## License

Private Project - All rights reserved