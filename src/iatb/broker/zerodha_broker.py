"""
Zerodha broker implementation using KiteConnect.

This module provides a concrete implementation of the BrokerInterface
for Zerodha's KiteConnect API, with integrated token management,
rate limiting, and retry logic.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from iatb.broker.base import (
    BrokerInterface,
    Exchange,
    Margin,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    TransactionType,
)
from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.exceptions import ConfigError
from iatb.data.rate_limiter import CircuitBreaker, RateLimiter, RetryConfig, retry_with_backoff

_LOGGER = logging.getLogger(__name__)


class ZerodhaBroker(BrokerInterface):
    """Zerodha broker implementation with KiteConnect.

    This class implements the BrokerInterface protocol for Zerodha,
    providing:
    - Token management through ZerodhaTokenManager
    - Rate limiting to respect API limits
    - Retry logic with exponential backoff
    - Circuit breaker for resilience

    Example:
        token_manager = ZerodhaTokenManager(
            api_key="...",
            api_secret="...",
            totp_secret="..."
        )
        broker = ZerodhaBroker(token_manager=token_manager)
        await broker.authenticate()

        # Place an order
        order = await broker.place_order(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10
        )
    """

    def __init__(
        self,
        *,
        token_manager: ZerodhaTokenManager,
        rate_limiter: RateLimiter | None = None,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """Initialize Zerodha broker.

        Args:
            token_manager: Zerodha token manager instance.
            rate_limiter: Optional rate limiter (defaults to 3 req/s, burst 10).
            retry_config: Optional retry configuration.
            circuit_breaker: Optional circuit breaker.

        Raises:
            ValueError: If token_manager is None.
        """
        if not token_manager:
            msg = "token_manager is required"
            raise ValueError(msg)

        self._token_manager = token_manager
        self._rate_limiter = rate_limiter or RateLimiter(
            requests_per_second=3.0,
            burst_capacity=10,
        )
        self._retry_config = retry_config or RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            backoff_multiplier=2.0,
            jitter_seconds=0.5,
        )
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=5,
            reset_timeout=60.0,
            name="zerodha_broker",
        )
        self._client: Any = None
        self._authenticated = False

    async def authenticate(self) -> None:
        """Authenticate with Zerodha using stored token.

        Raises:
            ConfigError: If authentication fails.
        """
        if self._authenticated and self._client:
            _LOGGER.debug("Already authenticated")
            return

        access_token = self._token_manager.get_access_token()
        if not access_token:
            msg = "No access token available. Please authenticate first."
            raise ConfigError(msg)

        self._client = await self._execute_with_retry(
            lambda: self._token_manager.get_kite_client(access_token=access_token)
        )
        self._authenticated = True
        _LOGGER.info("Successfully authenticated with Zerodha")

    async def _ensure_authenticated(self) -> None:
        """Ensure broker is authenticated."""
        if not self._authenticated or not self._client:
            await self.authenticate()

    async def _execute_with_retry(
        self,
        func: Any,
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Execute function with rate limiting and retry logic.

        Args:
            func: Function to execute.
            **kwargs: Arguments to pass to function.

        Returns:
            Result of function execution.

        Raises:
            ConfigError: If all retries exhausted.
        """
        return await self._rate_limiter.execute(
            retry_with_backoff(
                func,
                config=self._retry_config,
                circuit_breaker=self._circuit_breaker,
                **kwargs,
            )
        )

    @staticmethod
    def _parse_exchange(exchange: Exchange) -> str:
        """Convert Exchange enum to KiteConnect format.

        Args:
            exchange: Exchange enum value.

        Returns:
            KiteConnect exchange string.
        """
        exchange_map = {
            Exchange.NSE: "NSE",
            Exchange.BSE: "BSE",
            Exchange.NFO: "NFO",
            Exchange.BFO: "BFO",
            Exchange.MCX: "MCX",
        }
        return exchange_map.get(exchange, exchange.value)

    @staticmethod
    def _parse_order_type(order_type: OrderType) -> str:
        """Convert OrderType enum to KiteConnect format.

        Args:
            order_type: OrderType enum value.

        Returns:
            KiteConnect order type string.
        """
        type_map = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_LOSS: "SL",
            OrderType.STOP_LOSS_MARKET: "SL-M",
        }
        return type_map.get(order_type, order_type.value)

    @staticmethod
    def _parse_transaction_type(transaction_type: TransactionType) -> str:
        """Convert TransactionType enum to KiteConnect format.

        Args:
            transaction_type: TransactionType enum value.

        Returns:
            KiteConnect transaction type string.
        """
        return transaction_type.value

    @staticmethod
    def _parse_product_type(product_type: ProductType) -> str:
        """Convert ProductType enum to KiteConnect format.

        Args:
            product_type: ProductType enum value.

        Returns:
            KiteConnect product type string.
        """
        return product_type.value

    @staticmethod
    def _parse_order_status(status: str) -> OrderStatus:
        """Convert KiteConnect status to OrderStatus enum.

        Args:
            status: KiteConnect status string.

        Returns:
            OrderStatus enum value.
        """
        status_map = {
            "PUT ORDER REQ RECEIVED": OrderStatus.PENDING,
            "VALIDATION PENDING": OrderStatus.VALIDATION_PENDING,
            "OPEN": OrderStatus.OPEN,
            "TRIGGER PENDING": OrderStatus.TRIGGER_PENDING,
            "COMPLETE": OrderStatus.COMPLETE,
            "REJECTED": OrderStatus.REJECTED,
            "CANCELLED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        return status_map.get(status, OrderStatus.PENDING)

    @staticmethod
    def _parse_exchange_from_str(exchange_str: str) -> Exchange:
        """Convert KiteConnect exchange string to Exchange enum.

        Args:
            exchange_str: KiteConnect exchange string.

        Returns:
            Exchange enum value.
        """
        exchange_map = {
            "NSE": Exchange.NSE,
            "BSE": Exchange.BSE,
            "NFO": Exchange.NFO,
            "BFO": Exchange.BFO,
            "MCX": Exchange.MCX,
        }
        return exchange_map.get(exchange_str, Exchange.NSE)

    @staticmethod
    def _parse_order_type_from_str(order_type_str: str) -> OrderType:
        """Convert KiteConnect order type string to OrderType enum.

        Args:
            order_type_str: KiteConnect order type string.

        Returns:
            OrderType enum value.
        """
        type_map = {
            "MARKET": OrderType.MARKET,
            "LIMIT": OrderType.LIMIT,
            "SL": OrderType.STOP_LOSS,
            "SL-M": OrderType.STOP_LOSS_MARKET,
        }
        return type_map.get(order_type_str, OrderType.LIMIT)

    @staticmethod
    def _parse_transaction_type_from_str(trans_type_str: str) -> TransactionType:
        """Convert KiteConnect transaction type string to TransactionType enum.

        Args:
            trans_type_str: KiteConnect transaction type string.

        Returns:
            TransactionType enum value.
        """
        return TransactionType(trans_type_str)

    @staticmethod
    def _parse_product_type_from_str(product_str: str) -> ProductType:
        """Convert KiteConnect product type string to ProductType enum.

        Args:
            product_str: KiteConnect product type string.

        Returns:
            ProductType enum value.
        """
        product_map = {
            "MIS": ProductType.INTRADAY,
            "CNC": ProductType.DELIVERY,
            "NRML": ProductType.NRML,
            "BO": ProductType.BO,
            "CO": ProductType.CO,
        }
        return product_map.get(product_str, ProductType.INTRADAY)

    def _validate_order_params(
        self,
        order_type: OrderType,
        price: Decimal | None,
        trigger_price: Decimal | None,
        quantity: int,
    ) -> None:
        """Validate order parameters.

        Args:
            order_type: Type of order.
            price: Limit price.
            trigger_price: Trigger price.
            quantity: Number of shares/contracts.

        Raises:
            ValueError: If parameters are invalid.
        """
        if order_type == OrderType.LIMIT and price is None:
            msg = "price is required for LIMIT orders"
            raise ValueError(msg)
        if (
            order_type in (OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET)
            and trigger_price is None
        ):
            msg = "trigger_price is required for STOP_LOSS orders"
            raise ValueError(msg)
        if quantity <= 0:
            msg = "quantity must be positive"
            raise ValueError(msg)

    def _build_order_params(
        self,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        product_type: ProductType,
    ) -> dict[str, Any]:
        """Build order parameters dictionary.

        Args:
            symbol: Trading symbol.
            exchange: Exchange.
            transaction_type: BUY or SELL.
            order_type: Type of order.
            quantity: Number of shares.
            price: Limit price.
            trigger_price: Trigger price.
            product_type: Product type.

        Returns:
            Order parameters dictionary.
        """
        order_params = {
            "exchange": self._parse_exchange(exchange),
            "tradingsymbol": symbol,
            "transaction_type": self._parse_transaction_type(transaction_type),
            "quantity": quantity,
            "order_type": self._parse_order_type(order_type),
            "product": self._parse_product_type(product_type),
        }

        if price is not None:
            # API boundary: KiteConnect requires float, convert from Decimal
            order_params["price"] = float(price)
        if trigger_price is not None:
            # API boundary: KiteConnect requires float, convert from Decimal
            order_params["trigger_price"] = float(trigger_price)

        return order_params

    def _create_order_response(
        self,
        order_id: str,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        product_type: ProductType,
    ) -> Order:
        """Create Order object from parameters.

        Args:
            order_id: Order ID.
            symbol: Trading symbol.
            exchange: Exchange.
            transaction_type: BUY or SELL.
            order_type: Type of order.
            quantity: Number of shares.
            price: Limit price.
            trigger_price: Trigger price.
            product_type: Product type.

        Returns:
            Order object.
        """
        return Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            status=OrderStatus.PENDING,
            product_type=product_type,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            average_price=None,
        )

    async def place_order(  # noqa: D401
        self,
        *,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
    ) -> Order:
        """Place a new order with Zerodha."""
        await self._ensure_authenticated()
        order_params = self._prepare_order_params(
            symbol,
            exchange,
            transaction_type,
            order_type,
            quantity,
            price,
            trigger_price,
            product_type,
        )
        return await self._complete_order_placement(
            order_params,
            symbol,
            exchange,
            transaction_type,
            order_type,
            quantity,
            price,
            trigger_price,
            product_type,
        )

    async def _complete_order_placement(
        self,
        order_params: dict[str, Any],
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        product_type: ProductType,
    ) -> Order:
        """Complete order placement and build result.

        Args:
            order_params: Order parameters dictionary.
            symbol: Trading symbol.
            exchange: Exchange.
            transaction_type: BUY or SELL.
            order_type: Type of order.
            quantity: Number of shares.
            price: Limit price.
            trigger_price: Trigger price.
            product_type: Product type.

        Returns:
            Order object.

        Raises:
            RuntimeError: If order placement fails.
        """
        response = await self._execute_place_order(order_params)
        return self._build_order_result(
            str(response["order_id"]),
            symbol,
            exchange,
            transaction_type,
            order_type,
            quantity,
            price,
            trigger_price,
            product_type,
        )

    def _prepare_order_params(
        self,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        product_type: ProductType,
    ) -> dict[str, Any]:
        """Validate and build order parameters.

        Args:
            symbol: Trading symbol.
            exchange: Exchange.
            transaction_type: BUY or SELL.
            order_type: Type of order.
            quantity: Number of shares.
            price: Limit price.
            trigger_price: Trigger price.
            product_type: Product type.

        Returns:
            Order parameters dictionary.

        Raises:
            ValueError: If parameters are invalid.
        """
        self._validate_order_params(order_type, price, trigger_price, quantity)
        return self._build_order_params(
            symbol,
            exchange,
            transaction_type,
            order_type,
            quantity,
            price,
            trigger_price,
            product_type,
        )

    def _build_order_result(
        self,
        order_id: str,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        product_type: ProductType,
    ) -> Order:
        """Build order result from placement response.

        Args:
            order_id: Order ID from response.
            symbol: Trading symbol.
            exchange: Exchange.
            transaction_type: BUY or SELL.
            order_type: Type of order.
            quantity: Number of shares.
            price: Limit price.
            trigger_price: Trigger price.
            product_type: Product type.

        Returns:
            Order object.
        """
        return self._create_order_response(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            product_type=product_type,
        )

    async def _execute_place_order(self, order_params: dict[str, Any]) -> Mapping[str, Any]:
        """Execute order placement with retry logic.

        Args:
            order_params: Order parameters dictionary.

        Returns:
            Order placement response.

        Raises:
            RuntimeError: If order placement fails.
        """

        async def _place() -> Mapping[str, Any]:
            result = self._client.place_order(**order_params)
            if not result or "order_id" not in result:
                msg = f"Failed to place order: {result}"
                raise RuntimeError(msg)
            return result  # type: ignore[no-any-return]

        return await self._execute_with_retry(_place)  # type: ignore[no-any-return]

    async def _find_order_by_id(self, order_id: str) -> Order:
        """Find order by ID from current orders.

        Args:
            order_id: Order ID to find.

        Returns:
            Order object.

        Raises:
            RuntimeError: If order not found.
        """
        orders = await self.get_orders()
        order = next((o for o in orders if o.order_id == order_id), None)
        if not order:
            msg = f"Order {order_id} not found"
            raise RuntimeError(msg)
        return order

    async def cancel_order(self, *, order_id: str) -> Order:
        """Cancel an existing order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            Updated order object with CANCELLED status.

        Raises:
            ValueError: If order_id is invalid.
            RuntimeError: If cancellation fails.
        """
        await self._ensure_authenticated()

        if not order_id:
            msg = "order_id is required"
            raise ValueError(msg)

        async def _cancel() -> Mapping[str, Any]:
            result = self._client.cancel_order(order_id=order_id)
            if not result or "order_id" not in result:
                msg = f"Failed to cancel order: {result}"
                raise RuntimeError(msg)
            return result  # type: ignore[no-any-return]

        await self._execute_with_retry(_cancel)
        return await self._find_order_by_id(order_id)

    async def get_positions(self) -> list[Position]:
        """Get current positions.

        Returns:
            List of current positions.

        Raises:
            RuntimeError: If fetching positions fails.
        """
        await self._ensure_authenticated()

        async def _get_positions() -> Mapping[str, Any]:
            return self._client.positions()  # type: ignore[no-any-return]

        response: Mapping[str, Any] = await self._execute_with_retry(_get_positions)

        positions: list[Position] = []
        for pos in response.get("day", []):
            if pos["quantity"] == 0:
                continue
            positions.append(
                Position(
                    symbol=pos["tradingsymbol"],
                    exchange=self._parse_exchange_from_str(pos["exchange"]),
                    product_type=self._parse_product_type_from_str(pos["product"]),
                    quantity=int(pos["quantity"]),
                    average_price=Decimal(str(pos["average_price"])),
                    last_price=Decimal(str(pos["last_price"])),
                    pnl=Decimal(str(pos["pnl"])),
                    day_change=Decimal(str(pos["day_change"])),
                )
            )

        return positions

    async def get_orders(self) -> list[Order]:
        """Get all orders.

        Returns:
            List of all orders.

        Raises:
            RuntimeError: If fetching orders fails.
        """
        await self._ensure_authenticated()

        async def _get_orders() -> list[Mapping[str, Any]]:
            return self._client.orders()  # type: ignore[no-any-return]

        response: list[Mapping[str, Any]] = await self._execute_with_retry(_get_orders)

        orders: list[Order] = []
        for order_data in response:
            orders.append(
                Order(
                    order_id=str(order_data["order_id"]),
                    symbol=order_data["tradingsymbol"],
                    exchange=self._parse_exchange_from_str(order_data["exchange"]),
                    transaction_type=self._parse_transaction_type_from_str(
                        order_data["transaction_type"]
                    ),
                    order_type=self._parse_order_type_from_str(order_data["order_type"]),
                    quantity=int(order_data["quantity"]),
                    price=Decimal(str(order_data["price"])) if order_data["price"] else None,
                    trigger_price=Decimal(str(order_data["trigger_price"]))
                    if order_data["trigger_price"]
                    else None,
                    status=self._parse_order_status(order_data["status"]),
                    product_type=self._parse_product_type_from_str(order_data["product"]),
                    timestamp=datetime.fromisoformat(order_data["order_timestamp"]),
                    filled_quantity=int(order_data["filled_quantity"]),
                    average_price=Decimal(str(order_data["average_price"]))
                    if order_data["average_price"]
                    else None,
                )
            )

        return orders

    async def get_margins(self) -> Margin:
        """Get margin details.

        Returns:
            Margin details object.

        Raises:
            RuntimeError: If fetching margins fails.
        """
        await self._ensure_authenticated()

        async def _get_margins() -> Mapping[str, Any]:
            return self._client.margins()  # type: ignore[no-any-return]

        response: Mapping[str, Any] = await self._execute_with_retry(_get_margins)

        equity_data = response.get("equity", {})

        return Margin(
            available_cash=Decimal(str(equity_data.get("available", {}).get("cash", 0))),
            used_margin=Decimal(str(equity_data.get("used", {}).get("margin", 0))),
            available_margin=Decimal(str(equity_data.get("available", {}).get("live_balance", 0))),
            opening_balance=Decimal(str(equity_data.get("net", 0))),
        )

    async def get_order_history(
        self, *, order_id: str, from_date: date | None = None, to_date: date | None = None
    ) -> list[Mapping[str, Any]]:
        """Get order history for a specific order.

        Args:
            order_id: Order ID to fetch history for.
            from_date: Optional start date for filtering.
            to_date: Optional end date for filtering.

        Returns:
            List of order history entries.

        Raises:
            ValueError: If order_id is invalid.
            RuntimeError: If fetching history fails.
        """
        await self._ensure_authenticated()

        if not order_id:
            msg = "order_id is required"
            raise ValueError(msg)

        async def _get_history() -> list[Mapping[str, Any]]:
            history = self._client.order_history(order_id=order_id)
            if isinstance(history, list):
                return history
            return [history]

        result = await self._execute_with_retry(_get_history)
        if not isinstance(result, list):
            msg = f"Expected list from order_history, got {type(result)}"
            raise RuntimeError(msg)
        return result

    async def get_holdings(self) -> list[Mapping[str, Any]]:
        """Get holdings for delivery-based positions.

        Returns:
            List of holdings.

        Raises:
            RuntimeError: If fetching holdings fails.
        """
        await self._ensure_authenticated()

        async def _get_holdings() -> list[Mapping[str, Any]]:
            holdings = self._client.holdings()
            if isinstance(holdings, list):
                return holdings
            return [holdings]

        result = await self._execute_with_retry(_get_holdings)
        if not isinstance(result, list):
            msg = f"Expected list from holdings, got {type(result)}"
            raise RuntimeError(msg)
        return result

    def _build_modify_params(
        self,
        order_id: str,
        quantity: int | None,
        price: Decimal | None,
        order_type: OrderType | None,
        trigger_price: Decimal | None,
        disclosed_quantity: int | None,
    ) -> dict[str, Any]:
        """Build modify order parameters dictionary.

        Args:
            order_id: Order ID to modify.
            quantity: New quantity.
            price: New price.
            order_type: New order type.
            trigger_price: New trigger price.
            disclosed_quantity: New disclosed quantity.

        Returns:
            Modify parameters dictionary.

        Raises:
            ValueError: If quantity is invalid.
        """
        modify_params: dict[str, Any] = {"order_id": order_id}

        if quantity is not None:
            if quantity <= 0:
                msg = "quantity must be positive"
                raise ValueError(msg)
            modify_params["quantity"] = quantity
        if price is not None:
            # API boundary: KiteConnect requires float, convert from Decimal
            modify_params["price"] = float(price)
        if order_type is not None:
            modify_params["order_type"] = self._parse_order_type(order_type)
        if trigger_price is not None:
            # API boundary: KiteConnect requires float, convert from Decimal
            modify_params["trigger_price"] = float(trigger_price)
        if disclosed_quantity is not None:
            modify_params["disclosed_quantity"] = disclosed_quantity

        return modify_params

    async def modify_order(
        self,
        *,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        trigger_price: Decimal | None = None,
        disclosed_quantity: int | None = None,
    ) -> Order:
        """Modify an existing order.

        Args:
            order_id: Order ID to modify.
            quantity: New quantity (optional).
            price: New price (optional).
            order_type: New order type (optional).
            trigger_price: New trigger price (optional).
            disclosed_quantity: New disclosed quantity (optional).

        Returns:
            Updated order object.

        Raises:
            ValueError: If parameters are invalid or order cannot be modified.
            RuntimeError: If modification fails.
        """
        await self._ensure_authenticated()

        if not order_id:
            msg = "order_id is required"
            raise ValueError(msg)

        modify_params = self._build_modify_params(
            order_id, quantity, price, order_type, trigger_price, disclosed_quantity
        )

        async def _modify() -> Mapping[str, Any]:
            result = self._client.modify_order(**modify_params)
            if not result or "order_id" not in result:
                msg = f"Failed to modify order: {result}"
                raise RuntimeError(msg)
            return result  # type: ignore[no-any-return]

        await self._execute_with_retry(_modify)
        return await self._find_order_by_id(order_id)

    async def get_quote(self, *, symbol: str, exchange: Exchange) -> Mapping[str, Any]:
        """Get current quote for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange where symbol is traded.

        Returns:
            Quote data as dictionary.

        Raises:
            ValueError: If symbol is invalid.
            RuntimeError: If fetching quote fails.
        """
        await self._ensure_authenticated()

        if not symbol:
            msg = "symbol is required"
            raise ValueError(msg)

        async def _get_quote() -> Mapping[str, Any]:
            instrument_token = f"{self._parse_exchange(exchange)}:{symbol}"
            quotes = self._client.quote(instrument_tokens=instrument_token)
            if not quotes:
                msg = f"No quote data for {symbol}"
                raise RuntimeError(msg)
            return quotes[instrument_token]  # type: ignore[no-any-return]

        return await self._execute_with_retry(_get_quote)  # type: ignore[no-any-return]
