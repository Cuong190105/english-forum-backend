from database.models import Post
import pytest

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestPost:

    def test_getNewsfeed(self, client):
        # Test default newsfeed filter
        response = client.get(
            "/",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 200

        # Test with criteria newsfeed filter
        response = client.get(
            "/",
            headers={"Authorization": "Bearer 1"},
            params = {
                "criteria": "trending",
            }
        )
        assert response.status_code == 200

        # Test with criteria and offset+limit newsfeed filter
        response = client.get(
            "/",
            headers={"Authorization": "Bearer 1"},
            params = {
                "criteria": "trending",
                "offset": 15,
                "limit": 15,
            }
        )
    
    def test_upload(self, client):
        # Test upload without attachment
        response = client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 201

        # Test blank field
        response = client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "",
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 422

        # Test missing field
        response = client.post(
            "/posts/upload",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 422

        # Test with attachment
        # ...
        
    def test_getPost(self, client):
        # Test normal post
        response = client.get(
            "/posts/1",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 200
        assert response.json().get("post_id") == 1

        # Test non existent post
        response = client.get(
            "/posts/999",
            headers={"Authorization": "Bearer 1"}
        )

        assert response.status_code == 404

    def test_editPost(self, client):
        # Test edit without attachment
        response = client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 202

        # Test blank field
        response = client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "",
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 422

        # Test missing field
        response = client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 422

        # Test post not found
        response = client.put(
            "/posts/999",
            headers={"Authorization": "Bearer 1"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 404

        # Test user not permitted
        response = client.put(
            "/posts/1",
            headers={"Authorization": "Bearer 2"},
            data = {
                "title": "Title 1",
                "content": "Content 1",
                "tag": "Tag 1",
            }
        )
        assert response.status_code == 403

        # Test with attachment
        # ...

    def test_deletePost(self, client):
        # Test user not permitted
        response = client.delete(
            "/posts/1",
            headers={"Authorization": "Bearer 2"},
        )
        assert response.status_code == 403

        # Test post not found
        response = client.delete(
            "/posts/999",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404

        # Test normal delete
        response = client.delete(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 200

        # Test re-delete
        response = client.delete(
            "/posts/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404


    def test_votePost(self, client, mock_db):
        mock_db.query(Post).filter(Post.post_id == 1).first().is_deleted = False
        mock_db.commit()
        # Test normal vote
        r = client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 1}
        )
        assert r.status_code == 200
        
        r = client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": -1}
        )
        assert r.status_code == 200
        
        r = client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 0}
        )
        assert r.status_code == 200
        
        # Test post not found
        r = client.post(
            "/posts/999/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 0}
        )
        assert r.status_code == 404
        
        # Test invalid value
        r = client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 999}
        )
        assert r.status_code == 400

        r = client.post(
            "/posts/1/vote",
            headers={"Authorization": "Bearer 1"},
            data={"vote_type": 1.5}
        )
        assert r.status_code == 422
