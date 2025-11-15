import pytest

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestComment:
    
    @pytest.mark.asyncio
    async def test_upload(self, async_client):

        # Test blank field
        response = await async_client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "",
            }
        )
        assert response.status_code == 422

        # Test missing field
        response = await async_client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 422

        # Test non existed post
        response = await async_client.post(
            "/posts/999/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 404

        # Test not existed comment reply to
        response = await async_client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "Reply to non existed comment",
            },
            params = {
                "reply_comment_id": 9996
            }
        )
        assert response.status_code == 404

        # Test reply to comment not in the same post
        response = await async_client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "Reply to non existed comment",
            },
            params = {
                "reply_comment_id": 1
            }
        )
        assert response.status_code == 400

        # Test normal
        response = await async_client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 201

        # Test normal
        response = await async_client.post(
            "/posts/1/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "New comment 2",
            },
            params = {
                "reply_comment_id": 2
            }
        )
        assert response.status_code == 201


    @pytest.mark.asyncio
    async def test_getPostComments(self, async_client):
        # Test normal get comment
        response = await async_client.get(
            "/posts/1/comments",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 200
        assert len(response.json()) == 3

        # Test normal get comment with pagination
        r = await async_client.get(
            "/posts/1/comments",
            headers={"Authorization": "Bearer 1"},
            params={
                "offset": 0,
                "limit": 1
            }
        )
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0].get("author_username") == "testuser1"

        # Test non existed post
        r = await async_client.get(
            "/posts/3/comments",
            headers={"Authorization": "Bearer 1"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_getCommentById(self, async_client):
        # Test normal get comment
        response = await async_client.get(
            "/comments/1",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 202
        assert response.json().get("comment_id") == 1

        # Test non existed comment
        response = await async_client.get(
            "/comments/999",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_editComment(self, async_client):
        # Test edit normal
        response = await async_client.put(
            "/comments/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "New Content 1",
            }
        )
        assert response.status_code == 202

        # Test blank comment
        response = await async_client.put(
            "/comments/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "",
            }
        )
        assert response.status_code == 422

        # Test edit not permitted
        response = await async_client.put(
            "/comments/1",
            headers={"Authorization": "Bearer 2"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 403

        # Test comment not exists
        response = await async_client.put(
            "/comments/999",
            headers={"Authorization": "Bearer 2"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deleteComment(self, async_client):
        # Test user not permitted
        response = await async_client.delete(
            "/comments/1",
            headers={"Authorization": "Bearer 2"},
        )
        assert response.status_code == 403

        # Test comments not found
        response = await async_client.delete(
            "/comments/999",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404

        # Test normal behavior
        response = await async_client.delete(
            "/comments/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_voteComment(self, async_client):
       # Test normal vote
        r = await async_client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 1}
        )
        assert r.status_code == 200
        
        r = await async_client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": -1}
        )
        assert r.status_code == 200
        
        r = await async_client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 0}
        )
        assert r.status_code == 200
        
        # Test comment not found
        r = await async_client.post(
            "/comments/999/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 0}
        )
        assert r.status_code == 404
        
        # Test invalid value
        r = await async_client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 999}
        )
        assert r.status_code == 400

        r = await async_client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 1.5}
        )
        assert r.status_code == 422

# db.close()