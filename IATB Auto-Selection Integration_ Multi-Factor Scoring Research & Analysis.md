# IATB Auto-Selection Integration: Multi-Factor Scoring Research & Analysis
## 1. Problem Statement
IATB has four individually strong subsystems — **Sentiment**, **Market Strength**, **Volume Profile**, and **DRL/RL Backtesting** — but no orchestrating layer that fuses their outputs into a single, ranked instrument selection score. The auto-selection feature currently relies only on the `StrengthScorer.is_tradable()` binary gate. The goal is to create a unified `InstrumentSelector` that produces a continuous composite score per instrument, enabling ranked selection prior to trade execution.
## 2. Current State — Critical Review of Existing Components
### 2.1 Sentiment Subsystem (`sentiment/`)
**What exists:**
* `SentimentAggregator`: Weighted ensemble of FinBERT (0.50), AION (0.30), VADER (0.20) → composite score ∈ [-1, 1] with confidence ∈ [0, 1]
* `SentimentGateResult`: Binary `tradable` gate requiring `VERY_STRONG` (|score| ≥ 0.75) AND volume confirmation (ratio ≥ 1.5)
* `SentimentDrivenStrategy`: Uses gate result to emit directional signals
**Strengths:** Decimal-safe, multi-source, volume-confirmed. Well-tested architecture.
**Gaps for auto-selection:**
* Output is binary (tradable/not) — no granular ranking across instruments
* No temporal decay: a 4-hour-old sentiment score is treated identically to a 5-minute-old one
* No cross-instrument relative scoring (instrument A sentiment vs B)
* Missing news recency weighting and event-type classification (earnings vs rumor vs macro)
### 2.2 Market Strength Subsystem (`market_strength/`)
**What exists:**
* `StrengthScorer`: Composite score ∈ [0, 1] from breadth (0.25), ADX/trend (0.25), volume ratio (0.20), regime (0.30) minus volatility penalty
* `RegimeDetector`: HMM 3-state (BULL/BEAR/SIDEWAYS) with confidence
* `PandasTaIndicators`: RSI, ADX, ATR, MACD, Bollinger snapshot
* `breadth.py`: Advance/decline ratio, McClellan oscillator
* Per-exchange minimum thresholds (NSE 0.60, BINANCE 0.65, etc.)
**Strengths:** Exchange-aware thresholds, regime-gated bear market block, volatility penalty.
**Gaps for auto-selection:**
* Score is only used as a boolean `is_tradable()` gate — the continuous 0..1 value is discarded
* No ADX trend-quality differentiation (ADX 25 vs ADX 45 treated linearly, no acceleration)
* Missing sector-relative strength (instrument vs peers)
* Regime confidence not propagated into score weighting
### 2.3 Volume Profile Subsystem (`market_strength/volume_profile.py`)
**What exists:**
* `build_volume_profile()`: Computes POC, VAH, VAL from price/volume sequences with configurable value area (default 70%)
* Pure `Decimal` math, validated inputs
**Strengths:** Correct POC/VAH/VAL logic, Decimal-safe.
**Gaps for auto-selection:**
* Completely isolated — not consumed by any strategy or scoring module
* No derived metrics: distance-to-POC, value area width ratio, HVN/LVN detection
* No time-weighted profile (recent sessions weighted more)
* Missing profile shape classification (P-shape bullish, b-shape bearish, D-shape balanced)
* No multi-timeframe profile synthesis (intraday + weekly)
### 2.4 DRL/RL Subsystem (`rl/`)
**What exists:**
* `RLAgent`: SB3 wrapper for PPO/A2C/SAC with versioned model save/load
* `TradingEnvironment`: Discrete(3) action space, session-aware, IST auto-square-off, Indian transaction costs
* `RLParameterOptimizer`: Optuna TPE search over integer hyperparams
* `reward.py`: PnL, Sharpe, Sortino reward functions
* `callbacks.py`: Early stopping on Sharpe drop, TensorBoard, checkpointing
**Strengths:** Deterministic seed, session masks, real Indian cost modeling, early stop.
**Gaps for auto-selection:**
* Training output is a model artifact — no structured "conclusion" or backtest verdict is emitted
* No standardized `BacktestConclusion` dataclass that captures Sharpe, drawdown, win rate, robustness flag
* Walk-forward results (`WalkForwardResult.overfitting_detected`) and Monte Carlo robustness (`MonteCarloResult.robust`) are not wired to instrument scoring
* Agent predict() returns action (0/1/2) — no continuous confidence measure for instrument ranking
* No per-instrument DRL model registry or comparison framework
### 2.5 Backtesting Subsystem (`backtesting/`)
**What exists:**
* `EventDrivenBacktester`, `VectorizedBacktester`, `WalkForwardOptimizer`, `MonteCarloAnalyzer`
* `QuantStatsReporter` for HTML report generation
* Walk-forward overfitting detection (ratio > 2.0 flags overfit)
**Strengths:** Four complementary backtesting paradigms, overfitting detection.
**Gaps for auto-selection:**
* Results exist as standalone return values — no pipeline feeding them into a selection score
* No standardized `InstrumentBacktestSummary` that aggregates all four paradigms into one verdict
### 2.6 Strategy Layer (`strategies/`)
**What exists:**
* `StrategyBase` with `can_emit_signal()` → `is_tradable()` (boolean gate)
* `EnsembleStrategy`: Weighted directional voting across signals
* Momentum, Breakout, MeanReversion, SentimentDriven — each with own input dataclass
**Gap:** Ensemble voting happens across **strategies** for a single instrument but never across **instruments** to select which ones to trade.
## 3. Industry Best Practices — Web Research Synthesis
### 3.1 Multi-Factor Scoring Unification
**Academic & Industry Standard (FinClaw, BlackRock Factor Models, CAFPO):**
All heterogeneous signals (technical, sentiment, DRL, volume) should be normalized to a common scale [0, 1] and combined via weighted ensemble. Industry practice:
* **Normalization**: Z-score or min-max per factor, then sigmoid squash to [0, 1]
* **Weight assignment**: Static initial weights tuned via walk-forward optimization; or adaptive weights via Bayesian optimization / genetic algorithms
* **Design principle (FinClaw)**: "Technical, sentiment, DRL, fundamental — all signals are unified as factors returning [0, 1]. Weights are determined by the evolution engine, eliminating human bias from signal synthesis."
### 3.2 Regime-Aware Signal Gating
**Research finding (arXiv 2402.01441, Ray Islam pipeline):**
Dynamic sentiment-based switching of ensemble agent weights outperforms fixed-interval rebalancing. The regime should modulate which factors dominate:
* **BULL regime**: Momentum weight ↑, mean-reversion weight ↓, sentiment weight baseline
* **SIDEWAYS regime**: Mean-reversion weight ↑, volume profile weight ↑, momentum weight ↓
* **BEAR regime**: Defensive — only trade if DRL confidence high AND sentiment strongly positive (contrarian)
### 3.3 Volume Profile as Selection Signal
**Industry consensus (CME institutional traders, AVPT methodology):**
* **POC distance score**: Instruments trading near POC = mean-reversion opportunities; far from POC = trending opportunities
* **Value Area width**: Narrow VA = low disagreement = trending opportunity; Wide VA = balanced/range-bound
* **Profile shape**: P-shape (bullish accumulation), b-shape (bearish distribution), D-shape (balanced) — directly maps to directional bias
* **LVN traversal**: Instruments approaching LVN zones have acceleration potential (low resistance)
* **HVN clustering**: Multiple HVN stacking = ultra-strong institutional support/resistance
* **Best practice**: Volume profile is not a standalone signal — it should be a **quality multiplier** that amplifies/dampens other signals
### 3.4 DRL Backtesting Integration
**Research finding (CAFPO - Georgetown, Increase Alpha, DRL-MultiFactorTrading):**
* DRL should output **continuous portfolio weights** or **confidence scores**, not just discrete actions
* Factor-based DRL with conditional autoencoders (CAFPO) significantly outperforms vanilla DRL by compressing 94 firm characteristics into latent factors
* **Walk-forward + Monte Carlo validation is mandatory** before DRL conclusions influence live selection
* Key DRL-derived metrics for selection: out-of-sample Sharpe, overfitting ratio, reward stability
* **Meta-learning (MAML)**: Fast adaptation to regime changes (<5 min vs >24h manual recalibration)
### 3.5 Anti-Overfitting Best Practices
* Walk-forward with embargo period (prevent information leakage)
* Monte Carlo permutation testing (is strategy better than random?)
* Multiple testing correction (Bonferroni/BH when scanning multiple instruments)
* Alpha decay monitoring with retraining alerts
* Combinatorial Purged Cross-Validation (CPCV) for DRL model validation
## 4. Proposed Architecture — Instrument Auto-Selection Fusion
### 4.1 New Module: `src/iatb/selection/`
```warp-runnable-command
selection/
├── __init__.py
├── instrument_scorer.py      # InstrumentScorer: fuses all four signals
├── sentiment_signal.py        # Normalizes SentimentAggregator → [0, 1]
├── strength_signal.py         # Extracts continuous StrengthScorer value
├── volume_profile_signal.py   # Derives POC-distance, VA-width, shape scores
├── drl_signal.py              # Extracts DRL backtest conclusion metrics
├── composite_score.py         # Weighted fusion with regime-aware gating
├── ranking.py                 # Ranks instruments, applies top-N selection
└── decay.py                   # Temporal decay for stale signals
```
### 4.2 Signal Normalization Contract
Each signal module must implement:
```python
@dataclass(frozen=True)
class NormalizedSignal:
    instrument_symbol: str
    exchange: Exchange
    signal_name: str            # e.g. "sentiment", "strength", "volume_profile", "drl"
    score: Decimal              # [0, 1] — 0 = worst, 1 = best
    confidence: Decimal          # [0, 1] — signal reliability
    timestamp_utc: datetime
    metadata: dict[str, str]
```
### 4.3 Component Scoring Formulas
**Sentiment Score** (normalize from [-1, 1] to [0, 1]):
`sentiment_norm = (composite_score + 1) / 2` weighted by `confidence × recency_decay`
**Market Strength Score** (already [0, 1]):
`strength_norm = StrengthScorer.score()` weighted by `regime_confidence`
**Volume Profile Score** (composite of sub-metrics):
* `poc_proximity = 1 - abs(current_price - poc) / (vah - val)` clamped [0, 1]
* `va_width_ratio = 1 - ((vah - val) / current_price)` (narrower = stronger trend)
* `shape_score = {P: 0.8, D: 0.5, b: 0.2}` for bullish bias; inverted for bearish
* Combined: `volume_profile_score = 0.40 × poc_proximity + 0.35 × va_width_ratio + 0.25 × shape_score`
**DRL Backtest Conclusion Score**:
* `sharpe_norm = sigmoid(out_of_sample_sharpe)` [0, 1]
* `robustness_flag = 1.0 if monte_carlo.robust else 0.3`
* `overfit_penalty = 0.0 if not walk_forward.overfitting_detected else -0.4`
* Combined: `drl_score = sharpe_norm × robustness_flag + overfit_penalty` clamped [0, 1]
### 4.4 Composite Score with Regime-Aware Weights
```warp-runnable-command
composite = (w_sentiment × sentiment_norm × confidence_sentiment)
          + (w_strength × strength_norm × regime_confidence)
          + (w_volume   × volume_profile_score)
          + (w_drl      × drl_score)
```
Regime-dependent weight presets:
* BULL:     sentiment=0.20, strength=0.25, volume=0.15, drl=0.40
* SIDEWAYS: sentiment=0.15, strength=0.20, volume=0.35, drl=0.30
* BEAR:     sentiment=0.30, strength=0.30, volume=0.10, drl=0.30
Rationale: In BULL markets, DRL momentum conclusions dominate. In SIDEWAYS markets, volume profile structure provides the strongest edge. In BEAR markets, sentiment contrarian signals and market strength defense are critical.
### 4.5 Ranking & Selection
1. Compute composite score for all candidate instruments
2. Apply minimum threshold (e.g., composite ≥ 0.55)
3. Rank descending
4. Select top-N (configurable, e.g., 5)
5. Feed selected instruments + scores to `EnsembleStrategy` or individual strategies
## 5. Additional Optimizing Features Identified
### 5.1 Temporal Decay Function
Signals degrade over time. A sentiment score from 6 hours ago is less reliable:
`decay_factor = exp(-λ × hours_elapsed)` where λ is signal-specific (sentiment decays faster than DRL conclusion).
### 5.2 Cross-Instrument Relative Ranking
Normalize each signal **across the instrument universe** (not just per-instrument), so the score reflects relative standing among all candidates.
### 5.3 Correlation-Aware Diversification Filter
After top-N selection, check pairwise correlation of selected instruments. If correlation > 0.80, drop the lower-scored instrument to avoid concentrated exposure.
### 5.4 Alpha Decay Monitoring
Track selection score prediction accuracy over time. If the composite score's predictive power for 5-day forward returns drops below threshold, trigger retraining alert.
### 5.5 Profile Shape Migration Tracking
Track profile shape transitions (b→D→P) across sessions as leading indicator of trend reversals.
### 5.6 DRL Action Probability as Confidence
Instead of just the argmax action, extract the softmax probability distribution from the DRL policy network as a continuous confidence measure (PPO policy outputs logits → softmax → probability of BUY action as confidence).
### 5.7 Multi-Timeframe Signal Alignment
Compute each signal on multiple timeframes (5min, 1h, daily) and require alignment (e.g., all three bullish) as a quality multiplier.
## 6. Risk Considerations
* **Overfitting the selector itself**: The composite weights are hyperparameters. Must be validated via walk-forward on the selection pipeline, not just individual signals
* **Survivorship bias**: If DRL was trained on instruments that existed throughout the training period, new/delisted instruments will have stale or missing DRL scores
* **Latency**: Sentiment analysis (FinBERT) and DRL inference have non-trivial compute cost. Selection pipeline must complete within market-hours latency budget
* **Indian market specifics**: NSE/MCX instruments have circuit limits, lot size constraints, and SEBI margin rules that may override selection scores (fail-closed)
* **Decimal precision**: All scores must remain in `Decimal` throughout the pipeline (IATB project rule)
## 7. Comprehensive Final Remarks
### Assessment
The IATB project has **strong foundational components** across all four dimensions. The sentiment ensemble, market strength scorer, volume profile calculator, and DRL agent are each well-architected with Decimal-safe math, proper validation, and fail-closed design. The critical gap is the **absence of an integration layer** that fuses these signals into a unified instrument selection mechanism.
### Key Recommendations
1. **Create `selection/` module** with `InstrumentScorer` as the central orchestrator. All four signal sources normalize to `NormalizedSignal` contract.
2. **Promote `StrengthScorer.score()` from binary gate to continuous input**. The 0..1 value already exists — it is just unused past the boolean threshold.
3. **Wire Volume Profile into the scoring pipeline**. Derive POC-distance, VA-width, and profile shape as structured metrics. This is the **largest existing gap** — the module exists but feeds nothing.
4. **Create `BacktestConclusion` dataclass** that captures Sharpe, drawdown, Monte Carlo robustness flag, and walk-forward overfitting flag from the backtesting suite. Feed this into DRL signal scoring.
5. **Implement regime-aware weight switching** using the existing `RegimeDetector`. The infrastructure exists — only the weight modulation logic is missing.
6. **Add temporal decay** to prevent stale signals from influencing selection. Critical for sentiment (fast decay) and volume profile (medium decay).
7. **Walk-forward validate the composite scorer itself** — treat the selection pipeline as a model and test it for overfitting.
### Implementation Priority
* **P0 (Immediate)**: Wire existing `StrengthScorer.score()` + `SentimentAggregator.analyze()` into a basic 2-signal composite scorer
* **P1 (Week 1)**: Add volume profile signal derivation (POC-distance, VA-width, shape)
* **P2 (Week 2)**: Create `BacktestConclusion` dataclass and wire DRL/backtesting results
* **P3 (Week 3)**: Regime-aware weight switching + temporal decay + cross-instrument relative ranking
* **P4 (Week 4)**: Walk-forward validation of composite scorer + correlation-aware diversification filter
### Approval Gate
This plan requires approval before implementation begins. The composite scoring weights, regime presets, and threshold values should be reviewed and agreed upon before coding commences.