from datetime import timedelta

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.secrets_rotation import RotationPolicy, SecretType


def test_rotation_policy_validation():
    # This should work
    valid_policy = RotationPolicy(
        secret_type=SecretType.API_KEY, rotation_interval=timedelta(days=30)
    )
    assert valid_policy.rotation_interval == timedelta(days=30)

    # This should raise ConfigError
    with pytest.raises(ConfigError):
        RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(seconds=0),  # Zero interval
        )


if __name__ == "__main__":
    test_rotation_policy_validation()
