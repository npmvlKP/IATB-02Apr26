# IATB Strategy Development Guide

## Table of Contents

1. [Overview](#overview)
2. [Strategy Architecture](#strategy-architecture)
3. [Creating Your First Strategy](#creating-your-first-strategy)
4. [Strategy Testing](#strategy-testing)
5. [Backtesting Strategies](#backtesting-strategies)
6. [Integration with Selection Engine](#integration-with-selection-engine)
7. [Best Practices](#best-practices)
8. [Common Patterns](#common-patterns)
9. [Debugging Strategies](#debugging-strategies)
10. [Examples](#examples)

---

## Overview

This guide walks you through creating, testing, and deploying trading strategies in IATB. Strategies are the core decision-making components that analyze market data and generate trading signals.

### Key Concepts

- **Strategy**: A class that implements trading logic and generates order requests
- **StrategyContext**: Contains instrument metadata, signals, and ranking information
- **MarketData**: Real-time market tick data (price, volume, etc.)
- **OrderRequest**: Generated orders to be executed
- **Selection Rank**: Instrument ranking from the selection engine (affects position sizing)

---

## Strategy Architecture

### StrategyBase Class

All strategies inherit from `StrategyBase`:

```python
from iatb.strategies.base import StrategyBase, StrategyContext, MarketData
from iatb.execution.order_manager import OrderRequest
from iatb.core.enums import OrderSide
from decimal import Decimal

class MyStrategy(StrategyBase):
    """Your custom strategy."""
    
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        """Called on every market tick."""
        pass
```

### Strategy Lifecycle

```
Engine Start → Strategy Initialization → Market Open
     ↓
Market Data Arrives → on_tick() → Signal Generation
     ↓
Order Requests → Validation → Execution
     ↓
Market Close → Strategy Cleanup → Engine Stop
```

---

## Creating Your First Strategy

### Step 1: Define Strategy Class

```python
from iatb.strategies.base import StrategyBase, StrategyContext, MarketData
from iatb.execution.order_manager import OrderRequest
from iatb.core.enums import OrderSide, ProductType
from decimal import Decimal

class SimpleMomentumStrategy(StrategyBase):
    """Simple momentum strategy based on price change."""
    
    def __init__(
        self,
        threshold: Decimal = Decimal('0.02'),
        quantity: int = 10
    ) -> None:
        """Initialize strategy with parameters."""
        super().__init__()
        self.threshold = threshold  # 2% price change threshold
        self.quantity = quantity
        self.entry_prices: dict[str, Decimal] = {}
        
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        """Process tick and generate orders."""
        symbol = context.symbol
        
        # Check if instrument is selected
        if not self.can_emit_signal(context):
            return None
        
        # Initialize entry price if not set
        if symbol not in self.entry_prices:
            self.entry_prices[symbol] = tick.close
            return None
        
        entry_price = self.entry_prices[symbol]
        price_change = (tick.close - entry_price) / entry_price
        
        # Buy if price increased by threshold
        if price_change >= self.threshold:
            self.entry_prices[symbol] = tick.close  # Update entry
            return [OrderRequest(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=self.quantity,
                product=ProductType.MIS
            )]
        
        return None
```

### Step 2: Implement Required Methods

Your strategy must implement:

1. **`on_tick()`**: Main logic called on every market tick
2. **`__init__()`**: Initialize strategy parameters (optional)

Optional methods you can override:

3. **`can_emit_signal()`**: Check if signal is allowed (uses selection rank)
4. **`scale_quantity_by_rank()`**: Adjust position size based on rank
5. **`on_order_filled()`**: Called when an order is filled
6. **`on_market_open()`**: Called at market open
7. **`on_market_close()`**: Called at market close

### Step 3: Register Your Strategy

Add your strategy to `src/iatb/strategies/__init__.py`:

```python
from .simple_momentum import SimpleMomentumStrategy

__all__ = [
    # ... existing strategies
    "SimpleMomentumStrategy",
]
```

---

## Strategy Testing

### Unit Testing

Create tests in `tests/strategies/test_simple_momentum.py`:

```python
import pytest
from decimal import Decimal
from iatb.strategies.simple_momentum import SimpleMomentumStrategy
from iatb.selection.instrument_scorer import StrategyContext
from iatb.data.base import MarketData
from iatb.core.enums import Exchange, InstrumentType

@pytest.fixture
def strategy():
    """Create strategy instance."""
    return SimpleMomentumStrategy(
        threshold=Decimal('0.02'),
        quantity=10
    )

@pytest.fixture
def context():
    """Create strategy context."""
    return StrategyContext(
        symbol='RELIANCE',
        exchange=Exchange.NSE,
        instrument_type=InstrumentType.EQUITY,
        composite_score=Decimal('0.85'),
        selection_rank=1
    )

@pytest.mark.asyncio
async def test_on_tick_no_signal(strategy, context):
    """Test no signal when threshold not met."""
    tick = MarketData(
        timestamp=datetime.now(UTC),
        symbol='RELIANCE',
        open=Decimal('2500'),
        high=Decimal('2510'),
        low=Decimal('2495'),
        close=Decimal('2505'),
        volume=100000
    )
    
    orders = await strategy.on_tick(context, tick)
    assert orders is None

@pytest.mark.asyncio
async def test_on_tick_buy_signal(strategy, context):
    """Test buy signal when threshold met."""
    # Simulate price increase
    tick = MarketData(
        timestamp=datetime.now(UTC),
        symbol='RELIANCE',
        open=Decimal('2550'),
        high=Decimal('2560'),
        low=Decimal('2545'),
        close=Decimal('2555'),
        volume=100000
    )
    
    orders = await strategy.on_tick(context, tick)
    assert orders is not None
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BUY
    assert orders[0].quantity == 10
```

### Integration Testing

Test your strategy with the full engine:

```python
import pytest
from iatb.core.engine import Engine
from iatb.strategies.simple_momentum import SimpleMomentumStrategy

@pytest.mark.asyncio
async def test_strategy_integration():
    """Test strategy integration with engine."""
    engine = Engine()
    await engine.start()
    
    # Your strategy will be instantiated by the engine
    # based on configuration
    
    await engine.stop()
```

---

## Backtesting Strategies

### Step 1: Prepare Historical Data

```python
import pandas as pd
from datetime import datetime, UTC

# Load historical OHLCV data
data = pd.read_csv('historical_data.csv')

# Ensure proper format
data['timestamp'] = pd.to_datetime(data['timestamp'])
data.set_index(['ticker', 'timestamp'], inplace=True)
data.sort_index(inplace=True)
```

### Step 2: Run Backtest

```python
from iatb.backtesting.vectorbt_engine import VectorizedBacktester
from iatb.strategies.simple_momentum import SimpleMomentumStrategy
from decimal import Decimal

# Initialize strategy
strategy = SimpleMomentumStrategy(
    threshold=Decimal('0.02'),
    quantity=10
)

# Run backtest
backtester = VectorizedBacktester()
result = backtester.run_backtest(
    strategy=strategy,
    data=data,
    initial_capital=Decimal('100000')
)

# Analyze results
print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
print(f"Win Rate: {result.win_rate:.2%}")
print(f"Total Trades: {result.total_trades}")
```

### Step 3: Optimize Parameters

```python
from iatb.backtesting.walk_forward import WalkForwardOptimizer

# Define parameter grid
param_grid = {
    'threshold': [
        Decimal('0.01'),
        Decimal('0.015'),
        Decimal('0.02'),
        Decimal('0.025')
    ],
    'quantity': [5, 10, 15, 20]
}

# Run walk-forward optimization
optimizer = WalkForwardOptimizer()
result = optimizer.optimize(
    strategy=strategy,
    data=data,
    param_grid=param_grid,
    train_size=252,  # 1 year training
    test_size=63    # 3 months testing
)

print(f"Best Parameters: {result.best_params}")
print(f"Best Sharpe Ratio: {result.best_sharpe_ratio:.2f}")
```

### Step 4: Robustness Testing

```python
from iatb.backtesting.monte_carlo import MonteCarloSimulator

# Run Monte Carlo simulation
simulator = MonteCarloSimulator()
mc_result = simulator.simulate(
    returns=result.returns,
    n_simulations=1000,
    n_days=252
)

print(f"95th Percentile Return: {mc_result.percentile_95:.2%}")
print(f"5th Percentile Return: {mc_result.percentile_5:.2%}")
print(f"Probability of Positive Return: {mc_result.prob_positive:.2%}")
```

---

## Integration with Selection Engine

### Using Selection Rank

The selection engine ranks instruments based on multiple signals. Use this to:

1. **Filter instruments**: Only trade high-ranked instruments
2. **Scale positions**: Allocate more capital to higher-ranked instruments

```python
class RankWeightedStrategy(StrategyBase):
    """Strategy that weights positions by selection rank."""
    
    def __init__(self, base_quantity: int = 10) -> None:
        super().__init__()
        self.base_quantity = base_quantity
    
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        # Check if instrument is selected (rank >= 1)
        if not self.can_emit_signal(context):
            return None
        
        # Scale quantity based on rank (higher rank = larger position)
        quantity = self.scale_quantity_by_rank(self.base_quantity, context)
        
        # Generate signal...
        return [OrderRequest(
            symbol=context.symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            product=ProductType.MIS
        )]
```

### Accessing Composite Score

```python
class ScoreThresholdStrategy(StrategyBase):
    """Strategy that only trades instruments with high composite score."""
    
    def __init__(self, min_score: Decimal = Decimal('0.70')) -> None:
        super().__init__()
        self.min_score = min_score
    
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        # Check if composite score meets threshold
        if context.composite_score < self.min_score:
            return None
        
        # Generate signal...
        pass
```

---

## Best Practices

### 1. Use Decimal for Financial Calculations

```python
# BAD
price = 2500.50
quantity = 10
total = price * quantity  # Float precision issues

# GOOD
from decimal import Decimal
price = Decimal('2500.50')
quantity = 10
total = price * quantity  # Precise calculation
```

### 2. Use UTC Timestamps

```python
from datetime import datetime, UTC

# BAD
now = datetime.now()  # Local time

# GOOD
now = datetime.now(UTC)  # UTC time
```

### 3. Implement Proper Error Handling

```python
async def on_tick(
    self,
    context: StrategyContext,
    tick: MarketData
) -> list[OrderRequest] | None:
    try:
        # Strategy logic
        return orders
    except Exception as e:
        logger.error(f"Strategy error for {context.symbol}: {e}")
        return None  # Fail gracefully
```

### 4. Avoid State Mutability Issues

```python
class SafeStrategy(StrategyBase):
    def __init__(self):
        super().__init__()
        self._state_lock = asyncio.Lock()
    
    async def on_tick(self, context, tick):
        async with self._state_lock:
            # Modify state safely
            pass
```

### 5. Use Structured Logging

```python
from iatb.core.observability.logging_config import get_logger

logger = get_logger(__name__)

async def on_tick(self, context, tick):
    logger.info(
        "Processing tick",
        symbol=context.symbol,
        price=str(tick.close),
        score=str(context.composite_score)
    )
```

### 6. Keep Functions Small (< 50 LOC)

```python
# BAD
async def on_tick(self, context, tick):
    # 100+ lines of logic
    pass

# GOOD
async def on_tick(self, context, tick):
    if not self._should_trade(context, tick):
        return None
    
    signal = self._generate_signal(context, tick)
    if signal is None:
        return None
    
    return self._create_orders(context, signal)

def _should_trade(self, context, tick):
    """Check trading conditions."""
    pass

def _generate_signal(self, context, tick):
    """Generate trading signal."""
    pass

def _create_orders(self, context, signal):
    """Create order requests."""
    pass
```

### 7. Test Edge Cases

```python
@pytest.mark.asyncio
async def test_strategy_with_low_rank():
    """Test strategy behavior with low selection rank."""
    context = StrategyContext(
        symbol='RELIANCE',
        composite_score=Decimal('0.30'),
        selection_rank=10  # Low rank
    )
    
    orders = await strategy.on_tick(context, tick)
    assert orders is None  # Should not trade
```

---

## Common Patterns

### Pattern 1: Technical Indicator Strategy

```python
import talib
import numpy as np

class RSIStrategy(StrategyBase):
    """RSI-based mean reversion strategy."""
    
    def __init__(
        self,
        rsi_period: int = 14,
        oversold: int = 30,
        overbought: int = 70
    ) -> None:
        super().__init__()
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.price_history: dict[str, list[Decimal]] = {}
    
    async def on_tick(self, context, tick):
        # Update price history
        if context.symbol not in self.price_history:
            self.price_history[context.symbol] = []
        
        self.price_history[context.symbol].append(tick.close)
        
        # Need enough data for RSI
        if len(self.price_history[context.symbol]) < self.rsi_period:
            return None
        
        # Calculate RSI
        prices = np.array([float(p) for p in self.price_history[context.symbol]])
        rsi = talib.RSI(prices, timeperiod=self.rsi_period)[-1]
        
        # Generate signals
        if rsi < self.oversold:
            return [OrderRequest(
                symbol=context.symbol,
                side=OrderSide.BUY,
                quantity=10,
                product=ProductType.MIS
            )]
        elif rsi > self.overbought:
            return [OrderRequest(
                symbol=context.symbol,
                side=OrderSide.SELL,
                quantity=10,
                product=ProductType.MIS
            )]
        
        return None
```

### Pattern 2: Multi-Timeframe Strategy

```python
class MultiTimeframeStrategy(StrategyBase):
    """Strategy using multiple timeframes."""
    
    def __init__(self):
        super().__init__()
        self.daily_data: dict[str, list[MarketData]] = {}
        self.intraday_data: dict[str, list[MarketData]] = {}
    
    async def on_tick(self, context, tick):
        # Store intraday data
        if context.symbol not in self.intraday_data:
            self.intraday_data[context.symbol] = []
        self.intraday_data[context.symbol].append(tick)
        
        # Check daily signal
        daily_signal = self._check_daily_signal(context)
        if not daily_signal:
            return None
        
        # Check intraday signal
        intraday_signal = self._check_intraday_signal(context, tick)
        if not intraday_signal:
            return None
        
        # Generate orders if both signals align
        return self._generate_orders(context, daily_signal, intraday_signal)
```

### Pattern 3: Event-Driven Strategy

```python
class EventDrivenStrategy(StrategyBase):
    """Strategy that responds to specific events."""
    
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.events: dict[str, list] = {}
        
    async def on_market_open(self, context):
        """Subscribe to events at market open."""
        self.event_bus.subscribe(NewsEvent, self._on_news)
        self.event_bus.subscribe(EarningsEvent, self._on_earnings)
    
    async def _on_news(self, event: NewsEvent):
        """Handle news events."""
        if event.sentiment > 0.8:
            self.events[event.symbol].append('positive_news')
    
    async def _on_earnings(self, event: EarningsEvent):
        """Handle earnings events."""
        if event.surprise > 0.1:
            self.events[event.symbol].append('positive_earnings')
    
    async def on_tick(self, context, tick):
        """Check for triggered events."""
        if context.symbol in self.events and self.events[context.symbol]:
            return self._generate_orders(context, tick)
        return None
```

### Pattern 4: Risk-Aware Strategy

```python
class RiskAwareStrategy(StrategyBase):
    """Strategy with built-in risk management."""
    
    def __init__(
        self,
        max_positions: int = 5,
        max_exposure: Decimal = Decimal('0.80')
    ) -> None:
        super().__init__()
        self.max_positions = max_positions
        self.max_exposure = max_exposure
        self.current_positions: dict[str, int] = {}
    
    async def on_tick(self, context, tick):
        # Check position limits
        if len(self.current_positions) >= self.max_positions:
            return None
        
        # Calculate position size based on risk
        risk_amount = Decimal('10000')  # Risk per trade
        stop_loss_pct = Decimal('0.02')  # 2% stop loss
        quantity = int(risk_amount / (tick.close * stop_loss_pct))
        
        # Scale by selection rank
        quantity = self.scale_quantity_by_rank(quantity, context)
        
        return [OrderRequest(
            symbol=context.symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            product=ProductType.MIS
        )]
```

---

## Debugging Strategies

### 1. Enable Debug Logging

```python
import logging
logging.getLogger('iatb.strategies').setLevel(logging.DEBUG)
```

### 2. Print Strategy State

```python
async def on_tick(self, context, tick):
    logger.debug(
        "Strategy state",
        symbol=context.symbol,
        state=self.__dict__
    )
```

### 3. Use Strategy Assertions

```python
async def on_tick(self, context, tick):
    assert context.symbol == tick.symbol, "Symbol mismatch"
    assert tick.close > 0, "Invalid price"
    # ... rest of logic
```

### 4. Visualize Signals

```python
import matplotlib.pyplot as plt

def plot_signals(data, signals):
    """Plot price with buy/sell signals."""
    plt.figure(figsize=(12, 6))
    plt.plot(data['close'], label='Price')
    
    buy_signals = signals[signals['side'] == 'BUY']
    sell_signals = signals[signals['side'] == 'SELL']
    
    plt.scatter(
        buy_signals.index,
        buy_signals['price'],
        color='green',
        marker='^',
        label='Buy'
    )
    plt.scatter(
        sell_signals.index,
        sell_signals['price'],
        color='red',
        marker='v',
        label='Sell'
    )
    
    plt.legend()
    plt.show()
```

---

## Examples

### Example 1: Complete Strategy Implementation

```python
from iatb.strategies.base import StrategyBase, StrategyContext, MarketData
from iatb.execution.order_manager import OrderRequest
from iatb.core.enums import OrderSide, ProductType
from iatb.core.observability.logging_config import get_logger
from decimal import Decimal
from datetime import datetime, UTC

logger = get_logger(__name__)

class BollingerBandsStrategy(StrategyBase):
    """Bollinger Bands mean reversion strategy."""
    
    def __init__(
        self,
        period: int = 20,
        std_multiplier: Decimal = Decimal('2.0'),
        quantity: int = 10
    ) -> None:
        """Initialize Bollinger Bands strategy.
        
        Args:
            period: Period for moving average and std dev
            std_multiplier: Multiplier for standard deviation bands
            quantity: Base quantity for orders
        """
        super().__init__()
        self.period = period
        self.std_multiplier = std_multiplier
        self.quantity = quantity
        self.price_history: dict[str, list[Decimal]] = {}
        self.position_tracker: dict[str, str] = {}
    
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        """Process tick and generate orders."""
        symbol = context.symbol
        
        # Check if instrument is selected
        if not self.can_emit_signal(context):
            return None
        
        # Update price history
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(tick.close)
        
        # Need enough data for Bollinger Bands
        if len(self.price_history[symbol]) < self.period:
            return None
        
        # Calculate Bollinger Bands
        prices = self.price_history[symbol][-self.period:]
        sma = sum(prices) / len(prices)
        variance = sum((p - sma) ** 2 for p in prices) / len(prices)
        std = Decimal(str(variance.sqrt()))
        
        upper_band = sma + (std * self.std_multiplier)
        lower_band = sma - (std * self.std_multiplier)
        
        # Get current position
        current_position = self.position_tracker.get(symbol)
        
        # Generate signals
        orders = []
        
        # Buy if price crosses below lower band
        if tick.close <= lower_band and current_position != 'LONG':
            quantity = self.scale_quantity_by_rank(self.quantity, context)
            orders.append(OrderRequest(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                product=ProductType.MIS
            ))
            self.position_tracker[symbol] = 'LONG'
            logger.info(
                "Bollinger Bands BUY signal",
                symbol=symbol,
                price=str(tick.close),
                lower_band=str(lower_band),
                quantity=quantity
            )
        
        # Sell if price crosses above upper band
        elif tick.close >= upper_band and current_position == 'LONG':
            quantity = self.scale_quantity_by_rank(self.quantity, context)
            orders.append(OrderRequest(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                product=ProductType.MIS
            ))
            self.position_tracker[symbol] = None
            logger.info(
                "Bollinger Bands SELL signal",
                symbol=symbol,
                price=str(tick.close),
                upper_band=str(upper_band),
                quantity=quantity
            )
        
        return orders if orders else None
```

### Example 2: Ensemble Strategy

```python
class EnsembleStrategy(StrategyBase):
    """Combines multiple strategies."""
    
    def __init__(self, strategies: list[StrategyBase]) -> None:
        """Initialize ensemble strategy.
        
        Args:
            strategies: List of strategies to combine
        """
        super().__init__()
        self.strategies = strategies
    
    async def on_tick(
        self,
        context: StrategyContext,
        tick: MarketData
    ) -> list[OrderRequest] | None:
        """Get consensus from all strategies."""
        all_orders = []
        
        for strategy in self.strategies:
            orders = await strategy.on_tick(context, tick)
            if orders:
                all_orders.extend(orders)
        
        # Vote on direction
        if not all_orders:
            return None
        
        buy_count = sum(1 for o in all_orders if o.side == OrderSide.BUY)
        sell_count = sum(1 for o in all_orders if o.side == OrderSide.SELL)
        
        # Only execute if majority agrees
        if buy_count > sell_count:
            return [o for o in all_orders if o.side == OrderSide.BUY]
        elif sell_count > buy_count:
            return [o for o in all_orders if o.side == OrderSide.SELL]
        
        return None
```

---

## Next Steps

1. **Implement your strategy**: Follow the examples above
2. **Write comprehensive tests**: Cover all scenarios
3. **Backtest thoroughly**: Use multiple validation methods
4. **Paper trade first**: Validate in live market without risk
5. **Monitor performance**: Track metrics and adjust parameters
6. **Iterate and improve**: Continuously refine your strategy

## Additional Resources

- [API Reference](API_REFERENCE.md)
- [Architecture Documentation](ARCHITECTURE.md)
- [Backtesting Guide](../README.md#backtesting)
- [Risk Management](../README.md#safety-infrastructure)