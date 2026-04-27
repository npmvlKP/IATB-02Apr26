"""
Horizontal Scaling Infrastructure.

Provides node coordination, health aggregation, and load distribution
for multi-node deployment of the IATB trading platform.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum

from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)


class NodeRole(str, Enum):
    """Role of a node in the cluster."""

    LEADER = "LEADER"
    WORKER = "WORKER"
    OBSERVER = "OBSERVER"


class NodeStatus(str, Enum):
    """Status of a cluster node."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True)
class NodeInfo:
    """Information about a cluster node."""

    node_id: str
    host: str
    port: int
    role: NodeRole
    status: NodeStatus
    registered_at: datetime
    last_heartbeat: datetime
    max_strategies: int = 10
    active_strategies: int = 0
    cpu_usage_pct: Decimal = Decimal("0")
    memory_usage_pct: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            msg = "node_id cannot be empty"
            raise ConfigError(msg)
        if self.port <= 0 or self.port > 65535:
            msg = f"invalid port: {self.port}"
            raise ConfigError(msg)

    @property
    def strategy_capacity(self) -> Decimal:
        """Remaining strategy capacity as ratio."""
        if self.max_strategies <= 0:
            return Decimal("0")
        return Decimal(str(self.active_strategies)) / Decimal(str(self.max_strategies))

    @property
    def is_available(self) -> bool:
        """Check if node can accept more strategies."""
        return (
            self.status in (NodeStatus.HEALTHY, NodeStatus.DEGRADED)
            and self.active_strategies < self.max_strategies
        )


@dataclass(frozen=True)
class ClusterHealth:
    """Aggregated health of the cluster."""

    total_nodes: int
    healthy_nodes: int
    degraded_nodes: int
    unhealthy_nodes: int
    offline_nodes: int
    total_strategies: int
    max_strategies: int

    @property
    def health_ratio(self) -> Decimal:
        """Ratio of healthy nodes to total nodes."""
        if self.total_nodes == 0:
            return Decimal("0")
        return Decimal(str(self.healthy_nodes)) / Decimal(str(self.total_nodes))

    @property
    def capacity_ratio(self) -> Decimal:
        """Current strategy capacity usage ratio."""
        if self.max_strategies == 0:
            return Decimal("0")
        return Decimal(str(self.total_strategies)) / Decimal(str(self.max_strategies))


@dataclass(frozen=True)
class ScalingConfig:
    """Configuration for horizontal scaling."""

    heartbeat_interval: timedelta = timedelta(seconds=30)
    heartbeat_timeout: timedelta = timedelta(seconds=90)
    max_nodes: int = 10
    strategy_replicas: int = 1
    leader_election_timeout: timedelta = timedelta(seconds=10)

    def __post_init__(self) -> None:
        if self.heartbeat_interval.total_seconds() <= 0:
            msg = "heartbeat_interval must be positive"
            raise ConfigError(msg)
        if self.max_nodes <= 0:
            msg = "max_nodes must be positive"
            raise ConfigError(msg)
        if self.strategy_replicas < 1:
            msg = "strategy_replicas must be at least 1"
            raise ConfigError(msg)


