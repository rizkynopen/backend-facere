from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import supabase
from schemas.schema import (
    RegisterUser,
    LoginUser,
    ChangePasswordRequest,
    UpdateProfileRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from datetime import datetime
import logging
import os
from dotenv import load_dotenv

# Setup logging
logger = logging.getLogger(__name__)

load_dotenv()
SECRET_KEY = os.getenv("SUPABASE_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")  # URL Frontend

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Security scheme untuk Swagger UI (tombol Authorize)
security = HTTPBearer()


# Function untuk verify token dari Authorization header
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Dependency injection untuk verify token.
    Swagger UI akan otomatis menampilkan tombol 🔓 Authorize.
    """
    token = credentials.credentials

    # Verify token menggunakan Supabase
    try:
        user = supabase.auth.get_user(token)
        return user
    except Exception:
        raise HTTPException(
            status_code=401, detail="Token tidak valid atau sudah expired"
        )


# 1. Jalur untuk Mendaftar (Register)
@router.post("/register")
def register(user_data: RegisterUser):
    try:
        # a. Mendaftarkan email & password ke sistem Auth bawaan Supabase
        auth_response = supabase.auth.sign_up(
            {
                "email": user_data.email,
                "password": user_data.password,
                "options": {
                    "email_redirect_to": f"{FRONTEND_URL}/verify-email"
                },
            }
        )

        # b. Mengambil ID unik yang baru saja dibuat Supabase
        user_id = auth_response.user.id

        # c. Menyimpan nama_lengkap ke tabel 'users' milik kita
        supabase.table("users").insert(
            {
                "id": user_id,
                "nama_lengkap": user_data.nama_lengkap,
                "role": "masyarakat",  # Nilai awal selalu masyarakat
            }
        ).execute()

        return {
            "pesan": "Registrasi berhasil! Silakan cek email Anda untuk verifikasi akun.",
            "user_id": user_id,
            "email_verifikasi": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Registrasi gagal. Email mungkin sudah terdaftar atau password terlalu pendek.",
        )


# 2. Jalur untuk Masuk (Login)
@router.post("/login")
def login(user_data: LoginUser):
    try:
        # Mengecek email dan password ke Supabase
        auth_response = supabase.auth.sign_in_with_password(
            {"email": user_data.email, "password": user_data.password}
        )

        # Jika berhasil, Supabase akan memberikan Token (kunci masuk)
        token = auth_response.session.access_token
        user_id = auth_response.user.id

        logger.info(f"✓ Login berhasil untuk user {user_data.email}")

        return {
            "pesan": "Login berhasil!",
            "token": token,
            "user_id": user_id,
            "expires_in": 3600,  # 1 jam (sesuaikan dengan Supabase config)
        }
    except Exception as e:
        logger.error(f"✗ Login gagal: {str(e)}")
        raise HTTPException(status_code=400, detail="Email atau password salah")


# 3. Jalur untuk Logout
@router.post("/logout")
async def logout(current_user=Depends(get_current_user)):
    """
    Logout user. Invalidate token di Supabase.
    Frontend WAJIB menghapus token dari localStorage/sessionStorage setelah endpoint ini dipanggil.
    """
    try:
        # Supabase sign out (invalidate session)
        supabase.auth.sign_out()

        logger.info("✓ Logout berhasil")

        return {
            "pesan": "Logout berhasil! Silakan tutup browser atau refresh halaman.",
            "status": "success",
        }
    except Exception as e:
        logger.error(f"✗ Logout gagal: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Terjadi kesalahan saat logout")


# 4. Jalur untuk Validasi Token (Check apakah session masih valid)
@router.get("/validate-token")
async def validate_token(current_user=Depends(get_current_user)):
    """
    Validasi token yang sedang aktif.
    Endpoint ini bisa dipanggil secara berkala dari frontend untuk memastikan session masih valid.
    Jika token expired atau invalid, akan return 401 Unauthorized.

    Response: 200 = Token valid, 401 = Token expired/invalid
    """
    try:
        user_id = current_user.user.id
        user_email = current_user.user.email

        return {
            "status": "valid",
            "message": "Token masih valid",
            "user_id": user_id,
            "email": user_email,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Token tidak valid")


# 5. Jalur untuk Mendapatkan Data User Saat Ini
@router.get("/me")
async def get_profile(current_user=Depends(get_current_user)):
    """
    Mendapatkan profil user yang sedang login
    """
    try:
        user_id = current_user.user.id
        user_email = current_user.user.email  # Email dari token Supabase

        user_data = (
            supabase.table("users")
            .select("id, nama_lengkap, role")
            .eq("id", user_id)
            .execute()
        )

        if len(user_data.data) == 0:
            raise HTTPException(status_code=404, detail="User tidak ditemukan")

        # Gabungkan email dari token dengan data dari tabel users
        profile = user_data.data[0]
        profile["email"] = user_email

        return {"pesan": "Profil user berhasil diambil", "data": profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat mengambil profil"
        )


# 6. Jalur untuk Update Profil User
@router.put("/me")
async def update_profile(
    data: UpdateProfileRequest, current_user=Depends(get_current_user)
):
    """
    Update profil user (saat ini hanya bisa update nama_lengkap).
    Kirim data dalam request body JSON: {"nama_lengkap": "Nama Baru"}
    """
    try:
        user_id = current_user.user.id

        # Update ke database
        updated_user = (
            supabase.table("users")
            .update({"nama_lengkap": data.nama_lengkap})
            .eq("id", user_id)
            .execute()
        )

        return {"pesan": "Profil berhasil diperbarui!", "data": updated_user.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update profile gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat memperbarui profil"
        )


# 7. Jalur untuk Change Password
@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest, current_user=Depends(get_current_user)
):
    """
    Mengubah password user.
    Kirim data dalam request body JSON: {"old_password": "...", "new_password": "..."}
    """
    try:
        # Validasi password baru tidak sama dengan password lama
        if data.old_password == data.new_password:
            raise HTTPException(
                status_code=400,
                detail="Password baru tidak boleh sama dengan password lama",
            )

        # Verifikasi password lama dengan mencoba login ulang
        user_email = current_user.user.email
        try:
            supabase.auth.sign_in_with_password(
                {"email": user_email, "password": data.old_password}
            )
        except Exception:
            raise HTTPException(
                status_code=400, detail="Password lama tidak benar"
            )

        # Update password di Supabase
        supabase.auth.update_user({"password": data.new_password})

        return {"pesan": "Password berhasil diubah!"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Terjadi kesalahan saat mengubah password"
        )


# 8. Jalur untuk mendapatkan info session yang aktif (untuk frontend)
@router.get("/session-info")
async def get_session_info(current_user=Depends(get_current_user)):
    """
    Mendapatkan informasi session yang sedang berjalan.
    Berguna untuk frontend menampilkan informasi login user.
    """
    try:
        user_id = current_user.user.id
        user_email = current_user.user.email  # Email dari token Supabase

        user_data = (
            supabase.table("users")
            .select("id, nama_lengkap, role")
            .eq("id", user_id)
            .execute()
        )

        if len(user_data.data) == 0:
            raise HTTPException(status_code=404, detail="User tidak ditemukan")

        # Gabungkan email dari token dengan data dari tabel users
        user_info = user_data.data[0]
        user_info["email"] = user_email

        return {
            "status": "logged_in",
            "user": user_info,
            "login_timestamp": datetime.now().isoformat(),
            "message": "User sedang login",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session info gagal: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail="Session tidak valid")


# 9. Jalur untuk Forgot Password (Lupa Password)
@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """
    Kirim email reset password ke user.
    User TIDAK perlu login untuk mengakses endpoint ini.
    Supabase akan mengirim email berisi link reset password.
    """
    try:
        # Supabase mengirim email reset password
        # redirect_to adalah URL halaman frontend untuk form reset password
        supabase.auth.reset_password_for_email(
            data.email,
            options={
                "redirect_to": f"{FRONTEND_URL}/reset-password"
            },
        )

        # Selalu return sukses (jangan kasih tahu apakah email terdaftar atau tidak)
        # Ini untuk mencegah email enumeration attack
        return {
            "pesan": "Jika email terdaftar, link reset password telah dikirim. Silakan cek inbox dan folder spam Anda.",
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Forgot password gagal: {str(e)}", exc_info=True)
        # Tetap return sukses untuk keamanan (jangan expose apakah email ada atau tidak)
        return {
            "pesan": "Jika email terdaftar, link reset password telah dikirim. Silakan cek inbox dan folder spam Anda.",
            "status": "success",
        }


# 10. Jalur untuk Reset Password (Set Password Baru dari Link Email)
@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """
    Reset password menggunakan token yang diterima dari email.
    Frontend mengambil access_token dan refresh_token dari URL callback,
    lalu mengirimnya bersama password baru ke endpoint ini.

    Alur:
    1. User klik link di email → diarahkan ke frontend (misal: /reset-password?access_token=xxx&refresh_token=yyy)
    2. Frontend menampilkan form input password baru
    3. Frontend kirim access_token, refresh_token, dan new_password ke endpoint ini
    """
    try:
        # Set session menggunakan token dari email reset
        session = supabase.auth.set_session(
            access_token=data.access_token,
            refresh_token=data.refresh_token,
        )

        # Update password user
        supabase.auth.update_user({"password": data.new_password})

        return {
            "pesan": "Password berhasil direset! Silakan login dengan password baru Anda.",
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Reset password gagal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Token reset password tidak valid atau sudah expired. Silakan request ulang.",
        )
