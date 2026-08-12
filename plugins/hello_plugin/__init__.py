"""
hello_plugin — Genesis-046 proof-of-concept plugin.

Demonstrates the plugin contract:
  - Exposes get_workers() -> list[BaseWorker]
  - Workers integrate with the existing Worker architecture
  - No changes to Jarvis core required

To disable: remove "hello_plugin" from plugins/enabled.json.
"""

from plugins.hello_plugin.worker import HelloWorker


def get_workers():
    """Return the list of workers this plugin contributes."""
    return [HelloWorker()]
