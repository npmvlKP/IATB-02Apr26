# IATB Architecture Documentation

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                IATB TRADING SYSTEM                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL INTEGRATIONS                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   Zerodha    │  │   Jugaad     │  │   YFinance   │  │   CCXT       │           │
│  │  Kite API    │  │   Data       │  │   Finance    │  │  (Global)    │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                 │                     │
│         └─────────────────┴─────────────────┴─────────────────┘                     │
│                                   │                                                   │
│                           ┌───────▼────────┐                                          │
│                           │  Data Layer    │                                          │
│                           └───────┬────────┘                                          │
└───────────────────────────────────┼───────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                              CORE ENGINE LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                            Trading Engine                                     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │  │
│  │  │  Clock   │  │ EventBus │  │ Config   │  │   SSE    │  │  Health  │      │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │  │
│  └───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┘  │
│          │             │             │             │             │                │
│  ┌───────▼─────────────▼─────────────▼─────────────▼─────────────▼─────────────┐  │
│  │                     Selection Engine                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │  Composite   │  │    Rank      │  │ Correlation  │  │   Weight     │   │  │
│  │  │   Scorer     │  │  Normalizer  │  │   Filter     │  │  Optimizer   │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                    Signal Aggregation Layer                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │  Sentiment   │  │    Market    │  │  Volume      │  │     DRL      │   │  │
│  │  │   Signal     │  │  Strength    │  │   Profile    │  │   Signal     │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                            STRATEGY & EXECUTION LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                           Strategy Library                                    │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │  │
│  │  │ Momentum │  │ Breakout │  │  Mean    │  │Sentiment│  │ Ensemble │      │  │
│  │  │ Strategy │  │ Strategy │  │ Reversion│  │ Strategy │  │ Strategy │      │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │  │
│  └───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┘  │
│          │             │             │             │             │                │
│  ┌───────▼─────────────▼─────────────▼─────────────▼─────────────▼─────────────┐  │
│  │                      Execution Layer                                         │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │ Order Manager│  │ Pre-Trade    │  │  Live/Paper  │  │   Trade      │   │  │
│  │  │              │  │ Validator    │  │  Executor    │  │    Audit     │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                            RISK MANAGEMENT LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Kill Switch  │  │ Daily Loss   │  │ Position     │  │ SEBI         │           │
│  │              │  │ Guard        │  │ Sizer        │  │ Compliance   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Stop Loss    │  │ Trailing     │  │ Circuit      │  │ Portfolio    │           │
│  │ Manager      │  │ Stop         │  │ Breaker      │  │ Risk         │           │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                            ANALYTICS & STORAGE LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                          Machine Learning                                      │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │  │
│  │  │   LSTM   │  │    GNN   │  │   HMM    │  │Transformer│  │ Ensemble │      │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │  │
│  └───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┘  │
│          │             │             │             │             │                │
│  ┌───────▼─────────────▼─────────────▼─────────────▼─────────────▼─────────────┐  │
│  │                     Reinforcement Learning                                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │  PPO Agent   │  │  A2C Agent   │  │  SAC Agent   │  │   Optuna     │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                          Storage & Persistence                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │  │
│  │  │    DuckDB    │  │   SQLite     │  │   Parquet    │  │   Git Sync   │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                            BACKTESTING LAYER                                           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Event-Driven │  │ Vectorized   │  │ Walk-Forward │  │  Monte       │           │
│  │ Backtester   │  │ Backtester   │  │ Optimizer    │  │   Carlo      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                            OBSERVABILITY LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Structured  │  │   Metrics    │  │   Tracing    │  │   Alerting   │           │
│  │   Logging    │  │   (Prometheus)│  │  (OpenTelemetry)│  (Telegram)   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                          Visualization                                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │  │
│  │  │Dashboard │  │  Charts  │  │  Alerts  │  │ Breakout │  │Portfolio │      │  │
│  │  │  (Web)   │  │          │  │          │  │  Scanner │  │  View    │      │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│                            API LAYER                                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                            FastAPI Application                                  │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │  │
│  │  │  Health  │  │  Broker  │  │  OHLCV   │  │ Watchlist│  │  SSE     │      │  │
│  │  │ Endpoint │  │  Status  │  │  Charts  │  │  API     │  │  Stream  │      │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Architecture

### 1. Market Data Ingestion Flow

```
External APIs (Zerodha, Jugaad, YFinance, CCXT)
        │
        ▼
┌───────────────────────────────────────┐
│      Data Provider Layer             │
│  - Instrument Master                 │
│  - Real-time WebSocket Feeds         │
│  - Historical Data Fetch             │
│  - Market Data Cache                 │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Data Normalization              │
│  - Timestamp Alignment (UTC)         │
│  - Decimal Precision                 │
│  - Missing Data Handling             │
│  - Data Validation                   │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Signal Generation              │
│  - Sentiment Analysis                │
│  - Market Strength Scoring           │
│  - Volume Profile Analysis           │
│  - DRL Backtesting Results           │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Selection Engine                │
│  - Composite Scoring                 │
│  - Rank Normalization                │
│  - Correlation Filtering             │
│  - Top-N Selection                   │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Strategy Execution             │
│  - Signal Generation                 │
│  - Order Placement                   │
│  - Risk Validation                   │
│  - Trade Execution                   │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Risk Management                │
│  - Pre-Trade Validation             │
│  - Position Limits                   │
│  - Stop Loss / Trailing Stop         │
│  - Kill Switch                       │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Order Execution                 │
│  - Paper Trading Mode                │
│  - Live Trading Mode                 │
│  - Order Throttling                  │
│  - Trade Audit Logging               │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│      Storage & Analytics             │
│  - Trade Persistence (DuckDB/SQLite) │
│  - Performance Metrics               │
│  - Backtesting Results               │
│  - ML Model Training                 │
└───────────────────────────────────────┘
```

