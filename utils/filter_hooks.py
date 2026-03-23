from astrbot.api.event import filter


def optional_filter_hook(hook_name: str):
    def _decorator(func):
        hook = getattr(filter, hook_name, None)
        if not callable(hook):
            return func
        try:
            return hook()(func)
        except TypeError:
            try:
                return hook(func)
            except Exception:
                return func
        except Exception:
            return func

    return _decorator
