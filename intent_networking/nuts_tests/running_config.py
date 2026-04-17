"""Custom NUTS test class: assert that the device running-config contains a text snippet.

Bundle YAML format::

    - test_class: TestNapalmRunningConfigContains
      label: "Verify NTP servers are configured"
      test_data:
        - host: router1
          config_snippet: "ntp server 10.0.0.1"
        - host: router1
          config_snippet: "ntp server 10.0.0.2"

Or use the intent shorthand (expanded automatically by NutsVerifier)::

    - test_class: TestNapalmRunningConfigContains
      label: "Verify NTP servers are configured"
      expected:
        - config_snippet: "ntp server 10.0.0.1"
        - config_snippet: "ntp server 10.0.0.2"
"""

from typing import Any, Callable, Dict

import pytest
from nornir.core.task import MultiResult, Result
from nornir_napalm.plugins.tasks import napalm_get
from nuts.context import NornirNutsContext
from nuts.helpers.result import AbstractHostResultExtractor, NutsResult


class RunningConfigExtractor(AbstractHostResultExtractor):
    """Extract the running-config text from a NAPALM get_config result."""

    def single_transform(self, single_result: MultiResult) -> str:
        """Return the running-config string from the NAPALM get_config result."""
        return self._simple_extract(single_result)["config"]["running"]


class RunningConfigContext(NornirNutsContext):
    """Nornir NUTS context that fetches device running configuration via NAPALM."""

    def nuts_task(self) -> Callable[..., Result]:
        """Return the Nornir task used to collect data."""
        return napalm_get

    def nuts_arguments(self) -> Dict[str, Any]:
        """Return arguments passed to the Nornir task."""
        return {"getters": ["config"]}

    def nuts_extractor(self) -> RunningConfigExtractor:
        """Return the extractor that transforms raw Nornir results."""
        return RunningConfigExtractor(self)


CONTEXT = RunningConfigContext


class TestNapalmRunningConfigContains:
    """Assert that the device's running configuration contains a text snippet."""

    @pytest.mark.nuts("config_snippet")
    def test_running_config_contains(self, single_result: NutsResult, config_snippet: str) -> None:
        """Fail if config_snippet is not present in the device's running configuration."""
        if single_result.result is None:
            pytest.fail("No running-config result returned")
        if config_snippet not in single_result.result:
            pytest.fail(f"Snippet not found in running config: {config_snippet!r}")
