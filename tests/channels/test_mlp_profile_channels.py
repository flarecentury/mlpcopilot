from mlpcopilot.bus.queue import MessageBus
from mlpcopilot.channels.base import BaseChannel
from mlpcopilot.channels.manager import ChannelManager
from mlpcopilot.config.schema import Config


class _FakeChannel(BaseChannel):
    name = "fake"
    display_name = "Fake"

    @classmethod
    def default_config(cls):
        return {"enabled": False}

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, msg) -> None:
        pass


class _TelegramChannel(_FakeChannel):
    name = "telegram"
    display_name = "Telegram"


class _SlackChannel(_FakeChannel):
    name = "slack"
    display_name = "Slack"


def test_mlpcopilot_profile_only_loads_telegram_channel(monkeypatch) -> None:
    monkeypatch.setattr(
        "mlpcopilot.channels.registry.discover_all",
        lambda: {"telegram": _TelegramChannel, "slack": _SlackChannel},
    )
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "channels": {
                "telegram": {"enabled": True, "allowFrom": ["*"]},
                "slack": {"enabled": True, "allowFrom": ["*"]},
            },
        }
    )

    manager = ChannelManager(config, MessageBus())

    assert list(manager.channels) == ["telegram"]
