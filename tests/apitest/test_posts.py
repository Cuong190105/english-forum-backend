from datetime import datetime, timezone
from database.models import Post
import pytest

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestPost:

    @pytest.mark.asyncio
    async def test_getNewsfeed(self, async_client):
        # Test async default newsfeed filter
        response = await async_client.get(
            "/",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 200

        # Test with criteria newsfeed filter
        response = await async_client.get(
            "/",
            headers={"Authorization": "Bearer 1"},
            params = {
                "criteria": "trending",
            }
        )
        assert response.status_code == 200

        # Test with criteria, cursor and limit newsfeed filter
        response = await async_client.get(
            "/",
            headers={"Authorization": "Bearer 1"},
            params = {
                "criteria": "trending",
                "cursor": datetime.now(timezone.utc),
                "limit": 15,
            }
        )
        assert response.status_code == 200

        # Test with invalid criteria
        response = await async_client.get(
            "/",
            headers={"Authorization": "Bearer 1"},
            params = {
                "criteria": "trding",
            }
        )
        assert response.status_code == 422

        # Test with invalid criteria
        response = await async_client.get(
            "/",
            headers={"Authorization": "Bearer 1"},
            params = {
                "limit": "0",
            }
        )
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_upload(self, mock_file, async_client):
        # Test upload without attachment
        response = await async_client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 201

        # Test blank field
        response = await async_client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "",
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 422

        # Test missing field
        response = await async_client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 422

        # Test mentioning
        response = await async_client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "@testuser1 @testuser2 check this out!",
                "tag": "discussion",
            }
        )
        assert response.status_code == 201

        # Test with attachment
        response = await async_client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title",
                "content": "Test",
                "tag": "discussion",
            },
            files = [
                ("attachments", mock_file["too_big_png"]),
                ("attachments", mock_file["normal_jpg"])
            ]
        )
        
        assert response.status_code == 422

        response = await async_client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title",
                "content": "Test",
                "tag": "discussion",
            },
            files = [
                ("attachments", mock_file["normal_jpeg"]),
                ("attachments", mock_file["normal_jpg"]),
            ]
        )
        assert response.status_code == 201
        
    @pytest.mark.asyncio
    async def test_getPost(self, async_client):
        # Test normal post
        response = await async_client.get(
            "/posts/1",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 200
        assert response.json().get("post_id") == 1

        # Test non existent post
        response = await async_client.get(
            "/posts/999",
            headers={"Authorization": "Bearer 1"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_editPost(self, mock_file, async_client):
        # Test edit without attachment
        response = await async_client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 202

        # Test blank field
        response = await async_client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "",
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 422

        # Test missing field
        response = await async_client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 422

        # Test post not found
        response = await async_client.put(
            "/posts/999",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 404

        # Test user not permitted
        response = await async_client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 2"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "discussion",
            }
        )
        assert response.status_code == 403

        # Test with attachment
        response = await async_client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "discussion",
                "attachments_update": "add 3",
            },
            files = [
                ("attachments", mock_file["too_big_mp4"])
            ]
        )
        assert response.status_code == 422

        response = await async_client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "discussion",
                "attachments_update": "add 4",
            },
            files = [
                ("attachments", mock_file["file7"])
            ]
        )
        assert response.status_code == 202
        # ...

    @pytest.mark.asyncio
    async def test_deletePost(self, async_client):
        # Test user not permitted
        response = await async_client.delete(
            "/posts/1",
            headers={"Authorization": "Bearer 2"},
        )
        assert response.status_code == 403

        # Test post not found
        response = await async_client.delete(
            "/posts/999",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404

        # Test normal delete
        response = await async_client.delete(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 200

        # Test re-delete
        response = await async_client.delete(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404


    @pytest.mark.asyncio
    async def test_votePost(self, redis_client, async_client, mock_db):
        mock_db.query(Post).filter(Post.post_id == 1).first().is_deleted = False
        mock_db.commit()
        # Test normal vote
        r = await async_client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 1}
        )
        assert r.status_code == 200
        
        r = await async_client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": -1}
        )
        assert r.status_code == 200
        
        r = await async_client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 0}
        )
        assert r.status_code == 200
        
        # Test post not found
        r = await async_client.post(
            "/posts/999/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 0}
        )
        assert r.status_code == 404
        
        # Test invalid value
        r = await async_client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 999}
        )
        assert r.status_code == 400

        r = await async_client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 1.5}
        )
        assert r.status_code == 422
