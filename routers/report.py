from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import Optional
from database import supabase
from schemas.schema import (
    LaporanBaru,
    UpdateStatusLaporan,
)
from routers.auth import get_current_user
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Reports"])

# Konstanta untuk validasi file upload
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


# 1. Jalur untuk Menerima Laporan (Create) - HANYA USER YANG LOGIN
@router.post("/")
async def buat_laporan(data: LaporanBaru, current_user=Depends(get_current_user)):
    try:
        # current_user berisi data user yang sudah terverifikasi tokennya
        # Gunakan user_id dari token, bukan dari request body (lebih aman)
        user_id = current_user.user.id

        # Memasukkan data laporan ke tabel 'reports'
        respon = (
            supabase.table("reports")
            .insert(
                {
                    "user_id": user_id,  # Ambil dari token, bukan dari body
                    "category_id": data.category_id,
                    "deskripsi": data.deskripsi,
                    "latitude": data.latitude,
                    "longitude": data.longitude,
                    "foto_url": data.foto_url,
                    "status": "Menunggu",  # Status default saat laporan baru masuk
                }
            )
            .execute()
        )

        return {"pesan": "Laporan berhasil dikirim!", "data": respon.data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Buat laporan gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat membuat laporan"
        )


# 2. Jalur untuk Menampilkan Semua Laporan (Read / untuk Heatmap Peta) - dengan Pagination
@router.get("/")
def ambil_semua_laporan(page: int = 1, limit: int = 20):
    """
    Mengambil daftar laporan dengan pagination.
    - page: Nomor halaman (default: 1)
    - limit: Jumlah data per halaman (default: 20, max: 100)
    """
    try:
        # Batasi limit maksimal 100 untuk mencegah query terlalu besar
        if limit > 100:
            limit = 100
        if page < 1:
            page = 1

        offset = (page - 1) * limit

        # Menarik data laporan beserta nama kategori dan nama pelapornya
        respon = (
            supabase.table("reports")
            .select(
                "*, categories(nama_kategori), users(nama_lengkap)", count="exact"
            )
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {
            "data": respon.data,
            "total": respon.count,
            "page": page,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"Ambil semua laporan gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat mengambil data laporan"
        )


# 3. Jalur khusus Admin untuk mengubah status laporan - HANYA ADMIN YANG LOGIN
@router.put("/{report_id}")
async def update_status_laporan(
    report_id: int, data: UpdateStatusLaporan, current_user=Depends(get_current_user)
):
    try:
        # 1. Ambil user_id dari token (lebih aman)
        user_id = current_user.user.id

        # 2. CEK KEAMANAN: Apakah user ini adalah admin?
        cek_admin = supabase.table("users").select("role").eq("id", user_id).execute()

        # Jika user tidak ditemukan ATAU rolenya bukan admin, tolak!
        if len(cek_admin.data) == 0 or cek_admin.data[0]["role"] != "admin":
            raise HTTPException(
                status_code=403,
                detail="Akses Ditolak! Hanya Admin yang boleh mengubah status.",
            )

        # 3. Jika dia terbukti admin, baru jalankan update status
        # Catatan: status sudah divalidasi oleh schema Literal["Menunggu", "Sedang Diperbaiki", "Selesai"]
        respon = (
            supabase.table("reports")
            .update({"status": data.status})
            .eq("id", report_id)
            .execute()
        )

        if len(respon.data) == 0:
            raise HTTPException(status_code=404, detail="ID Laporan tidak ditemukan")

        return {"pesan": "Status laporan berhasil diperbarui!", "data": respon.data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update status laporan gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Terjadi kesalahan saat memperbarui status laporan",
        )


# 4. Jalur untuk memberikan Upvote (Dukungan) pada laporan - HANYA USER YANG LOGIN
@router.post("/{report_id}/upvote")
async def upvote_laporan(report_id: int, current_user=Depends(get_current_user)):
    try:
        user_id = current_user.user.id

        # Cek apakah laporan ada
        laporan = (
            supabase.table("reports")
            .select("id")
            .eq("id", report_id)
            .execute()
        )

        if len(laporan.data) == 0:
            raise HTTPException(status_code=404, detail="ID Laporan tidak ditemukan")

        # Cek apakah user sudah pernah upvote laporan ini
        existing_upvote = (
            supabase.table("report_upvotes")
            .select("*")
            .eq("user_id", user_id)
            .eq("report_id", report_id)
            .execute()
        )

        if len(existing_upvote.data) > 0:
            raise HTTPException(
                status_code=400,
                detail="Anda sudah pernah memberikan upvote pada laporan ini",
            )

        # Catat upvote di tabel report_upvotes (mencegah double upvote)
        supabase.table("report_upvotes").insert(
            {"user_id": user_id, "report_id": report_id}
        ).execute()

        # Gunakan RPC untuk atomic increment (mencegah race condition)
        supabase.rpc("increment_upvote", {"row_id": report_id}).execute()

        # Ambil jumlah upvote terbaru
        updated = (
            supabase.table("reports")
            .select("jumlah_upvote")
            .eq("id", report_id)
            .execute()
        )

        return {
            "pesan": "Berhasil memberikan upvote!",
            "jumlah_upvote_baru": updated.data[0]["jumlah_upvote"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upvote gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat memberikan upvote"
        )


# 5. Jalur untuk Upload Foto Laporan - HANYA USER YANG LOGIN
@router.post("/upload-foto")
async def upload_foto(
    file: UploadFile = File(...), current_user=Depends(get_current_user)
):
    try:
        # a. Validasi ekstensi file
        if not file.filename or "." not in file.filename:
            raise HTTPException(
                status_code=400, detail="Nama file tidak valid"
            )

        ekstensi_file = file.filename.split(".")[-1].lower()
        if ekstensi_file not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Format file tidak didukung. Gunakan: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        # b. Validasi MIME type
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Tipe file tidak valid. Hanya gambar JPG, PNG, dan WebP yang diperbolehkan.",
            )

        # c. Baca isi file dan validasi ukuran
        isi_file = await file.read()
        if len(isi_file) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Ukuran file terlalu besar. Maksimal {MAX_FILE_SIZE // (1024 * 1024)} MB",
            )

        # d. Buat nama file unik agar tidak tertimpa jika ada nama file yang sama
        nama_file_unik = f"{uuid.uuid4()}.{ekstensi_file}"

        # e. Upload ke Supabase Storage (ke dalam bucket 'laporan')
        supabase.storage.from_("laporan").upload(
            path=nama_file_unik,
            file=isi_file,
            file_options={"content-type": file.content_type},
        )

        # f. Dapatkan URL Publik dari foto yang baru di-upload
        url_publik = supabase.storage.from_("laporan").get_public_url(nama_file_unik)

        return {"pesan": "Foto berhasil diunggah!", "foto_url": url_publik}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload foto gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat mengunggah foto"
        )
