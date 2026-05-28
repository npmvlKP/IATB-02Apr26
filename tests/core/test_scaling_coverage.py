"""Supplemental coverage tests for scaling module.

Covers: ClusterHealth zero max_strategies capacity_ratio, NodeInfo zero max_strategies
strategy_capacity, _validate_utc with non-UTC raises, NodeRole/NodeStatus enum values,
generate_node_id different ports, update_heartbeat with non-UTC raises,
elect_leader with non-UTC raises, get_cluster_health with non-UTC raises,
assign_strategy already assigned returns existing, unassign_strategy node not in cluster.
"""

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
    _validate_utc,
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


class TestClusterHealthEdgeCases:
    def test_zero_max_strategies_capacity_ratio(self) -> None:
        health = ClusterHealth(
            total_nodes=1,
            healthy_nodes=1,
            degraded_nodes=0,
            unhealthy_nodes=0,
            offline_nodes=0,
            total_strategies=5,
            max_strategies=0,
        )
        assert health.capacity_ratio == Decimal("0")

    def test_all_nodes_offline(self) -> None:
        health = ClusterHealth(
            total_nodes=3,
            healthy_nodes=0,
            degraded_nodes=0,
            unhealthy_nodes=0,
            offline_nodes=3,
            total_strategies=0,
            max_strategies=30,
        )
        assert health.health_ratio == Decimal("0")
        assert health.capacity_ratio == Decimal("0")

    def test_all_nodes_healthy(self) -> None:
        health = ClusterHealth(
            total_nodes=5,
            healthy_nodes=5,
            degraded_nodes=0,
            unhealthy_nodes=0,
            offline_nodes=0,
            total_strategies=25,
            max_strategies=50,
        )
        assert health.health_ratio == Decimal("1")

    def test_capacity_ratio_full(self) -> None:
        health = ClusterHealth(
            total_nodes=2,
            healthy_nodes=2,
            degraded_nodes=0,
            unhealthy_nodes=0,
            offline_nodes=0,
            total_strategies=20,
            max_strategies=20,
        )
        assert health.capacity_ratio == Decimal("1")


class TestNodeInfoZeroMaxStrategies:
    def test_strategy_capacity_with_zero_max(self) -> None:
        node = NodeInfo(
            node_id="zero-max",
            host="h",
            port=8001,
            role=NodeRole.WORKER,
            status=NodeStatus.HEALTHY,
            registered_at=_utc_now(),
            last_heartbeat=_utc_now(),
            max_strategies=0,
            active_strategies=0,
        )
        assert node.strategy_capacity == Decimal("0")

    def test_is_available_with_zero_max(self) -> None:
        node = NodeInfo(
            node_id="zero-max-avail",
            host="h",
            port=8002,
            role=NodeRole.WORKER,
            status=NodeStatus.HEALTHY,
            registered_at=_utc_now(),
            last_heartbeat=_utc_now(),
            max_strategies=0,
            active_strategies=0,
        )
        assert node.is_available is False


class TestNodeRoleEnumValues:
    def test_leader_value(self) -> None:
        assert NodeRole.LEADER == "LEADER"

    def test_worker_value(self) -> None:
        assert NodeRole.WORKER == "WORKER"

    def test_observer_value(self) -> None:
        assert NodeRole.OBSERVER == "OBSERVER"


class TestNodeStatusEnumValues:
    def test_healthy_value(self) -> None:
        assert NodeStatus.HEALTHY == "HEALTHY"

    def test_degraded_value(self) -> None:
        assert NodeStatus.DEGRADED == "DEGRADED"

    def test_unhealthy_value(self) -> None:
        assert NodeStatus.UNHEALTHY == "UNHEALTHY"

    def test_offline_value(self) -> None:
        assert NodeStatus.OFFLINE == "OFFLINE"


class TestValidateUTC:
    def test_non_utc_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2026, 4, 27, 12, 0, 0))

    def test_utc_passes(self) -> None:
        _validate_utc(_utc_now())


