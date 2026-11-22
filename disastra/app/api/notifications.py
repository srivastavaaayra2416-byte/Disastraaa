from fastapi import APIRouter
from app.services.notify_service import notify_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/recent")
async def get_recent_notifications():
    """Returns recent mock notifications (useful for automated testing and UI verification)."""
    return notify_service.sent_notifications
