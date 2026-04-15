# IATB API Reference

## Table of Contents

1. [Core Engine API](#core-engine-api)
2. [Selection Engine API](#selection-engine-api)
3. [Strategy API](#strategy-api)
4. [Execution API](#execution-api)
5. [Risk Management API](#risk-management-api)
6. [Data Providers API](#data-providers-api)
7. [Backtesting API](#backtesting-api)
8. [FastAPI REST Endpoints](#fastapi-rest-endpoints)

---

## Core Engine API

### Engine Class

```python
from iatb.core.engine import Engine

class Engine:
    """Main trading engine coordinating all components."""
    
    def __init__(self) -> None:
        """Initialize the trading engine."""
        
    async def start(self) -> None:
        """Start the trading engine.
        
        Runs pre-flight checks and initializes all components.
        
        Raises:
            RuntimeError: If pre-flight checks fail
        """
        
    async def stop(self) -> None:
        """Stop the trading engine gracefully."""
        
    def run_selection_cycle(
        self,
        signals: InstrumentSignals,
        regime: MarketRegime
    ) -> list[StrategyContext]:
        """Run a single selection cycle (synchronous).
        
        Args:
            signals: Instrument signals containing all signal data
            regime: Current market regime (BULL/SIDEWAYS/BEAR)
            
        Returns:
            List of StrategyContext objects with selected instruments
            
        Example:
            >>> signals = InstrumentSignals(strength_inputs={...})
            >>> contexts = engine.run_selection_cycle(signals, MarketRegime.BULL)
            >>> for ctx in contexts:
            ...     print(f"{ctx.symbol}: score={ctx.composite_score}")
        """
        
    async def run_selection_cycle_async(
        self,
        signals: InstrumentSignals,
        regime: MarketRegime
    ) -> list[StrategyContext]:
        """Run a single selection cycle (async).
        
        Args:
            signals: Instrument signals containing all signal data
            regime: Current market regime (BULL/SIDEWAYS/BEAR)
            
        Returns:
            List of StrategyContext objects with selected instruments
        """
        
    def engage_kill_switch(self, reason: str) -> None:
        """Engage the kill switch to halt all trading.
        
        Args:
            reason: Reason for engaging the kill switch
            
        Example:
            >>> engine.engage_kill_switch("manual emergency stop")
        """
        
    def disengage_kill_switch(self) -> None:
        """Disengage the kill switch to resume trading.
        
        Example:
            >>> engine.disengage_kill_switch()
        """
```

### EventBus Class

```python
from iatb.core.event_bus import EventBus

class EventBus:
    """Event bus for publishing and subscribing to trading events."""
    
    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.
        
        Args:
            event: Event object to publish
        """
        
    def subscribe(
        self,
        event_type: type[Event],
        callback: Callable[[Event], Awaitable[None]]
    ) -> None:
        """Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            callback: Async callback function to handle events
            
        Example:
            >>> async def handle_trade(event: TradeEvent):
            ...     print(f"Trade executed: {event.symbol}")
            >>> event_bus.subscribe(TradeEvent, handle_trade)
        """
```

---

## Selection Engine API

### InstrumentScorer Class

```python
from iatb.selection.instrument_scorer import InstrumentScorer

class InstrumentScorer:
    """Scores and ranks instruments based on multiple signals."""
    
    def __init__(
        self,
        custom_weights: dict[MarketRegime, dict[str, Decimal]] | None = None
    ) -> None:
        """Initialize the instrument scorer.
        
        Args:
            custom_weights: Optional custom weights per regime
                Format: {regime: {signal_name: weight}}
        """
        
    def score_instruments(
        self,
        signals: InstrumentSignals,
        regime: MarketRegime
    ) -> dict[str, Decimal]:
        """Score instruments based on composite signal.
        
        Args:
            signals: Instrument signals containing all signal data
            regime: Current market regime
            
        Returns:
            Dictionary mapping symbol to composite score [0, 1]
            
        Example:
            >>> scorer = InstrumentScorer()
            >>> scores = scorer.score_instruments(signals, MarketRegime.BULL)
            >>> print(scores['RELIANCE'])  # e.g., 0.85
        """
        
    def rank_instruments(
        self,
        scores: dict[str, Decimal]
    ) -> list[tuple[str, int, Decimal]]:
        """Rank instruments by score.
        
        Args:
            scores: Dictionary mapping symbol to composite score
            
        Returns:
            List of (symbol, rank, score) tuples sorted by rank
            
        Example:
            >>> ranked = scorer.rank_instruments(scores)
            >>> print(ranked[0])  # ('RELIANCE', 1, Decimal('0.85'))
        """
        
    def select_top_n(
        self,
        ranked: list[tuple[str, int, Decimal]],
        n: int = 5,
        min_score: Decimal = Decimal('0.20')
    ) -> list[tuple[str, int, Decimal]]:
        """Select top N instruments with minimum score threshold.
        
        Args:
            ranked: Ranked instruments from rank_instruments()
            n: Maximum number of instruments to select
            min_score: Minimum composite score required
            
        Returns:
            List of selected (symbol, rank, score) tuples
        """
        
    def filter_by_correlation(
        self,
        instruments: list[tuple[str, int, Decimal]],
        correlation_matrix: dict[str, dict[str, Decimal]],
        threshold: Decimal = Decimal('0.80')
    ) -> list[tuple[str, int, Decimal]]:
        """Filter instruments by correlation to diversify portfolio.
        
        Args:
            instruments: List of (symbol, rank, score) tuples
            correlation_matrix: Correlation matrix (Pearson)
            threshold: Correlation threshold above which to drop lower-ranked
            
        Returns:
            Filtered list of instruments
        """
```

### WeightOptimizer Class

```python
from iatb.selection.weight_optimizer import WeightOptimizer

class WeightOptimizer:
    """Optimizes signal weights for maximum predictive power."""
    
    def optimize_weights_for_regime(
        self,
        regime: MarketRegime,
        historical_data: pd.DataFrame,
        n_trials: int = 100
    ) -> dict[str, Decimal]:
        """Optimize weights for a specific market regime.
        
        Uses Optuna TPE search to maximize Information Coefficient (IC).
        
        Args:
            regime: Market regime to optimize for
            historical_data: Historical data with signals and returns
            n_trials: Number of optimization trials
            
        Returns:
            Optimized weight dictionary {signal_name: weight}
            
        Example:
            >>> optimizer = WeightOptimizer()
            >>> weights = optimizer.optimize_weights_for_regime(
            ...     MarketRegime.BULL, data, n_trials=50
            ... )
            >>> print(weights)
        """
```

### ICMonitor Class

```python
from iatb.selection.ic_monitor import ICMonitor

class ICMonitor:
    """Monitors Information Coefficient for alpha decay."""
    
    def check_alpha_decay(
        self,
        scores: dict[str, Decimal],
        returns: dict[str, Decimal],
        threshold: float = 0.03
    ) -> tuple[bool, float]:
        """Check if selector predictive power has decayed.
        
        Args:
            scores: Composite selection scores
            returns: Forward returns (e.g., 5-day)
            threshold: IC threshold below which to warn
            
        Returns:
            Tuple of (is_decayed, ic_value)
            
        Example:
            >>> monitor = ICMonitor()
            >>> is_decayed, ic = monitor.check_alpha_decay(scores, returns)
            >>> if is_decayed:
            ...     print(f"Alpha decay detected! IC={ic:.3f}")
        """
```

---

## Strategy API

### StrategyBase Class

```python
from iatb.strategies.base import StrategyBase

class StrategyBase(ABC):
    """Base class for all trading strategies."""
    
    @abstractmethod
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        """Handle market tick and generate orders.
        
        Args:
            context: Strategy context with instrument metadata
            tick: Current market data tick
            
        Returns:
            List of order requests, or None if no orders
            
        Example:
            >>> class MyStrategy(StrategyBase):
            ...     async def on_tick(self, context, tick):
            ...         if self.should_buy(context, tick):
            ...             return [OrderRequest(
            ...                 symbol=context.symbol,
            ...                 side=OrderSide.BUY,
            ...                 quantity=self.calculate_quantity(context)
            ...             )]
        """
        
    def can_emit_signal(self, context: StrategyContext) -> bool:
        """Check if strategy can emit signal for this instrument.
        
        Checks selection rank - instruments with rank < 1 are blocked.
        
        Args:
            context: Strategy context
            
        Returns:
            True if signal emission is allowed
        """
        
    def scale_quantity_by_rank(
        self,
        quantity: int,
        context: StrategyContext
    ) -> int:
        """Scale quantity based on selection rank.
        
        Higher-ranked instruments get larger positions.
        
        Args:
            quantity: Base quantity
            context: Strategy context
            
        Returns:
            Scaled quantity
        """
```

### MomentumStrategy Class

```python
from iatb.strategies.momentum import MomentumStrategy

class MomentumStrategy(StrategyBase):
    """Momentum-based trading strategy."""
    
    def __init__(
        self,
        lookback_period: int = 20,
        threshold: Decimal = Decimal('0.02')
    ) -> None:
        """Initialize momentum strategy.
        
        Args:
            lookback_period: Period for momentum calculation
            threshold: Minimum momentum threshold for signal
        """
```

### BreakoutStrategy Class

```python
from iatb.strategies.breakout import BreakoutStrategy

class BreakoutStrategy(StrategyBase):
    """Breakout trading strategy."""
    
    def __init__(
        self,
        period: int = 20,
        atr_multiplier: Decimal = Decimal('2.0')
    ) -> None:
        """Initialize breakout strategy.
        
        Args:
            period: Period for high/low calculation
            atr_multiplier: ATR multiplier for stop loss
        """
```

### MeanReversionStrategy Class

```python
from iatb.strategies.mean_reversion import MeanReversionStrategy

class MeanReversionStrategy(StrategyBase):
    """Mean reversion trading strategy."""
    
    def __init__(
        self,
        period: int = 20,
        std_multiplier: Decimal = Decimal('2.0')
    ) -> None:
        """Initialize mean reversion strategy.
        
        Args:
            period: Period for mean/std calculation
            std_multiplier: Standard deviation multiplier for signal
        """
```

---

## Execution API

### OrderManager Class

```python
from iatb.execution.order_manager import OrderManager

class OrderManager:
    """Manages order placement and tracking."""
    
    def __init__(
        self,
        executor: BaseExecutor,
        kill_switch: KillSwitch
    ) -> None:
        """Initialize order manager.
        
        Args:
            executor: Paper or live executor
            kill_switch: Kill switch instance
        """
        
    async def place_order(
        self,
        request: OrderRequest
    ) -> OrderResult:
        """Place an order with full safety pipeline.
        
        Args:
            request: Order request to execute
            
        Returns:
            Order result with status and details
            
        Raises:
            OrderRejectedError: If order fails any validation
            
        Example:
            >>> manager = OrderManager(executor, kill_switch)
            >>> request = OrderRequest(
            ...     symbol='RELIANCE',
            ...     side=OrderSide.BUY,
            ...     quantity=10,
            ...     product=ProductType.MIS
            ... )
            >>> result = await manager.place_order(request)
        """
```

### PreTradeValidator Class

```python
from iatb.execution.pre_trade_validator import PreTradeValidator

class PreTradeValidator:
    """Validates orders before execution (5 gates)."""
    
    def validate_order(
        self,
        request: OrderRequest,
        current_positions: dict[str, Position]
    ) -> ValidationResult:
        """Validate order against 5 safety gates.
        
        Gates:
        1. Fat-finger quantity limit
        2. Max notional value
        3. Price deviation tolerance
        4. Position limit per instrument
        5. Portfolio exposure cap
        
        Args:
            request: Order request to validate
            current_positions: Current portfolio positions
            
        Returns:
            ValidationResult with is_valid and error_message
        """
```

### BaseExecutor Class

```python
from iatb.execution.base import BaseExecutor

class BaseExecutor(ABC):
    """Base class for order executors."""
    
    @abstractmethod
    async def execute_order(
        self,
        request: OrderRequest
    ) -> OrderResult:
        """Execute an order.
        
        Args:
            request: Order request to execute
            
        Returns:
            Order result with execution details
        """
```

---

## Risk Management API

### KillSwitch Class

```python
from iatb.risk.kill_switch import KillSwitch

class KillSwitch:
    """Emergency trading halt mechanism."""
    
    def __init__(self, alert_callback: Callable[[str], Awaitable[None]]) -> None:
        """Initialize kill switch.
        
        Args:
            alert_callback: Async callback for alerts
        """
        
    def engage(self, reason: str) -> None:
        """Engage the kill switch.
        
        Cancels all open orders, blocks all new orders.
        
        Args:
            reason: Reason for engagement
        """
        
    def disengage(self) -> None:
        """Disengage the kill switch (manual reset only)."""
        
    def is_engaged(self) -> bool:
        """Check if kill switch is engaged.
        
        Returns:
            True if engaged
        """
        
    def check_order_allowed(self, request: OrderRequest) -> bool:
        """Check if order is allowed (not blocked by kill switch).
        
        Args:
            request: Order request to check
            
        Returns:
            True if order is allowed
        """
```

### DailyLossGuard Class

```python
from iatb.risk.daily_loss_guard import DailyLossGuard

class DailyLossGuard:
    """Tracks intraday PnL and auto-engages kill switch on excessive loss."""
    
    def __init__(
        self,
        loss_threshold: Decimal = Decimal('0.02'),
        kill_switch: KillSwitch | None = None
    ) -> None:
        """Initialize daily loss guard.
        
        Args:
            loss_threshold: Loss threshold as fraction of NAV (default 2%)
            kill_switch: Optional kill switch to auto-engage
        """
        
    def reset(self, current_nav: Decimal) -> None:
        """Reset daily tracking (call at market open).
        
        Args:
            current_nav: Current net asset value
        """
        
    def record_trade(self, pnl: Decimal) -> None:
        """Record trade PnL.
        
        Auto-engages kill switch if cumulative loss exceeds threshold.
        
        Args:
            pnl: Trade PnL (positive for profit, negative for loss)
        """
        
    def get_cumulative_pnl(self) -> Decimal:
        """Get cumulative intraday PnL.
        
        Returns:
            Cumulative PnL
        """
```

### PositionSizer Class

```python
from iatb.risk.position_sizer import PositionSizer

class PositionSizer:
    """Calculates position sizes based on risk parameters."""
    
    def calculate_quantity(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        risk_per_trade: Decimal,
        current_positions: dict[str, Position]
    ) -> int:
        """Calculate position quantity based on risk parameters.
        
        Args:
            symbol: Instrument symbol
            side: Order side (BUY/SELL)
            entry_price: Entry price
            stop_loss_price: Stop loss price
            risk_per_trade: Risk amount per trade (in currency)
            current_positions: Current portfolio positions
            
        Returns:
            Quantity to trade (rounded to lot size)
        """
```

---

## Data Providers API

### BaseDataProvider Class

```python
from iatb.data.base import BaseDataProvider

class BaseDataProvider(ABC):
    """Base class for market data providers."""
    
    @abstractmethod
    async def get_ohlcv(
        self,
        ticker: str,
        interval: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None
    ) -> pd.DataFrame:
        """Get OHLCV data.
        
        Args:
            ticker: Instrument ticker
            interval: Time interval (day, 5minute, etc.)
            start_date: Start date (UTC)
            end_date: End date (UTC)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        
    @abstractmethod
    async def subscribe_ticker(
        self,
        ticker: str,
        callback: Callable[[Tick], Awaitable[None]]
    ) -> None:
        """Subscribe to real-time ticker updates.
        
        Args:
            ticker: Instrument ticker
            callback: Async callback for tick updates
        """
```

### InstrumentMaster Class

```python
from iatb.data.instrument_master import InstrumentMaster

class InstrumentMaster:
    """Manages instrument metadata and lookups."""
    
    def __init__(self, data_provider: BaseDataProvider) -> None:
        """Initialize instrument master.
        
        Args:
            data_provider: Data provider for fetching instruments
        """
        
    async def load_instruments(self, exchange: Exchange) -> None:
        """Load instruments for an exchange.
        
        Args:
            exchange: Exchange to load (NSE, CDS, MCX)
        """
        
    def get_instrument(self, ticker: str) -> Instrument | None:
        """Get instrument by ticker.
        
        Args:
            ticker: Instrument ticker
            
        Returns:
            Instrument object or None if not found
        """
        
    def search_instruments(
        self,
        query: str,
        exchange: Exchange | None = None
    ) -> list[Instrument]:
        """Search instruments by name or ticker.
        
        Args:
            query: Search query
            exchange: Optional exchange filter
            
        Returns:
            List of matching instruments
        """
```

---

## Backtesting API

### VectorizedBacktester Class

```python
from iatb.backtesting.vectorbt_engine import VectorizedBacktester

class VectorizedBacktester:
    """Vectorized backtesting engine using VectorBT."""
    
    def run_backtest(
        self,
        strategy: StrategyBase,
        data: pd.DataFrame,
        initial_capital: Decimal = Decimal('100000')
    ) -> BacktestResult:
        """Run a vectorized backtest.
        
        Args:
            strategy: Strategy instance to backtest
            data: OHLCV data with multi-index (ticker, timestamp)
            initial_capital: Starting capital
            
        Returns:
            BacktestResult with performance metrics
            
        Example:
            >>> backtester = VectorizedBacktester()
            >>> result = backtester.run_backtest(strategy, data)
            >>> print(f"Sharpe Ratio: {result.sharpe_ratio}")
        """
```

### WalkForwardOptimizer Class

```python
from iatb.backtesting.walk_forward import WalkForwardOptimizer

class WalkForwardOptimizer:
    """Walk-forward optimization for parameter tuning."""
    
    def optimize(
        self,
        strategy: StrategyBase,
        data: pd.DataFrame,
        param_grid: dict[str, list],
        train_size: int = 252,
        test_size: int = 63
    ) -> WalkForwardResult:
        """Run walk-forward optimization.
        
        Args:
            strategy: Strategy instance to optimize
            data: OHLCV data
            param_grid: Parameter grid to search
            train_size: Training window size (in days)
            test_size: Test window size (in days)
            
        Returns:
            WalkForwardResult with optimal parameters and performance
        """
```

### MonteCarloSimulator Class

```python
from iatb.backtesting.monte_carlo import MonteCarloSimulator

class MonteCarloSimulator:
    """Monte Carlo simulation for robustness testing."""
    
    def simulate(
        self,
        returns: pd.Series,
        n_simulations: int = 1000,
        n_days: int = 252
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation.
        
        Args:
            returns: Strategy returns series
            n_simulations: Number of simulations to run
            n_days: Number of days to simulate
            
        Returns:
            MonteCarloResult with distribution metrics
        """
```

---

## FastAPI REST Endpoints

### Health Endpoint

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy" | "degraded",
  "detail": "operational" | "api_not_initialized",
  "message": "Optional additional information"
}
```

### Broker Status Endpoint

```http
GET /broker/status
```

**Response:**
```json
{
  "status": "connected" | "disconnected" | "relogin_required",
  "uid": "ABC123",
  "balance": 100000.0,
  "message": "Broker connection active."
}
```

### OHLCV Chart Endpoint

```http
GET /charts/ohlcv/{ticker}?interval={interval}
```

**Parameters:**
- `ticker`: Instrument symbol (e.g., RELIANCE)
- `interval`: Time interval (default: day)

**Response:**
```json
{
  "status": "success" | "error",
  "ticker": "RELIANCE",
  "data": [
    {
      "timestamp": "2026-01-01T00:00:00Z",
      "open": 2500,
      "high": 2550,
      "low": 2480,
      "close": 2530,
      "volume": 100000
    }
  ],
  "count": 1,
  "message": "Optional error message"
}
```

### Watchlist API Endpoints

```http
# Get watchlist
GET /api/watchlist

# Add to watchlist
POST /api/watchlist
Content-Type: application/json

{
  "symbol": "RELIANCE"
}

# Remove from watchlist
DELETE /api/watchlist/{symbol}
```

### SSE Stream Endpoint

```http
GET /stream/ticks
```

**Response:** Server-Sent Events stream with real-time tick updates.

---

## Error Handling

### Common Errors

```python
# Order rejected
class OrderRejectedError(Exception):
    """Raised when order fails validation."""
    
# API connection error
class APIConnectionError(Exception):
    """Raised when API connection fails."""
    
# Insufficient funds
class InsufficientFundsError(Exception):
    """Raised when insufficient funds for order."""
    
# Market closed
class MarketClosedError(Exception):
    """Raised when attempting to trade outside market hours."""
```

### Error Response Format

```json
{
  "detail": "Error message describing the issue"
}
```

### HTTP Status Codes

- `200 OK`: Successful request
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `502 Bad Gateway`: External API error
- `503 Service Unavailable`: API not initialized or service unavailable

---

## Usage Examples

### Complete Trading Workflow

```python
from iatb.core.engine import Engine
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.instrument_scorer import InstrumentSignals

# Initialize engine
engine = Engine()
await engine.start()

# Prepare signals
signals = InstrumentSignals(
    sentiment_inputs={...},
    strength_inputs={...},
    volume_inputs={...},
    drl_inputs={...}
)

# Run selection cycle
contexts = engine.run_selection_cycle(signals, MarketRegime.BULL)

# Process each selected instrument
for ctx in contexts:
    print(f"{ctx.symbol}: score={ctx.composite_score}, rank={ctx.selection_rank}")
    # Strategy will process this context in on_tick()

# Stop engine
await engine.stop()
```

### Custom Strategy Implementation

```python
from iatb.strategies.base import StrategyBase, StrategyContext, MarketData
from iatb.core.enums import OrderSide
from iatb.execution.order_manager import OrderRequest
from decimal import Decimal

class MyCustomStrategy(StrategyBase):
    """Custom strategy example."""
    
    def __init__(
        self,
        rsi_period: int = 14,
        rsi_threshold: Decimal = Decimal('30')
    ) -> None:
        super().__init__()
        self.rsi_period = rsi_period
        self.rsi_threshold = rsi_threshold
        
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        # Check if instrument is selected
        if not self.can_emit_signal(context):
            return None
            
        # Calculate RSI (simplified)
        rsi = self.calculate_rsi(tick)
        
        # Generate buy signal if RSI is low (oversold)
        if rsi < self.rsi_threshold:
            quantity = self.scale_quantity_by_rank(10, context)
            return [OrderRequest(
                symbol=context.symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=tick.close
            )]
        
        return None
```

### Backtesting Workflow

```python
from iatb.backtesting.vectorbt_engine import VectorizedBacktester
from iatb.strategies.momentum import MomentumStrategy
from decimal import Decimal
import pandas as pd

# Load historical data
data = pd.read_csv('historical_data.csv')

# Initialize strategy
strategy = MomentumStrategy(
    lookback_period=20,
    threshold=Decimal('0.02')
)

# Run backtest
backtester = VectorizedBacktester()
result = backtester.run_backtest(
    strategy=strategy,
    data=data,
    initial_capital=Decimal('100000')
)

# Print results
print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")