class TestClusterManagerUTCErrors:
    def _make_cluster(self, max_nodes: int = 10) -> ClusterManager:
        config = ScalingConfig(
            max_nodes=max_nodes, heartbeat_timeout=timedelta(seconds=90)
        )
        return ClusterManager(config)

    def test_update_heartbeat_non_utc_raises(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        with pytest.raises(ConfigError, match="UTC"):
            cm.update_heartbeat("node-001", datetime(2026, 4, 27, 12, 0, 0))

    def test_get_cluster_health_non_utc_raises(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        with pytest.raises(ConfigError, match="UTC"):
            cm.get_cluster_health(datetime(2026, 4, 27, 12, 0, 0))

    def test_elect_leader_non_utc_raises(self) -> None:
        cm = self._make_cluster()
        cm.register_node(_make_node())
        with pytest.raises(ConfigError, match="UTC"):
            cm.elect_leader(datetime(2026, 4, 27, 12, 0, 0))


class TestClusterManagerAssignAlreadyAssigned:
    def test_assign_already_assigned_returns_existing(self) -> None:
        cm = self._make_cluster_with_nodes()
        node_id_1 = cm.assign_strategy("strat-dup")
        node_id_2 = cm.assign_strategy("strat-dup")
        assert node_id_1 == node_id_2

    def _make_cluster_with_nodes(self) -> ClusterManager:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("n1", active=0))
        return cm


class TestClusterManagerUnassignNodeNotInCluster:
    def test_unassign_with_removed_node_no_error(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("temp-node"))
        cm.assign_strategy("strat-temp")
        cm.deregister_node("temp-node")
        cm.unassign_strategy("strat-temp")


class TestGenerateNodeIdDifferentPorts:
    def test_different_ports_different_ids(self) -> None:
        id1 = generate_node_id("localhost", 8000)
        id2 = generate_node_id("localhost", 8001)
        assert id1 != id2


class TestScalingConfigEdgeCases:
    def test_negative_heartbeat_interval_raises(self) -> None:
        with pytest.raises(ConfigError, match="heartbeat_interval"):
            ScalingConfig(heartbeat_interval=timedelta(seconds=-1))

    def test_negative_max_nodes_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_nodes"):
            ScalingConfig(max_nodes=-1)

    def test_default_config_values(self) -> None:
        config = ScalingConfig()
        assert config.max_nodes == 10
        assert config.strategy_replicas == 1
        assert config.heartbeat_interval == timedelta(seconds=30)
        assert config.heartbeat_timeout == timedelta(seconds=90)
        assert config.leader_election_timeout == timedelta(seconds=10)


class TestClusterManagerDegradedNodeAvailable:
    def test_degraded_node_is_available(self) -> None:
        node = _make_node(status=NodeStatus.DEGRADED, active=3)
        assert node.is_available is True

    def test_degraded_node_full_not_available(self) -> None:
        node = _make_node(status=NodeStatus.DEGRADED, active=10)
        assert node.is_available is False


class TestClusterManagerComputeEffectiveStatus:
    def test_healthy_node_within_timeout(self) -> None:
        config = ScalingConfig(heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("fresh"))
        health = cm.get_cluster_health(_utc_now())
        assert health.healthy_nodes == 1

    def test_healthy_node_beyond_timeout_is_offline(self) -> None:
        config = ScalingConfig(heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        stale_node = NodeInfo(
            node_id="stale",
            host="h",
            port=8001,
            role=NodeRole.WORKER,
            status=NodeStatus.HEALTHY,
            registered_at=_utc_now(),
            last_heartbeat=_utc_now() - timedelta(seconds=120),
        )
        cm.register_node(stale_node)
        health = cm.get_cluster_health(_utc_now())
        assert health.offline_nodes == 1


class TestNodeInfoValidation:
    def test_empty_node_id_raises(self) -> None:
        with pytest.raises(ConfigError, match="node_id cannot be empty"):
            NodeInfo(
                node_id="  ",
                host="h",
                port=8000,
                role=NodeRole.WORKER,
                status=NodeStatus.HEALTHY,
                registered_at=_utc_now(),
                last_heartbeat=_utc_now(),
            )

    def test_zero_port_raises(self) -> None:
        with pytest.raises(ConfigError, match="invalid port"):
            NodeInfo(
                node_id="bad-port",
                host="h",
                port=0,
                role=NodeRole.WORKER,
                status=NodeStatus.HEALTHY,
                registered_at=_utc_now(),
                last_heartbeat=_utc_now(),
            )

    def test_negative_port_raises(self) -> None:
        with pytest.raises(ConfigError, match="invalid port"):
            NodeInfo(
                node_id="neg-port",
                host="h",
                port=-1,
                role=NodeRole.WORKER,
                status=NodeStatus.HEALTHY,
                registered_at=_utc_now(),
                last_heartbeat=_utc_now(),
            )

    def test_port_over_65535_raises(self) -> None:
        with pytest.raises(ConfigError, match="invalid port"):
            NodeInfo(
                node_id="high-port",
                host="h",
                port=65536,
                role=NodeRole.WORKER,
                status=NodeStatus.HEALTHY,
                registered_at=_utc_now(),
                last_heartbeat=_utc_now(),
            )

    def test_valid_port_1_accepted(self) -> None:
        node = NodeInfo(
            node_id="port-1",
            host="h",
            port=1,
            role=NodeRole.WORKER,
            status=NodeStatus.HEALTHY,
            registered_at=_utc_now(),
            last_heartbeat=_utc_now(),
        )
        assert node.port == 1

    def test_valid_port_65535_accepted(self) -> None:
        node = NodeInfo(
            node_id="port-max",
            host="h",
            port=65535,
            role=NodeRole.WORKER,
            status=NodeStatus.HEALTHY,
            registered_at=_utc_now(),
            last_heartbeat=_utc_now(),
        )
        assert node.port == 65535


class TestClusterManagerRegisterNodeEdgeCases:
    def test_register_node_at_max_capacity_raises(self) -> None:
        config = ScalingConfig(max_nodes=1, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("first"))
        with pytest.raises(ConfigError, match="max capacity"):
            cm.register_node(_make_node("second"))

    def test_register_duplicate_node_raises(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("dup"))
        with pytest.raises(ConfigError, match="already registered"):
            cm.register_node(_make_node("dup"))

    def test_register_leader_sets_leader_id(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        leader_node = _make_node("leader-1", role=NodeRole.LEADER)
        cm.register_node(leader_node)
        assert cm.get_leader() is not None
        assert cm.get_leader().node_id == "leader-1"

    def test_register_second_leader_does_not_replace(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("leader-1", role=NodeRole.LEADER))
        cm.register_node(_make_node("leader-2", role=NodeRole.LEADER))
        assert cm.get_leader().node_id == "leader-1"


class TestClusterManagerDeregisterNode:
    def test_deregister_existing_node(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("to-remove"))
        cm.deregister_node("to-remove")
        assert cm.get_node_count() == 0

    def test_deregister_nonexistent_raises(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        with pytest.raises(ConfigError, match="node not found"):
            cm.deregister_node("ghost")

    def test_deregister_leader_clears_leader(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("leader-1", role=NodeRole.LEADER))
        cm.deregister_node("leader-1")
        assert cm.get_leader() is None

    def test_deregister_reassigns_strategies(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("n1"))
        cm.assign_strategy("strat-1")
        cm.deregister_node("n1")
        assert "strat-1" not in cm.get_strategy_assignments()


class TestClusterManagerAssignStrategy:
    def test_assign_strategy_no_nodes_raises(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        with pytest.raises(ConfigError, match="no nodes available"):
            cm.assign_strategy("strat-1")

    def test_assign_strategy_no_available_nodes_raises(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        full_node = _make_node("full", active=10)
        cm.register_node(full_node)
        with pytest.raises(ConfigError, match="no available nodes with capacity"):
            cm.assign_strategy("strat-1")

    def test_assign_strategy_picks_least_loaded(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("busy", active=5))
        cm.register_node(_make_node("idle", active=0))
        node_id = cm.assign_strategy("strat-1")
        assert node_id == "idle"


class TestClusterManagerElectLeader:
    def test_elect_leader_selects_healthy(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        cm.register_node(_make_node("w1"))
        cm.register_node(_make_node("w2"))
        leader = cm.elect_leader(_utc_now())
        assert leader.role == NodeRole.LEADER

    def test_elect_leader_no_healthy_raises(self) -> None:
        config = ScalingConfig(max_nodes=5, heartbeat_timeout=timedelta(seconds=90))
        cm = ClusterManager(config)
        unhealthy_node = _make_node("sick", status=NodeStatus.UNHEALTHY)
        cm.register_node(unhealthy_node)
        with pytest.raises(ConfigError, match="no healthy nodes"):
            cm.elect_leader(_utc_now())


class TestScalingConfigStrategyReplicas:
    def test_zero_strategy_replicas_raises(self) -> None:
        with pytest.raises(ConfigError, match="strategy_replicas"):
            ScalingConfig(strategy_replicas=0)

    def test_strategy_replicas_default(self) -> None:
        config = ScalingConfig()
        assert config.strategy_replicas == 1
