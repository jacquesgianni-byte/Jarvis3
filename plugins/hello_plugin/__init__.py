"""
hello_plugin — Genesis-046 proof-of-concept plugin.

Demonstrates the Sprint-002 plugin contract:
  - get_workers(config=None) accepts config dict from PluginLoader
  - plugin.json provides stable identity
  - config.json (optional) provides configuration
  - Plugin interprets its own config keys; Jarvis Core never inspects them
  - Workers integrate with the existing Worker architecture
  - No changes to Jarvis Core required

To disable: remove "hello_plugin" from plugins/enabled.json.
"""

from plugins.hello_plugin.worker import HelloWorker


def get_workers(config=None):
    """
    Return the list of workers this plugin contributes.

    config: dict passed by PluginLoader from config.json (or {} if absent).
            Plugin is responsible for interpreting all keys.
            config=None is treated as {}.
    """
    if config is None:
        config = {}
    return [HelloWorker(config=config)]
