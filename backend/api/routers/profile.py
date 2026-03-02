"""
api/routers/profile.py

Profile management endpoints.

    GET  /profile                  — get full profile (avatar, bio, stats)
    POST /profile/avatar           — upload profile photo to Supabase Storage
    POST /profile/bio/generate     — AI generates "who you're becoming" 2-liner
    POST /profile/share-message    — AI generates personal invite message + ref link
"""

import io
import uuid
from typing import Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.memory.context_builder import ContextBuilder
from api.dependencies.auth import get_current_active_user
from core.config import get_settings
from core.database import get_db
from db.models.user import User

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter(prefix="/profile", tags=["Profile"])
context_builder = ContextBuilder()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB


# ─── Response schemas ─────────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    user_id: str
    display_name: Optional[str]
    email: str
    avatar_url: Optional[str]
    bio: Optional[str]
    days_active: int
    current_streak: int
    goal_area: Optional[str]


class BioResponse(BaseModel):
    bio: str


class ShareMessageResponse(BaseModel):
    message: str
    share_url: str
    full_text: str  # message + url combined, ready to paste


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return profile data including avatar, bio, and key stats."""
    # Get days active + streak from identity_profiles
    result = await db.execute(
        text("""
            SELECT
                COALESCE(ip.days_active, 0),
                COALESCE(ip.current_streak, 0),
                g.title
            FROM users u
            LEFT JOIN identity_profiles ip ON ip.user_id = u.id
            LEFT JOIN goals g ON g.user_id = u.id AND g.status = 'active'
            WHERE u.id = :user_id
        """),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    days_active = row[0] if row else 0
    current_streak = row[1] if row else 0
    goal_area = row[2] if row else None

    # Get bio from users table (stored after generation)
    bio_result = await db.execute(
        text("SELECT bio FROM users WHERE id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    bio_row = bio_result.fetchone()
    bio = bio_row[0] if bio_row else None

    return ProfileResponse(
        user_id=str(current_user.id),
        display_name=current_user.display_name,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        bio=bio,
        days_active=days_active,
        current_streak=current_streak,
        goal_area=goal_area,
    )


@router.post("/avatar", response_model=dict)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload profile photo to Supabase Storage and save URL to user record."""

    # Validate type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed. Use JPEG, PNG, or WebP.",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5MB.",
        )

    # Build storage path: avatars/{user_id}/{uuid}.{ext}
    ext = file.content_type.split("/")[1]
    if ext == "jpeg":
        ext = "jpg"
    object_path = f"{current_user.id}/{uuid.uuid4()}.{ext}"
    bucket_name = "avatars"

    # Upload to Supabase Storage via REST API
    # URL format: /storage/v1/object/{bucket}/{object_path}
    storage_url = f"{settings.supabase_url}/storage/v1/object/{bucket_name}/{object_path}"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            storage_url,
            content=contents,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": file.content_type,
                "x-upsert": "true",
            },
        )

    if response.status_code not in (200, 201):
        logger.error("avatar_upload_failed", status=response.status_code, body=response.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to upload image. Please try again.",
        )

    # Build public URL
    public_url = (
        f"{settings.supabase_url}/storage/v1/object/public/{bucket_name}/{object_path}"
    )

    # Save to users table
    await db.execute(
        text("UPDATE users SET avatar_url = :url WHERE id = :user_id"),
        {"url": public_url, "user_id": str(current_user.id)},
    )
    await db.commit()

    logger.info("avatar_uploaded", user_id=str(current_user.id))
    return {"avatar_url": public_url}


