from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import traceback
import typing
import uuid
from fastapi import UploadFile
from configs.config_app import FilePurpose
from configs.config_post import FileChange
from configs.config_validation import FileRule
from database.database import Db_dependency
from database.models import Attachment, Post, User
def getMetadata(file: UploadFile):
    filename = file.filename
    ext = filename[filename.rfind(".")]

async def validateFile(file: UploadFile):
    """
    Validate a file by type and size.
    
    Params:
        file: File need validating

    Returns:
        bool: True if pass, else False
    """
    ext = os.path.splitext(file.filename)[1]
    limitSize = 0
    if ext in FileRule.VALID_IMAGE_FILE_TYPES:
        limitSize = FileRule.IMAGE_MAX_SIZE_MB
    elif ext in FileRule.VALID_VIDEO_FILE_TYPES:
        limitSize = FileRule.VIDEO_MAX_SIZE_MB
    else:
        return False
    
    total_size = 0
    CHUNK_SIZE = 1024 * 1024
    while chunk := await file.read(CHUNK_SIZE):
        total_size += len(chunk) / CHUNK_SIZE
        if total_size >= limitSize:
            return False
    file.file.seek(0)
    return True

async def saveAttachments(db: Db_dependency, attachments: list[UploadFile]):
    """
    Validate and store attachments.

    Params:
        db: Database session object
        attachments: List of Files uploaded

    Returns:
        Optional[list[Attachment]]: List of Attachment metadata objects. None if one of the attachment fails the validation.  
    """
    # Validate files
    if len(attachments) > FileRule.MAX_FILE_COUNT:
        return None
    for file in attachments:
        if not await validateFile(file):
            print(file.filename)
            return None
    
    # Store files
    idx = 0
    try:
        saved = []
        for file in attachments:
            filename = await saveFile(file, purpose='attachment')

            attachment = Attachment(
                media_type=file.content_type,
                media_metadata="",
                index=idx,
                media_filename=filename,
            )
            idx += 1
            saved.append(attachment)
        return saved
    except Exception as e:
        print(file.filename)
        print(e)
        return None

async def editAttachments(db: Db_dependency, post: Post, attachments: list[UploadFile], updates: str):
    """
    Validate and store updated attachments.

    Params:
        db: Database session object
        attachments: List of Files uploaded
        updates: status of updated media

    Returns:
        int: Change status. 0 for normal, 1 for invalid file, 2 for not acceptable change, 3 for other errors.
    """
    # Validate files
    for file in attachments:
        if not await validateFile(file):
            print("Not validated")
            return 1
        
    updatelist = updates.split(",")
    for update in updatelist:
        parted = update.split(" ")
        if len(parted) < 2 or parted[0] not in typing.get_args(FileChange) or not parted[1].isnumeric() or int(parted[1]) >= FileRule.MAX_FILE_COUNT:
            print("Wrong command", parted)
            return 1
        elif parted[0] == 'move' and (len(parted) == 2 or int(parted[2]) >= FileRule.MAX_FILE_COUNT):
            print("Wrong command", parted)
            return 1

    # Validate attachment position and modify database
    def sortkey(x):
        parted = x.split()
        return (-ord(parted[0][0]), int(parted[1]))
    
    updatelist.sort(key=sortkey)

    try:
        position_taken = []

        postAtt = sorted(post.attachments, key=lambda x: x.index)
        for att in postAtt:
            position_taken.append(att.index)
        newAtts = []

        for update in updatelist:
            parted = update.split(" ")
            idx = int(parted[1])
            if parted[0] == 'remove':
                if idx not in position_taken:
                    db.rollback()
                    return 2
                postAtt[idx].is_deleted = True
                position_taken.remove(idx)

            elif parted[0] == 'move':
                if idx not in position_taken:
                    db.rollback()
                    return 2
                new_idx = int(parted[2])
                postAtt[idx].index = new_idx
                position_taken.remove(idx)
                position_taken.append(new_idx)

            else:
                if idx in position_taken:
                    db.rollback()
                    return 2
                
                newAtts.append(Attachment(
                    media_type=file.content_type,
                    media_metadata="",
                    index=idx,
                    media_filename="",
                ))
                position_taken.append(idx)
                
        position_taken.sort()
        for i in range(len(position_taken) - 1):
            if position_taken[i] + 1 != position_taken[i + 1]:
                db.rollback()
                return 2
        
        if len(newAtts) != len(attachments):
            db.rollback()
            return 2


        # Store files
        for i in range(len(newAtts)):
            file = attachments[i]
            filename = await saveFile(file, purpose='attachment')
            newAtts[i].media_filename = filename
        post.attachments.extend(newAtts)
        db.commit()
        return 0
    except Exception as e:
        print(traceback.format_exc())

        return 3
    
async def getFile(db: Db_dependency, media_filename: str):
    storage_path = Path("storage").resolve().as_posix()
    if db.query(Attachment).filter(Attachment.media_filename == media_filename, Attachment.is_deleted == False).first() is not None:
        return f"{storage_path}/attachments{media_filename}"
    elif db.query(User).filter(User.avatar_filename == media_filename).first() is not None:
        return f"{storage_path}/avatar/{media_filename}"
    return None

async def saveFile(file: UploadFile, purpose: FilePurpose):
    """
    Save an uploaded file.

    Params:
        file: The uploaded file
        purpose: Choose from `avatar` and `attachment`
    
    Returns:
        str: File name
    """
    os.makedirs(f"storage/{purpose}", exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}_{uuid.uuid4().hex}{ext}"
    path = f"storage/{purpose}/{filename}"
    with open(path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)
    return filename
