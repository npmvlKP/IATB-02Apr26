"""Tests for Horizontal Scaling Infrastructure."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.scaling import (
    ClusterHealth,
    ClusterManager,
    NodeInfo,
    NodeRole,
    NodeStatus,
    ScalingConfig,
    generate_node_id,
)


def _utc_now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _make_node(
    node_id: str = "node-001",
    role: NodeRole = NodeRole.WORKER,
    status: NodeStatus = NodeStatus.HEALTHY,
    active: int = 0,
) -> NodeInfo:
    return NodeInfo(
        node_id=node_id,
        host="localhost",
        port=8000 + hash(node_id) % 1000,
        role=role,
        status=status,
        registered_at=_utc_now(),
        last_heartbeat=_utc_now(),
        max_strategies=10,
        active_strategies=active,
    )


class TestNodeInfo:
    def test_valid_node(self) -> None:
        node = _make_node()
        assert node.node_id == "node-001"
        assert node.is_available is True

    def test_empty_node_id_rejected(self) -> None:
        with pytest.raises(ConfigError, match="node_id"):
            _make_node(node_id="   ")

    def test_invalid_port_rejected(self) -> None:
        with pytest.raises(ConfigError, match="port"):
            NodeInfo(
                node_id="n1",
                host="h",
                port=0,
                role=NodeRole.WORKER,
                status=NodeStatus.HEALTHY,
                registered_at=_utc_now(),
                last_heartbeat=_utc_now(),
            )

    def test_invalid_port_high_rejected(self) -> None:
        with pytest.raises(ConfigError, match="port"):
            NodeInfo(
                node_id="n1",
                host="h",
                port=70000,
                role=NodeRole.WORKER,
                status=NodeStatus.HEALTHY,
                registered_at=_utc_now(),
                last_heartbeat=_utc_now(),
            )

    def test_strategy_capacity(self) -> None:
        node = _make_node(active=5)
        assert node.strategy_capacity == Decimal("0.5")

    def test_strategy_capacity_full(self) -> None:
        node = _make_node(active=10)
        assert node.is_available is False

    def test_unhealthy_node_not_available(self) -> None:
        node = _make_node(status=NodeStatus.UNHEALTHY)
        assert node.is_available is False

    def test_offline_node_not_available(self) -> None:
        node = _make_node(status=NodeStatus.OFFLINE)
        assert node.is_available is False


class TestClusterHealth:
    def test_health_ratio(self) -> None:
        health = ClusterHealth(
            total_nodes=4,
            healthy_nodes=3,
            degraded_nodes=0,
            unhealthy_nodes=1,
            offline_nodes=0,
            total_strategies=10,
            max_strategies=40,
        )
        assert health.health_ratio == Decimal("0.75")

    def test_health_ratio_zero_nodes(self) -> None:
        health = ClusterHealth(
            total_nodes=0,
            healthy_nodes=0,
            degraded_nodes=0,
            unhealthy_nodes=0,
            offline_nodes=0,
            total_strategies=0,
            max_strategies=0,
        )
        assert health.health_ratio == Decimal("0")

    def test_capacity_ratio(self) -> None:
        health = ClusterHealth(
            total_nodes=2,
            healthy_nodes=2,
            degraded_nodes=0,
            unhealthy_nodes=0,
            offline_nodes=0,
            total_strategies=10,
            max_strategies=20,
        )
        assert health.capacity_ratio == Decimal("0.5")


class TestScalingConfig:
    def test_valid_config(self) -> None:
        config = ScalingConfig()
        assert config.max_nodes == 10

    def test_invalid_heartbeat_interval(self) -> None:
        with pytest.raises(ConfigError, match="heartbeat_interval"):
            ScalingConfig(heartbeat_interval=timedelta(0))

    def test_invalid_max_nodes(self) -> None:
        with pytest.raises(ConfigError, match="max_nodes"):
            ScalingConfig(max_nodes=0)

    def test_invalid_strategy_replicas(self) -> None:
        with pytest.raises(ConfigError, match="strategy_replicas"):
            ScalingConfig(strategy_replicas=0)


class TestClusterManager:
    def _make_cluster(self, max_nodes: int = 10) -> ClusterManager:
        config = ScalingConfig(max_nodes=max_nodes, heartbeat_timeout=timedelta(seconds=90))
        return ClusterManager(config)

    def test_register_node(self) -> None:
        cm = self._make_cluster()
        node = _make_node()
        cm.register_node(node)
        assert cm.get_node_count() == 1

    def test_register_duplicate_rejected(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        with pytest.raises(ConfigError, match="already registered"):
            cm.register_node(_make_node())

    def test_register_max_capacity_rejected(self) -> None:
        cm = self._make_cluster(max_nodes=1)
        cm.register_node(_make_node("n1"))
        with pytest.raises(ConfigError, match="max capacity"):
            cm.register_node(_make_node("n2"))

    def test_deregister_node(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        cm.deregister_node("node-001")
        assert cm.get_node_count() == 0

    def test_deregister_unknown_rejected(self) -> None:
        cm = self._make_cluster()
        with pytest.raises(ConfigError, match="not found"):
            cm.deregister_node("unknown")

    def test_update_heartbeat(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        later = _utc_now() + timedelta(minutes=1)
        updated = cm.update_heartbeat("node-001", later)
        assert updated.last_heartbeat == later

    def test_update_heartbeat_unknown_rejected(self) -> None:
        cm = self._make_cluster()
        with pytest.raises(ConfigError, match="not found"):
            cm.update_heartbeat("unknown", _utc_now())

    def test_get_cluster_health(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("n1", status=NodeStatus.HEALTHY))
        cm.register_node(_make_node("n2", status=NodeStatus.DEGRADED))
        health = cm.get_cluster_health(_utc_now())
        assert health.total_nodes == 2
        assert health.healthy_nodes == 1
        assert health.degraded_nodes == 1

    def test_get_cluster_health_offline_node(self) -> None:
        cm = self._make_cluster()
        old_heartbeat = _utc_now() - timedelta(seconds=120)
        node = NodeInfo(
            node_id="stale",
            host="h",
            port=8001,
            role=NodeRole.WORKER,
            status=NodeStatus.HEALTHY,
            registered_at=_utc_now(),
            last_heartbeat=old_heartbeat,
        )
        cm.register_node(node)
        health = cm.get_cluster_health(_utc_now())
        assert health.offline_nodes == 1

    def test_assign_strategy(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        node_id = cm.assign_strategy("strat-001")
        assert node_id == "node-001"
        assignments = cm.get_strategy_assignments()
        assert "strat-001" in assignments

    def test_assign_strategy_no_nodes_rejected(self) -> None:
        cm = self._make_cluster()
        with pytest.raises(ConfigError, match="no nodes"):
            cm.assign_strategy("strat-001")

    def test_assign_strategy_least_loaded(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("n1", active=5))
        cm.register_node(_make_node("n2", active=0))
        node_id = cm.assign_strategy("strat-001")
        assert node_id == "n2"

    def test_assign_strategy_no_capacity_rejected(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("n1", active=10))
        with pytest.raises(ConfigError, match="no available"):
            cm.assign_strategy("strat-001")

    def test_unassign_strategy(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        cm.assign_strategy("strat-001")
        cm.unassign_strategy("strat-001")
        assert "strat-001" not in cm.get_strategy_assignments()

    def test_unassign_unknown_noop(self) -> None:
        cm = self._make_cluster()
        cm.unassign_strategy("unknown")

    def test_deregister_reassigns_strategies(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("n1"))
        cm.assign_strategy("strat-001")
        cm.deregister_node("n1")
        assert "strat-001" not in cm.get_strategy_assignments()

    def test_elect_leader(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("n1"))
        cm.register_node(_make_node("n2"))
        leader = cm.elect_leader(_utc_now())
        assert leader.role == NodeRole.LEADER
        assert cm.get_leader() is not None

    def test_elect_leader_no_healthy_rejected(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("n1", status=NodeStatus.UNHEALTHY))
        with pytest.raises(ConfigError, match="no healthy"):
            cm.elect_leader(_utc_now())

    def test_deregister_leader_clears(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node("leader", role=NodeRole.LEADER))
        assert cm.get_leader() is not None
        cm.deregister_node("leader")
        assert cm.get_leader() is None


class TestGenerateNodeId:
    def test_deterministic(self) -> None:
        id1 = generate_node_id("localhost", 8000)
        id2 = generate_node_id("localhost", 8000)
        assert id1 == id2

    def test_different_for_different_hosts(self) -> None:
        id1 = generate_node_id("host1", 8000)
        id2 = generate_node_id("host2", 8000)
        assert id1 != id2

    def test_length(self) -> None:
        node_id = generate_node_id("localhost", 8000)
        assert len(node_id) == 12
