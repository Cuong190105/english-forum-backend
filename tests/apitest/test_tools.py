from datetime import datetime, timedelta, timezone
import pytest

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestPost:

    @pytest.mark.asyncio
    async def test_search(self, async_client):
        response = await async_client.get(
            "/search",
            headers={"Authorization": "Bearer 1"},
            params = {
                "keyword": "",
            }
        )
        assert response.status_code == 400

        # Test with criteria newsfeed filter
        response = await async_client.get(
            "/search",
            headers={"Authorization": "Bearer 1"},
            params = {
                "keyword": "abc",
            }
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_getNotifications(self, async_client):
        response = await async_client.get(
            "/notifications",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

        # Test with criteria newsfeed filter
        response = await async_client.get(
            "/notifications",
            headers={"Authorization": "Bearer 1"},
            params = {
                "cursor": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            }
        )
        assert response.status_code == 200
        assert len(response.json()) == 0

    @pytest.mark.asyncio
    async def test_markAsRead(self, async_client):
        response = await async_client.put(
            "/notifications/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 200

        # Test with criteria newsfeed filter
        response = await async_client.put(
            "/notifications/999",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code ==400

    @pytest.mark.asyncio
    async def test_download(self, async_client):
        response = await async_client.get(
            "/download/text.jpg",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404