### 2. Event-Driven Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Event Bus                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │   Tick   │  │  Order   │  │  Trade   │  │   Risk   │     │
│  │  Event   │  │  Event   │  │  Event   │  │  Event   │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
└───────┼─────────────┼─────────────┼─────────────┼────────────┘
        │             │             │             │
        ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Event Subscribers                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Strategy   │  │    Risk      │  │   Storage    │          │
│  │   Engine     │  │  Managers    │  │   Layer      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Selection    │  │  Execution   │  │ Observability│          │
│  │ Engine       │  │  Layer       │ │   Layer      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Component Interactions

### 1. Selection Engine Flow

```
Market Data → Sentiment Analyzer → Sentiment Signal
Market Data → Strength Scorer → Strength Signal
Market Data → Volume Profile → Volume Signal
Backtest Results → DRL Signal → DRL Signal

Sentiment Signal ┐
Strength Signal ├→ Composite Scorer → Rank Normalizer
Volume Signal  │                      ↓
DRL Signal     ┘                 Correlation Filter
                                     ↓
                                Top-N Selection
                                     ↓
                            Strategy Context List
```

### 2. Order Execution Flow

```
Strategy Signal → Order Request
                     ↓
              Pre-Trade Validator (5 gates)
                     ↓
              Kill Switch Check
                     ↓
              Order Manager
                     ↓
              Paper/Live Executor
                     ↓
              Trade Audit Logger
                     ↓
              Daily Loss Guard
                     ↓
              Order Confirmation
```

### 3. Risk Management Flow

```
Order Request → Position Sizer → Quantity Check
                     ↓
              Portfolio Risk → Exposure Check
                     ↓
              SEBI Compliance → Regulatory Check
                     ↓
              Stop Loss Manager → Risk Check
                     ↓
              Circuit Breaker → Loss Check
                     ↓
              Kill Switch → Emergency Stop
```

## Technology Stack

### Core Technologies
- **Python 3.12+**: Primary programming language
- **Poetry**: Dependency management and packaging
- **FastAPI**: REST API framework
- **Pydantic**: Data validation and settings management
- **SQLAlchemy**: Database ORM
- **Alembic**: Database migrations

### Data Processing
- **Pandas**: Data manipulation and analysis
- **NumPy**: Numerical computing
- **Decimal**: Precision arithmetic for financial data
- **DuckDB**: High-performance analytical database
- **SQLite**: Lightweight database for audit trails

### Machine Learning
- **PyTorch**: Deep learning framework
- **Scikit-learn**: Traditional ML algorithms
- **Optuna**: Hyperparameter optimization
- **Stable-Baselines3**: Reinforcement learning
- **HMMlearn**: Hidden Markov Models
- **Transformers**: NLP models (FinBERT)

### Testing & Quality
- **Pytest**: Testing framework
- **pytest-cov**: Code coverage
- **Ruff**: Linting and formatting
- **MyPy**: Static type checking
- **Bandit**: Security analysis
- **Gitleaks**: Secret detection

### Observability
- **Prometheus**: Metrics collection
- **OpenTelemetry**: Distributed tracing
- **Python JSON Logger**: Structured logging
- **Telegram**: Alert notifications

### External Integrations
- **Zerodha Kite Connect**: Indian broker API
- **Jugaad Data**: Indian market data
- **yFinance**: Global market data
- **CCXT**: Multi-exchange support
- **AION Sentiment**: News sentiment analysis

## Deployment Architecture

### Development Environment
```
Developer Machine
    │
    ├── Poetry Virtual Environment
    ├── Local SQLite Database
    ├── Local DuckDB Storage
    └── FastAPI Development Server (Uvicorn)
```

### Production Environment
```
Server
    │
    ├── Docker Container
    │   ├── Poetry Production Environment
    │   ├── Production Database (PostgreSQL/MySQL)
    │   ├── Redis Cache (optional)
    │   └── Gunicorn + Uvicorn Workers
    │
    ├── Nginx (Reverse Proxy & SSL)
    ├── Prometheus (Metrics)
    ├── Grafana (Visualization)
    └── AlertManager (Alerts)
```

### Security Considerations

1. **API Security**
   - Rate limiting
   - IP whitelisting (Zerodha requirement)
   - API key rotation
   - Secret management (environment variables)

2. **Data Security**
   - Encrypted database connections
   - Secure file storage
   - Audit trail logging
   - Regular backups

3. **Network Security**
   - TLS/SSL encryption
   - Firewall rules
   - VPN access (optional)
   - DDoS protection

## Performance Considerations

### 1. Data Processing
- Async/await for I/O operations
- Connection pooling for databases
- Caching for frequently accessed data
- Batch processing for historical data

### 2. Order Execution
- WebSocket for real-time data
- Order throttling to prevent rate limit violations
- Parallel order processing (where allowed)
- Optimistic locking for position updates

### 3. Strategy Execution
- Event-driven architecture for low latency
- Pre-computed indicators where possible
- Efficient data structures for signal generation
- Lazy loading for large datasets

## Scalability Considerations

### 1. Horizontal Scaling
- Stateless API design
- Load balancing for API servers
- Distributed task queue for background jobs
- Microservices architecture (future)

### 2. Vertical Scaling
- Multi-core processing for backtesting
- GPU acceleration for ML models
- Memory optimization for large datasets
- Database query optimization

### 3. Data Storage
- Time-series databases for market data
- Partitioning for historical data
- Archival of old data
- Data compression techniques