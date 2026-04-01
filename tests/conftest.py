from __future__ import annotations

import sys
import types


def _install_astrbot_stubs() -> None:
    if "astrbot" in sys.modules:
        return

    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )

    message_components_module = types.ModuleType("astrbot.api.message_components")

    class File:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    message_components_module.File = File

    event_module = types.ModuleType("astrbot.api.event")

    class AstrMessageEvent:
        pass

    class MessageChain(list):
        pass

    class MessageEventResult:
        def stop_event(self):
            return self

    event_module.AstrMessageEvent = AstrMessageEvent
    event_module.MessageChain = MessageChain
    event_module.MessageEventResult = MessageEventResult
    event_module.filter = types.SimpleNamespace()

    star_module = types.ModuleType("astrbot.api.star")

    class Context:
        pass

    class Star:
        def __init__(self, context=None):
            self.context = context

    star_module.Context = Context
    star_module.Star = Star

    api_module.logger = logger
    api_module.message_components = message_components_module
    api_module.event = event_module
    api_module.star = star_module

    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.message_components"] = message_components_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module


_install_astrbot_stubs()
