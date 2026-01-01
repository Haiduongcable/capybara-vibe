"""LiteLLM configuration and output suppression."""

import os


def suppress_litellm_output():
    """Suppress all LiteLLM verbose output and logging."""
    # Environment variables to suppress LiteLLM
    os.environ["LITELLM_LOG"] = "ERROR"
    os.environ["LITELLM_DROP_PARAMS"] = "True"

    # Force LiteLLM to use httpx instead of aiohttp (fixes DNS issues)
    os.environ["LITELLM_USE_AIOHTTP"] = "False"

    # Import and configure litellm
    try:
        import litellm

        # Disable all success/failure callbacks
        litellm.success_callback = []
        litellm.failure_callback = []

        # Disable telemetry
        litellm.telemetry = False

        # Suppress print statements from litellm
        litellm.suppress_debug_info = True

        # Set to silent mode
        litellm.set_verbose = False

    except ImportError:
        pass

    # Suppress standard library logging for LiteLLM
    import logging

    for logger_name in [
        "LiteLLM",
        "LiteLLM Router",
        "LiteLLM Proxy",
        "litellm",
        "litellm.router",
        "litellm.proxy",
    ]:
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)
        logging.getLogger(logger_name).propagate = False


# Call on import - REMOVED to avoid eager loading
# suppress_litellm_output()
