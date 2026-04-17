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
        return self._simple_extract(single_result)["config"]["running"]


class RunningConfigContext(NornirNutsContext):
    def nuts_task(self) -> Callable[..., Result]:
        return napalm_get

    def nuts_arguments(self) -> Dict[str, Any]:
        return {"getters": ["config"]}

    def nuts_extractor(self) -> RunningConfigExtractor:
        return RunningConfigExtractor(self)


CONTEXT = RunningConfigContext


class TestNapalmRunningConfigContains:
    """Assert that the device's running configuration contains a text snippet."""

    @pytest.mark.nuts("config_snippet")
    def test_running_config_contains(self, single_result: NutsResult, config_snippet: str) -> None:
        assert single_result.result is not None, "No running-config result returned"
        assert config_snippet in single_result.result, f"Snippet not found in running config: {config_snippet!r}"
