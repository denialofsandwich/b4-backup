import omegaconf.errors
import pytest

from b4_backup.config_schema import BaseConfig


@pytest.mark.parametrize(
    "default_targets",
    [
        [],
        ["localhost/home"],
        ["localhost"],
    ],
)
def test_post_init(
    config: BaseConfig,
    default_targets: list[str],
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(config, "default_targets", default_targets)

    # Act
    config.__post_init__()


def test_post_init__error(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(config, "default_targets", ["idontexist"])

    # Act
    with pytest.raises(omegaconf.errors.ValidationError):
        config.__post_init__()
