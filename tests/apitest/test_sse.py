import asyncio
import json
import pytest
from httpx import AsyncClient, HTTPStatusError, Timeout

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestSSE:

    @pytest.mark.asyncio
    async def test_sse_noti(self, async_client: AsyncClient, fake_redis):
        # Unauthorized access
        with pytest.raises(HTTPStatusError):
            async with async_client.stream("GET", "/sse/notifications") as response:
                assert response.status_code == 401
                response.raise_for_status()

        # Authorized access
        async with async_client.stream("GET", "/sse/notifications", headers={"Authorization": "Bearer 1"}) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line:
                    assert "data:" in line
                    message = json.loads(line[6:])
                    assert "message" in message
        
    @pytest.mark.asyncio
    async def test_sse_post(self, async_client, fake_redis):
        # Unauthorized access
        with pytest.raises(HTTPStatusError):
            async with async_client.stream("GET", "/sse/post/1") as response:
                assert response.status_code == 401
                response.raise_for_status()

        # Authorized access
        async with async_client.stream("GET", "/sse/post/1", headers={"Authorization": "Bearer 1"}) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line:
                    assert "data:" in line
                    data = line.replace("data: ", "")
                    message = json.loads(data)
                    assert "message" in message