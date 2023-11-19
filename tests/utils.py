import asyncio
import warnings


def get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Return the currently set event loop or create a new event loop if there
    is no set event loop.

    Starting from python3.10, asyncio.get_event_loop() raises a DeprecationWarning
    when there is no event loop set, this deprecation will be enforced starting from
    python3.12

    This function serves as a future-proof wrapper over asyncio.get_event_loop()
    that preserves the old behaviour.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
