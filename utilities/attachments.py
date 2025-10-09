from fastapi import UploadFile
def getMetadata(file: UploadFile):
    filename = file.filename
    ext = filename[filename.rfind(".")]