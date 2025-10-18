import pytest


@pytest.mark.usefixtures("setup_database", "seed_data")
class TestComment:
    
    def test_upload(self, client):

        # Test blank field
        response = client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "",
            }
        )
        assert response.status_code == 422

        # Test missing field
        response = client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 422

        # Test normal
        response = client.post(
            "/posts/2/comments",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 201


    def test_getPostComments(self, client):
        # Test normal get comment
        response = client.get(
            "/posts/1/comments",
            headers={"Authorization": "Bearer 1"}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Test normal get comment with pagination
        r = client.get(
            "/posts/1/comments",
            headers={"Authorization": "Bearer 1"},
            params={
                "offset": 1,
                "limit": 1
            }
        )
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0].get("author_id") == 2

        # Test non existed post
        r = client.get(
            "/posts/3/comments",
            headers={"Authorization": "Bearer 1"},
        )
        assert r.status_code == 404


    def test_editComment(self, client):
        # Test edit normal
        response = client.put(
            "/comments/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "New Content 1",
            }
        )
        assert response.status_code == 202

        # Test blank comment
        response = client.put(
            "/comments/1",
            headers={"Authorization": "Bearer 1"},
            data = {
                "content": "",
            }
        )
        assert response.status_code == 422

        # Test edit not permitted
        response = client.put(
            "/comments/1",
            headers={"Authorization": "Bearer 2"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 403

        # Test comment not exists
        response = client.put(
            "/comments/999",
            headers={"Authorization": "Bearer 2"},
            data = {
                "content": "New comment 1",
            }
        )
        assert response.status_code == 404

    def test_deleteComment(self, client):
        # Test user not permitted
        response = client.delete(
            "/comments/1",
            headers={"Authorization": "Bearer 2"},
        )
        assert response.status_code == 403

        # Test comments not found
        response = client.delete(
            "/comments/999",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 404

        # Test normal behavior
        response = client.delete(
            "/comments/1",
            headers={"Authorization": "Bearer 1"},
        )
        assert response.status_code == 204

    def test_voteComment(self, client):
       # Test normal vote
        r = client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 1}
        )
        assert r.status_code == 200
        
        r = client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": -1}
        )
        assert r.status_code == 200
        
        r = client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 0}
        )
        assert r.status_code == 200
        
        # Test comment not found
        r = client.post(
            "/comments/999/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 0}
        )
        assert r.status_code == 404
        
        # Test invalid value
        r = client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 999}
        )
        assert r.status_code == 400

        r = client.post(
            "/comments/2/vote",
            headers={"Authorization": "Bearer 1"},
            params={"vote_type": 1.5}
        )
        assert r.status_code == 422

# db.close()