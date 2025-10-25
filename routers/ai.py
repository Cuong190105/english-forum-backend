from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from database.database import Db_dependency
from database.models import Post
from database.outputmodel import OutputAIGeneratedItems
# Use our LLM generator utilities
from utilities.ai_generator_LLM_Clone import (
    generate_homework as llm_generate_homework,
    generate_exercises_from_context,
)

router = APIRouter()


class GenerateRequest(BaseModel):
    post_id: int
    type: Optional[str] = Field(default='mcq', pattern=r'^(mcq|fill)$')
    num_items: Optional[int] = Field(default=1, ge=1, le=10)


class GenerateFromTextRequest(BaseModel):
    context_text: str = Field(min_length=1)
    type: Optional[str] = Field(default='mcq', pattern=r'^(mcq|fill)$')
    num_items: Optional[int] = Field(default=1, ge=1, le=10)
    mode: Optional[str] = Field(default='cot', pattern=r'^(cot|minimal)$')


@router.post('/ai/generate/{post_id}', response_model=OutputAIGeneratedItems, status_code=status.HTTP_200_OK)
async def generate_homework(post_id: int, req: GenerateRequest, db: Db_dependency):
    post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
    if not post:
        raise HTTPException(status_code=404, detail='Post not found')
    items = llm_generate_homework(post.content, req.type, req.num_items)
    if not items:
        raise HTTPException(status_code=500, detail='AI generation failed')
    # return the strict JSON items directly
    return {'items': items}


@router.post('/ai/generate-from-text', response_model=OutputAIGeneratedItems, status_code=status.HTTP_200_OK)
async def generate_from_text(req: GenerateFromTextRequest):
    """
    Accept raw context text, classify a single best-fit grammar topic, then generate
    MCQ/FILL items locked to that topic using our LLM prompts.
    """
    text = (req.context_text or '').strip()
    if not text:
        raise HTTPException(status_code=400, detail='context_text is required')

    try:
        result = generate_exercises_from_context(
            context_text=text,
            hw_type=(req.type or 'mcq'),
            num_items=int(req.num_items or 1),
            mode=(req.mode or 'cot'),
            temperature=0.0,
            seed=0,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'LLM generation failed: {e}')

    # include isAskable flag (False when classifier couldn't pick an allowed topic)
    return {"items": result.get("items", []), "isAskable": bool(result.get("isAskable", True))}