class ClusterManager:
    """Manages horizontal scaling with node coordination."""

    def __init__(self, config: ScalingConfig) -> None:
        self._config = config
        self._nodes: dict[str, NodeInfo] = {}
        self._strategy_assignments: dict[str, str] = {}
        self._leader_id: str | None = None

    def register_node(self, node: NodeInfo) -> None:
        """Register a new node in the cluster."""
        if len(self._nodes) >= self._config.max_nodes:
            msg = f"cluster at max capacity: {self._config.max_nodes} nodes"
            raise ConfigError(msg)
        if node.node_id in self._nodes:
            msg = f"node already registered: {node.node_id}"
            raise ConfigError(msg)
        self._nodes[node.node_id] = node
        if node.role == NodeRole.LEADER and self._leader_id is None:
            self._leader_id = node.node_id
        _LOGGER.info(
            "Node registered",
            extra={"node_id": node.node_id, "role": node.role.value},
        )

    def deregister_node(self, node_id: str) -> None:
        """Remove a node from the cluster."""
        if node_id not in self._nodes:
            msg = f"node not found: {node_id}"
            raise ConfigError(msg)
        strategies_to_reassign = [s for s, n in self._strategy_assignments.items() if n == node_id]
        for strategy_id in strategies_to_reassign:
            del self._strategy_assignments[strategy_id]
        if self._leader_id == node_id:
            self._leader_id = None
        del self._nodes[node_id]
        _LOGGER.info("Node deregistered", extra={"node_id": node_id})

    def update_heartbeat(self, node_id: str, now_utc: datetime) -> NodeInfo:
        """Update heartbeat for a node."""
        _validate_utc(now_utc)
        if node_id not in self._nodes:
            msg = f"node not found: {node_id}"
            raise ConfigError(msg)
        old = self._nodes[node_id]
        updated = NodeInfo(
            node_id=old.node_id,
            host=old.host,
            port=old.port,
            role=old.role,
            status=old.status,
            registered_at=old.registered_at,
            last_heartbeat=now_utc,
            max_strategies=old.max_strategies,
            active_strategies=old.active_strategies,
            cpu_usage_pct=old.cpu_usage_pct,
            memory_usage_pct=old.memory_usage_pct,
        )
        self._nodes[node_id] = updated
        return updated

    def get_cluster_health(self, now_utc: datetime) -> ClusterHealth:
        """Get aggregated cluster health snapshot."""
        _validate_utc(now_utc)
        healthy = degraded = unhealthy = offline = 0
        total_strat = 0
        max_strat = 0
        for node in self._nodes.values():
            effective_status = self._compute_effective_status(node, now_utc)
            match effective_status:
                case NodeStatus.HEALTHY:
                    healthy += 1
                case NodeStatus.DEGRADED:
                    degraded += 1
                case NodeStatus.UNHEALTHY:
                    unhealthy += 1
                case NodeStatus.OFFLINE:
                    offline += 1
            total_strat += node.active_strategies
            max_strat += node.max_strategies
        return ClusterHealth(
            total_nodes=len(self._nodes),
            healthy_nodes=healthy,
            degraded_nodes=degraded,
            unhealthy_nodes=unhealthy,
            offline_nodes=offline,
            total_strategies=total_strat,
            max_strategies=max_strat,
        )

    def _compute_effective_status(self, node: NodeInfo, now_utc: datetime) -> NodeStatus:
        """Compute effective node status based on heartbeat freshness."""
        elapsed = (now_utc - node.last_heartbeat).total_seconds()
        timeout = self._config.heartbeat_timeout.total_seconds()
        if elapsed > timeout:
            return NodeStatus.OFFLINE
        return node.status

    def assign_strategy(self, strategy_id: str) -> str:
        """Assign a strategy to the best available node."""
        if not self._nodes:
            msg = "no nodes available for strategy assignment"
            raise ConfigError(msg)
        if strategy_id in self._strategy_assignments:
            return self._strategy_assignments[strategy_id]
        best_node = self._find_best_node()
        if best_node is None:
            msg = "no available nodes with capacity for strategy"
            raise ConfigError(msg)
        self._strategy_assignments[strategy_id] = best_node.node_id
        self._increment_strategy_count(best_node.node_id)
        _LOGGER.info(
            "Strategy assigned",
            extra={"strategy_id": strategy_id, "node_id": best_node.node_id},
        )
        return best_node.node_id

    def _find_best_node(self) -> NodeInfo | None:
        """Find the best node for a new strategy assignment."""
        candidates = [n for n in self._nodes.values() if n.is_available]
        if not candidates:
            return None
        return min(candidates, key=lambda n: n.strategy_capacity)

    def _increment_strategy_count(self, node_id: str) -> None:
        """Increment active strategy count for a node."""
        old = self._nodes[node_id]
        updated = NodeInfo(
            node_id=old.node_id,
            host=old.host,
            port=old.port,
            role=old.role,
            status=old.status,
            registered_at=old.registered_at,
            last_heartbeat=old.last_heartbeat,
            max_strategies=old.max_strategies,
            active_strategies=old.active_strategies + 1,
            cpu_usage_pct=old.cpu_usage_pct,
            memory_usage_pct=old.memory_usage_pct,
        )
        self._nodes[node_id] = updated

    def unassign_strategy(self, strategy_id: str) -> None:
        """Unassign a strategy from its node."""
        if strategy_id not in self._strategy_assignments:
            return
        node_id = self._strategy_assignments.pop(strategy_id)
        if node_id in self._nodes:
            old = self._nodes[node_id]
            updated = NodeInfo(
                node_id=old.node_id,
                host=old.host,
                port=old.port,
                role=old.role,
                status=old.status,
                registered_at=old.registered_at,
                last_heartbeat=old.last_heartbeat,
                max_strategies=old.max_strategies,
                active_strategies=max(0, old.active_strategies - 1),
                cpu_usage_pct=old.cpu_usage_pct,
                memory_usage_pct=old.memory_usage_pct,
            )
            self._nodes[node_id] = updated

    def get_leader(self) -> NodeInfo | None:
        """Get the current leader node."""
        if self._leader_id is None:
            return None
        return self._nodes.get(self._leader_id)

    def elect_leader(self, now_utc: datetime) -> NodeInfo:
        """Elect a new leader from healthy nodes."""
        _validate_utc(now_utc)
        candidates = [
            n
            for n in self._nodes.values()
            if self._compute_effective_status(n, now_utc) == NodeStatus.HEALTHY
        ]
        if not candidates:
            msg = "no healthy nodes available for leader election"
            raise ConfigError(msg)
        leader = min(candidates, key=lambda n: n.node_id)
        old = self._nodes[leader.node_id]
        updated = NodeInfo(
            node_id=old.node_id,
            host=old.host,
            port=old.port,
            role=NodeRole.LEADER,
            status=old.status,
            registered_at=old.registered_at,
            last_heartbeat=now_utc,
            max_strategies=old.max_strategies,
            active_strategies=old.active_strategies,
            cpu_usage_pct=old.cpu_usage_pct,
            memory_usage_pct=old.memory_usage_pct,
        )
        self._nodes[leader.node_id] = updated
        self._leader_id = leader.node_id
        _LOGGER.info("Leader elected", extra={"leader_id": leader.node_id})
        return updated

    def get_node_count(self) -> int:
        """Get total number of registered nodes."""
        return len(self._nodes)

    def get_strategy_assignments(self) -> dict[str, str]:
        """Get all strategy-to-node assignments."""
        return dict(self._strategy_assignments)


def generate_node_id(host: str, port: int) -> str:
    """Generate a deterministic node ID from host and port."""
    raw = f"{host}:{port}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _validate_utc(dt: datetime) -> None:
    """Validate datetime is UTC-aware."""
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC-aware"
        raise ConfigError(msg)
