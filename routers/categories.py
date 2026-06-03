# Isi dari routers/categories.py
from fastapi import APIRouter, HTTPException
from database import supabase
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/categories", tags=["Categories"])


# Jalur untuk Frontend mengambil daftar kategori untuk dropdown
@router.get("/")
def ambil_semua_kategori():
    try:
        respon = supabase.table("categories").select("*").execute()
        return {"data": respon.data}
    except Exception as e:
        logger.error(f"Ambil kategori gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat mengambil data kategori"
        )

