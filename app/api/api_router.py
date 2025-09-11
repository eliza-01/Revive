# app/api/api_router.py
from app.api.image_access import ImageAccess

class APIRouter:
    def __init__(self):
        self.image_access = ImageAccess()
