import pytest
from utilities import attachments
from database.database import Base
from database.models import Post
@pytest.mark.usefixtures("setup_database", "seed_data")
class TestAccount:

    @pytest.mark.asyncio
    async def test_validateFile(self, mock_file):
        assert await attachments.validateFile(mock_file["normal_jpg"]) == True
        assert await attachments.validateFile(mock_file["normal_jpeg"]) == True
        assert await attachments.validateFile(mock_file["normal_mp4"]) == True
        assert await attachments.validateFile(mock_file["too_big_mp4"]) == False
        assert await attachments.validateFile(mock_file["wrong_type_txt"]) == False
        assert await attachments.validateFile(mock_file["too_big_png"]) == False
    
    @pytest.mark.asyncio
    async def test_saveAttachments(self, mock_db, mock_file):
        attachments_list = [mock_file[x] for x in mock_file.keys()]
        assert await attachments.saveAttachments(mock_db, attachments_list) is None
        assert await attachments.saveAttachments(mock_db, attachments_list[:3]) is None
        assert await attachments.saveAttachments(mock_db, attachments_list[:2]) is not None

    @pytest.mark.asyncio
    async def test_editAttachments(self, mock_db, mock_file):
        post = mock_db.query(Post).first()
        attachments_list = [mock_file[x] for x in mock_file.keys()]
        update1 = "add 0,add 1"
        update2 = "remove 0,add 1"
        update3 = "add"
        update4 = "random text"
        update5 = "add random"
        update6 = "add 100"
        update7 = 'move 2'
        update8 = 'move 2 20'
        update9 = 'remove 3'
        update10 = 'remove 0,move 1 2'
        update11 = 'remove 0,move 1 1'
        update12 = 'add 0'
        update13 = 'remove 0,move 1 0,add 3'
        update14 = 'remove 0,move 1 0,add 1,add 2,add 3'
        update15 = 'remove 0,move 2 0,add 1,add 2'
        update16 = 'remove 0,move 1 0,add 1,add 2'
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update1) == 0
        assert await attachments.editAttachments(mock_db, post, attachments_list[2:3], update2) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update3) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update4) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update5) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update6) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update7) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update8) == 1
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update9) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update10) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update11) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update12) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update13) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update14) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update15) == 2
        assert await attachments.editAttachments(mock_db, post, attachments_list[:2], update16) == 0

    @pytest.mark.asyncio
    async def test_saveFile(self, mock_file):
        assert await attachments.saveFile(mock_file["normal_jpg"], "attachment") is not None

    @pytest.mark.asyncio
    async def test_getFile(self, mock_db):
        assert await attachments.getFile(mock_db, "non_existing_file_id") is None
        assert await attachments.getFile(mock_db, "sample1.jpeg") is not None
        assert await attachments.getFile(mock_db, "virus.jpg") is not None