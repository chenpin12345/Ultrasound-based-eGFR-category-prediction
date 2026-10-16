from .datasets import router as datasets_router
from .jobs import router as jobs_router
from .models import router as models_router
from .system import router as system_router
from .training import router as training_router

__all__ = ["datasets_router", "jobs_router", "models_router", "system_router", "training_router"]
