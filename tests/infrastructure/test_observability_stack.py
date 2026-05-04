"""Infrastructure tests to validate observability stack configuration."""
from pathlib import Path

import yaml

REQUIRED_SERVICES = {
    "prometheus": {
        "image": "prom/prometheus:v2.54.1",
        "ports": [{"target": 9090, "published": 9090}],
    },
    "grafana": {
        "image": "grafana/grafana:11.3.0",
        "ports": [{"target": 3000, "published": 3000}],
    },
    "otel-collector": {
        "image": "otel/opentelemetry-collector-contrib:0.110.0",
        "ports": [
            {"target": 4317, "published": 4317},
            {"target": 4318, "published": 4318},
        ],
    },
    "jaeger": {
        "image": "jaegertracing/all-in-one:1.62.0",
        "ports": [{"target": 16686, "published": 16686}],
    },
}

REQUIRED_PROMETHEUS_JOBS = {"prometheus", "trading-engine", "otel-collector"}


def load_docker_compose() -> dict:
    """Load and parse docker-compose.yml."""
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists(), "docker-compose.yml not found"
    with open(compose_path) as f:
        return yaml.safe_load(f)


def load_prometheus_config() -> dict:
    """Load and parse config/prometheus.yml."""
    prom_path = Path("config/prometheus.yml")
    assert prom_path.exists(), "config/prometheus.yml not found"
    with open(prom_path) as f:
        return yaml.safe_load(f)


class TestObservabilityStack:
    """Test observability services are correctly configured in docker-compose."""

    def test_all_services_present(self):
        """Verify all required observability services exist."""
        compose = load_docker_compose()
        services = compose.get("services", {})
        for service_name in REQUIRED_SERVICES:
            assert service_name in services, f"Service '{service_name}' missing"

    def test_service_images_and_ports(self):
        """Verify each service uses correct image and port mappings."""
        compose = load_docker_compose()
        services = compose.get("services", {})
        for name, expected in REQUIRED_SERVICES.items():
            service = services[name]
            assert service["image"] == expected["image"], f"{name}: wrong image"
            ports = service.get("ports", [])
            # Normalize port strings "host:container" to dicts
            port_mappings = []
            for p in ports:
                if isinstance(p, str):
                    host, container = p.split(":")
                    port_mappings.append({"target": int(container), "published": int(host)})
                else:
                    port_mappings.append(p)
            for expected_port in expected["ports"]:
                assert expected_port in port_mappings, f"{name}: missing port {expected_port}"

    def test_prometheus_volume_mount(self):
        """Verify Prometheus has config volume mount."""
        compose = load_docker_compose()
        prom = compose["services"]["prometheus"]
        volumes = prom.get("volumes", [])
        assert any("prometheus.yml" in v for v in volumes), "Prometheus: missing config volume"

    def test_prometheus_config_scrape_jobs(self):
        """Verify prometheus.yml contains required scrape targets."""
        prom_cfg = load_prometheus_config()
        jobs = {job["job_name"] for job in prom_cfg.get("scrape_configs", [])}
        for required in REQUIRED_PROMETHEUS_JOBS:
            assert required in jobs, f"Missing Prometheus scrape job: {required}"

    def test_services_connected_to_backend_network(self):
        """Verify all observability services are on backend network."""
        compose = load_docker_compose()
        services = compose.get("services", {})
        for name in REQUIRED_SERVICES:
            networks = services[name].get("networks", [])
            assert "backend" in networks, f"{name}: not on backend network"

    def test_all_services_have_common_security(self):
        """Verify observability services use common security profile."""
        compose = load_docker_compose()
        services = compose.get("services", {})
        for name in REQUIRED_SERVICES:
            service = services[name]
            # Check for common-security anchor
            assert "security_opt" in service or "<<:" in str(
                service
            ), f"{name}: missing security options"
