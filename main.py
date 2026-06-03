from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from routers import categories, auth, report
import logging
import time

# ===== SETUP LOGGING =====
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="API Lapor Fasilitas Pekanbaru",
    description="Backend API untuk sistem pelaporan fasilitas umum Pekanbaru",
    version="1.0.0",
)

# ===== MIDDLEWARE: CORS =====
# Configure CORS (Sementara dibuka semua agar Frontend bisa akses dari mana saja)
allowed_origins = [
    "*",  # Mengizinkan semua domain (penting untuk kolaborasi jarak jauh)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ===== MIDDLEWARE: Request Logging =====
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log semua request dan response"""
    start_time = time.time()

    logger.info(f"→ {request.method} {request.url.path}")

    response = await call_next(request)

    process_time = time.time() - start_time
    logger.info(f"← {response.status_code} (dalam {process_time:.3f}s)")

    return response


# ===== MIDDLEWARE: Error Handling =====
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation error dengan response yang lebih baik"""
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "code": "VALIDATION_ERROR",
            "message": "Data input tidak valid",
            "errors": exc.errors(),
        },
    )


# ===== INCLUDE ROUTERS =====
app.include_router(categories.router)
app.include_router(auth.router)
app.include_router(report.router)


# ===== ENDPOINTS =====
@app.get("/")
def read_root():
    """Root endpoint - status API"""
    return {
        "status": "success",
        "message": "Backend API Lapor Fasilitas Pekanbaru sudah online ✓",
        "version": "1.0.0",
    }


# ===== HEALTH CHECK ENDPOINT =====
@app.get("/health")
def health_check():
    """
    Health check endpoint untuk monitoring
    Endpoint ini bisa diakses tanpa token
    Gunakan untuk Docker healthcheck atau uptime monitoring
    """
    return {"status": "healthy", "service": "lapor-api", "timestamp": time.time()}


# ===== VERSION ENDPOINT =====
@app.get("/api/v1/status")
def api_status():
    """Status API dengan informasi lengkap"""
    return {
        "status": "success",
        "api_version": "1.0.0",
        "endpoints": {
            "auth": "/api/auth/",
            "categories": "/api/categories/",
            "reports": "/api/reports/",
            "health": "/health",
        },
    }