@router.post("/bio/generate", response_model=BioResponse)
async def generate_bio(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI generates a 2-line 'who you're becoming' bio
    based on interview data and goal. Saves to users table.
    """
    try:
        context = await context_builder.get_context(current_user.id, db)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile context found. Complete onboarding first.",
        )

    # Pull relevant context
    identity = context.get("identity", {})
    goal = context.get("goal", {})
    scores = context.get("scores", {})

    life_direction = identity.get("life_direction", "")
    vision = identity.get("personal_vision", "")
    goal_statement = goal.get("statement", "")
    required_identity = goal.get("required_identity", "")
    transformation_score = scores.get("transformation", 0)

    prompt = f"""You write ultra-concise identity statements for people on transformation journeys.

USER CONTEXT:
- Life direction: {life_direction}
- Vision: {vision}
- Their one goal: {goal_statement}
- The identity they're building: {required_identity}
- Transformation progress: {transformation_score}/100

TASK:
Write exactly 2 lines that capture WHO THIS PERSON IS BECOMING — not what they do, not their job title, not their current state.

Think of it like a compass statement. It should feel aspirational but grounded. Personal but not overly specific. Like something they'd want to read every day.

RULES:
- Exactly 2 lines
- No quotation marks
- No "I am" or "I will" — use present-tense identity language ("Someone who..." or "A person who..." or similar)
- No corporate jargon
- No emojis
- Make it feel earned, not generic

OUTPUT: Just the 2 lines. Nothing else."""

    bio = await _call_openai(prompt, max_tokens=120)

    # Save bio
    await db.execute(
        text("UPDATE users SET bio = :bio WHERE id = :user_id"),
        {"bio": bio, "user_id": str(current_user.id)},
    )
    await db.commit()

    logger.info("bio_generated", user_id=str(current_user.id))
    return BioResponse(bio=bio)


@router.post("/share-message", response_model=ShareMessageResponse)
async def generate_share_message(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI generates a personal invite message referencing goal area + progress.
    Returns message + referral URL for native share sheet.
    """
    # Get stats
    result = await db.execute(
        text("""
            SELECT
                COALESCE(ip.days_active, 0),
                COALESCE(ip.current_streak, 0),
                COALESCE(ip.transformation_score, 0),
                g.refined_statement
            FROM users u
            LEFT JOIN identity_profiles ip ON ip.user_id = u.id
            LEFT JOIN goals g ON g.user_id = u.id AND g.status = 'active'
            WHERE u.id = :user_id
        """),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    days_active = row[0] if row else 0
    current_streak = row[1] if row else 0
    transformation_score = row[2] if row else 0
    goal_title = row[3] if row else None

    # Infer goal area from title (moderate depth — area, not specifics)
    goal_area = _extract_goal_area(goal_title)
    first_name = (current_user.display_name or "").split()[0] or "Someone"

    prompt = f"""You write short, personal transformation share messages for social invites.

PERSON:
- First name: {first_name}
- Goal area: {goal_area} (do NOT mention the specific goal title)
- Days active: {days_active}
- Current streak: {current_streak} days
- Transformation score: {transformation_score}/100

TASK:
Write a short, honest invite message they'd send to a friend. It should feel like something a real person would actually send — not a marketing pitch. Reference their goal area and progress naturally. End with something that makes a friend curious enough to click.

RULES:
- 3-4 sentences max
- First person (they're sending this, not you writing about them)
- Reference the goal AREA loosely (e.g. "my career", "my fitness", "my business") — never the exact goal title
- Mention the streak or days active naturally — make it feel real
- No hashtags, no emojis, no exclamation spam
- Conversational tone — like a WhatsApp message to a friend
- End with something human, not "click here" or "sign up now"

OUTPUT: Just the message. Nothing else."""

    message = await _call_openai(prompt, max_tokens=180)

    # Build referral URL
    ref_slug = _make_ref_slug(current_user.display_name or current_user.email)
    share_url = f"https://onegoalpro.vercel.app?ref={ref_slug}"
    full_text = f"{message}\n\n{share_url}"

    logger.info("share_message_generated", user_id=str(current_user.id))
    return ShareMessageResponse(
        message=message,
        share_url=share_url,
        full_text=full_text,
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _call_openai(prompt: str, max_tokens: int = 200) -> str:
    """Minimal OpenAI call for profile generation."""
    import openai
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()


def _extract_goal_area(goal_title: Optional[str]) -> str:
    """
    Map a goal title to a broad area without exposing specifics.
    Falls back to 'my main goal' if nothing matches.
    """
    if not goal_title:
        return "my main goal"

    title_lower = goal_title.lower()
    area_map = {
        ("business", "startup", "saas", "product", "launch", "revenue", "sales"): "my business",
        ("career", "job", "promotion", "leadership", "manager", "director"): "my career",
        ("fitness", "health", "weight", "run", "gym", "exercise", "training"): "my health",
        ("write", "book", "author", "publish", "content", "blog"): "my writing",
        ("finance", "invest", "money", "saving", "wealth", "income"): "my finances",
        ("family", "relationship", "parenting", "marriage", "partner"): "my personal life",
        ("learn", "skill", "course", "study", "education", "degree"): "my growth",
    }
    for keywords, area in area_map.items():
        if any(kw in title_lower for kw in keywords):
            return area

    return "my main goal"


def _make_ref_slug(name: str) -> str:
    """Turn display name or email into a clean URL slug."""
    import re
    slug = name.lower().split("@")[0]
    slug = re.sub(r"[^a-z0-9]", "", slug)
    return slug[:20] or "friend"