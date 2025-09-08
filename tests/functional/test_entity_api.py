import asyncio
import logging

import pytest
from appdaemon.app_management import ManagedObject

from .utils import AsyncTempTest

logger = logging.getLogger("AppDaemon._test")


@pytest.mark.ci
@pytest.mark.functional
class TestEntityAPI:
    """Class to group the various tests for the entity API."""

    app_name: str = "test_entity_api"
    timeout: int | float = 2.0

    @pytest.mark.asyncio
    async def test_entity_api(self, run_app_for_time: AsyncTempTest) -> None:
        async with run_app_for_time(self.app_name) as (ad, caplog):
            match ad.app_management.objects.get(self.app_name):
                case ManagedObject(object=app_obj):
                    await asyncio.wait_for(app_obj.execute_event.wait(), timeout=self.timeout)
