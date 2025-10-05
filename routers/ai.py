from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Any, List

from database.database import SessionLocal
from sqlalchemy.orm import Session
from database.models import Post
from utilities import ai_generator

router = APIRouter(prefix="/ai", tags=["ai"])


class GenerateRequest(BaseModel):
    post_id: int
    type: Optional[str] = Field(default='mcq', pattern=r'^(mcq|fill)$')
    num_items: Optional[int] = Field(default=5, ge=1, le=10)


class GenerateResponse(BaseModel):
    items: List[Any] = Field(default_factory=list)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post('/generate', response_model=GenerateResponse)
def generate_homework(req: GenerateRequest, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.post_id == req.post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail='Post not found')

    items = ai_generator.generate_homework(post.content, req.type, req.num_items)
    if not items:
        raise HTTPException(status_code=500, detail='AI generation failed')
    # return the strict JSON items directly
    return {'items': items}
