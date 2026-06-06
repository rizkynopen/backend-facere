from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from typing import Optional, Literal
from database import supabase
from schemas.schema import (
    LaporanBaru,
    UpdateStatusLaporan,
)
from routers.auth import get_current_user
from fpdf import FPDF
from io import BytesIO
from datetime import datetime
import httpx
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


# 6. Jalur untuk Export Laporan ke PDF - HANYA ADMIN
@router.get("/export-pdf")
async def export_laporan_pdf(
    status: Literal["Menunggu", "Sedang Diperbaiki", "Selesai"] = "Menunggu",
    current_user=Depends(get_current_user),
):
    """
    Export laporan ke file PDF berdasarkan status.
    Hanya bisa diakses oleh Admin.
    Filter status: Menunggu, Sedang Diperbaiki, atau Selesai.
    """
    try:
        # 1. Cek apakah user adalah admin
        user_id = current_user.user.id
        cek_admin = supabase.table("users").select("role").eq("id", user_id).execute()

        if len(cek_admin.data) == 0 or cek_admin.data[0]["role"] != "admin":
            raise HTTPException(
                status_code=403,
                detail="Akses Ditolak! Hanya Admin yang bisa mengekspor laporan.",
            )

        # 2. Ambil data laporan berdasarkan status
        laporan_list = (
            supabase.table("reports")
            .select("*, categories(nama_kategori), users(nama_lengkap)")
            .eq("status", status)
            .order("created_at", desc=True)
            .execute()
        )

        if len(laporan_list.data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Tidak ada laporan dengan status '{status}'.",
            )

        # 3. Buat dokumen PDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)

        # === HALAMAN SAMPUL ===
        pdf.add_page()

        # Judul utama
        pdf.set_font("Helvetica", "B", 20)
        pdf.ln(30)
        pdf.cell(0, 12, "LAPORAN FASILITAS UMUM", ln=True, align="C")
        pdf.cell(0, 12, "KOTA PEKANBARU", ln=True, align="C")
        pdf.ln(10)

        # Garis pemisah
        pdf.set_draw_color(50, 50, 50)
        pdf.set_line_width(0.5)
        pdf.line(40, pdf.get_y(), 170, pdf.get_y())
        pdf.ln(10)

        # Info status dan tanggal
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 8, f"Status Laporan: {status}", ln=True, align="C")
        pdf.cell(
            0,
            8,
            f"Tanggal Cetak: {datetime.now().strftime('%d-%m-%Y, %H:%M WIB')}",
            ln=True,
            align="C",
        )
        pdf.cell(
            0, 8, f"Total Laporan: {len(laporan_list.data)}", ln=True, align="C"
        )
        pdf.ln(15)

        # Garis pemisah bawah
        pdf.line(40, pdf.get_y(), 170, pdf.get_y())
        pdf.ln(5)

        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(
            0,
            8,
            "Dokumen ini digenerate otomatis oleh sistem Backend API FaCare",
            ln=True,
            align="C",
        )

        # === HALAMAN ISI: DETAIL SETIAP LAPORAN ===
        for i, laporan in enumerate(laporan_list.data, 1):
            pdf.add_page()

            # Ambil data dari relasi tabel
            kategori = (
                laporan.get("categories", {}).get("nama_kategori", "Tidak diketahui")
                if laporan.get("categories")
                else "Tidak diketahui"
            )
            pelapor = (
                laporan.get("users", {}).get("nama_lengkap", "Anonim")
                if laporan.get("users")
                else "Anonim"
            )
            deskripsi = laporan.get("deskripsi", "-")
            latitude = laporan.get("latitude", 0)
            longitude = laporan.get("longitude", 0)
            foto_url = laporan.get("foto_url", None)
            created_at = laporan.get("created_at", "-")
            jumlah_upvote = laporan.get("jumlah_upvote", 0)

            # Header laporan
            pdf.set_fill_color(44, 62, 80)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 12, f"  Laporan #{i}", ln=True, fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(5)

            # Detail laporan dalam format tabel
            pdf.set_font("Helvetica", "B", 10)
            col_label = 45
            col_value = 0

            # Baris: Kategori
            pdf.cell(col_label, 8, "Kategori", border=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(col_value, 8, f"  {kategori}", border=1, ln=True)

            # Baris: Pelapor
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col_label, 8, "Pelapor", border=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(col_value, 8, f"  {pelapor}", border=1, ln=True)

            # Baris: Koordinat
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col_label, 8, "Koordinat", border=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(col_value, 8, f"  {latitude}, {longitude}", border=1, ln=True)

            # Baris: Status
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col_label, 8, "Status", border=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(col_value, 8, f"  {status}", border=1, ln=True)

            # Baris: Jumlah Upvote
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col_label, 8, "Jumlah Upvote", border=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(col_value, 8, f"  {jumlah_upvote}", border=1, ln=True)

            # Baris: Tanggal Lapor
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col_label, 8, "Tanggal Lapor", border=1)
            pdf.set_font("Helvetica", "", 10)
            tanggal_format = str(created_at)[:10] if created_at else "-"
            pdf.cell(col_value, 8, f"  {tanggal_format}", border=1, ln=True)

            pdf.ln(5)

            # Deskripsi
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 8, "Deskripsi:", ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, deskripsi)
            pdf.ln(5)

            # Foto laporan (download dan embed ke PDF)
            if foto_url:
                try:
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(0, 8, "Foto Laporan:", ln=True)
                    async with httpx.AsyncClient() as client:
                        img_response = await client.get(foto_url, timeout=10)
                        if img_response.status_code == 200:
                            img_bytes = BytesIO(img_response.content)
                            pdf.image(img_bytes, x=10, w=90)
                            pdf.ln(5)
                        else:
                            pdf.set_font("Helvetica", "I", 9)
                            pdf.cell(0, 7, "[Foto tidak dapat dimuat]", ln=True)
                except Exception:
                    pdf.set_font("Helvetica", "I", 9)
                    pdf.cell(0, 7, "[Foto tidak dapat dimuat]", ln=True)

        # 4. Generate output PDF dan kirim sebagai response
        pdf_output = pdf.output()

        # Buat nama file yang rapi
        status_clean = status.lower().replace(" ", "_")
        filename = f"laporan_{status_clean}_{datetime.now().strftime('%Y%m%d')}.pdf"

        logger.info(
            f"PDF berhasil digenerate: {filename} ({len(laporan_list.data)} laporan)"
        )

        return Response(
            content=bytes(pdf_output),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export PDF gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Terjadi kesalahan saat mengekspor laporan ke PDF",
        )
