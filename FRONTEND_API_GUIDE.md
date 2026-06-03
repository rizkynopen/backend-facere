# 🚀 Panduan Integrasi API Backend FaCare (Untuk Frontend Developer / AI Assistant)

Dokumen ini adalah panduan lengkap dan terbaru untuk mengintegrasikan Frontend dengan Backend API FaCare. Harap baca dengan teliti, terutama di bagian **Alur Autentikasi** dan **Halaman yang Dibutuhkan**.

---

## 📌 Informasi Dasar
- **Base URL Backend:** `http://localhost:8000`
- **Swagger UI (Dokumentasi Interaktif):** `http://localhost:8000/docs`
- **Format Data:** `application/json`
- **Autentikasi:** Menggunakan **Bearer Token**. Untuk endpoint yang membutuhkan login, kirimkan header:
  `Authorization: Bearer <token>`

---

## 🗺️ Daftar Halaman Frontend yang Dibutuhkan

Berikut adalah daftar halaman/komponen yang harus dibuat di sisi Frontend untuk mendukung semua fitur API:

### 1. 🔓 Halaman Public (Tidak perlu login)
- **Halaman Login (`/login`)**: Form email dan password.
- **Halaman Register (`/register`)**: Form email, password, dan nama lengkap.
  > ⚠️ **Catatan UI:** Setelah sukses register, tampilkan pesan: *"Registrasi berhasil! Silakan cek email Anda untuk mengaktifkan akun."* (User belum bisa login sebelum klik link di email).
- **Halaman Lupa Password (`/forgot-password`)**: **[HALAMAN BARU]**
  - Hanya berisi 1 input: `Email` dan tombol "Kirim Link Reset".
- **Halaman Reset Password (`/reset-password`)**: **[HALAMAN BARU]**
  - Berisi input `Password Baru`.
  - Halaman ini akan diakses dari link email. URL-nya akan memiliki token, misalnya: `http://localhost:3000/reset-password#access_token=xxx&refresh_token=yyy`.
  - Frontend harus membaca token dari URL tersebut untuk dikirim ke API.

### 2. 🔐 Halaman Protected (Harus login)
- **Dashboard / Home**: Menampilkan daftar laporan dan peta.
- **Form Buat Laporan**: Input kategori, deskripsi, lokasi, dan upload foto.
- **Profil User & Pengaturan (`/profile`)**:
  - Menampilkan data profil (nama, email).
  - Form untuk mengubah nama lengkap.
  - Form untuk **Ubah Password** (input: password lama & password baru).

---

## 🔑 1. Modul Autentikasi (`/api/auth`)

| Endpoint | Method | Auth | Body Request | Keterangan |
|---|---|---|---|---|
| `/register` | POST | ❌ | `{ email, password, nama_lengkap }` | Daftar akun baru. Password min. 6 karakter. |
| `/login` | POST | ❌ | `{ email, password }` | Login. Simpan `token` dari response ke `localStorage`. |
| `/logout` | POST | ✅ | - | Hapus token di backend. **Frontend WAJIB hapus token di `localStorage` setelah ini!** |
| `/me` | GET | ✅ | - | Ambil data profil user (id, email, nama, role). |
| `/me` | PUT | ✅ | `{ nama_lengkap }` | Update nama lengkap. |
| `/validate-token`| GET | ✅ | - | Cek apakah token masih valid (berguna saat app pertama kali load). |

### 🛠️ Alur Lupa Password & Reset Password
**1. Request Reset (Di halaman `/forgot-password`)**
- Hit `POST /api/auth/forgot-password` dengan body `{ "email": "user@email.com" }`.
- Backend/Supabase akan otomatis mengirim email ke user.

**2. Submit Password Baru (Di halaman `/reset-password`)**
- User klik link dari email dan diarahkan ke frontend.
- Supabase menaruh token di URL fragment (hash), contoh: `.../reset-password#access_token=xxx&refresh_token=yyy`
- Frontend ambil nilai `access_token` dan `refresh_token` dari URL.
- Hit `POST /api/auth/reset-password` dengan body:
  ```json
  {
    "access_token": "xxx",
    "refresh_token": "yyy",
    "new_password": "password_baru"
  }
  ```

**3. Ubah Password Normal (Di halaman Profil)**
- Jika user **ingat password lama** dan ingin ganti, gunakan `POST /api/auth/change-password` dengan body:
  ```json
  {
    "old_password": "...",
    "new_password": "..."
  }
  ```
  *(Harus menyertakan header Authorization Bearer token)*

---

## 📝 2. Modul Laporan (`/api/reports`)

| Endpoint | Method | Auth | Keterangan |
|---|---|---|---|
| `/` | GET | ❌ | Ambil semua laporan. Mendukung pagination: `?page=1&limit=20`. |
| `/` | POST | ✅ | Buat laporan baru. Body: `{ category_id, deskripsi, latitude, longitude, foto_url }`. |
| `/{id}/upvote` | POST | ✅ | Beri upvote. **Catatan:** 1 User hanya bisa 1x upvote per laporan. Jika diulang akan error HTTP 400. |
| `/upload-foto` | POST | ✅ | Upload foto. Gunakan `multipart/form-data` dengan key `file`. Maks 5MB (JPG/PNG/WebP). Response mengembalikan `foto_url`. |
| `/{id}` | PUT | ✅ | **[KHUSUS ADMIN]** Update status laporan. Body: `{ "status": "Menunggu" | "Sedang Diperbaiki" | "Selesai" }`. |

### 📸 Alur Pembuatan Laporan (Frontend)
1. User pilih foto.
2. Hit `POST /api/reports/upload-foto` ➡️ Dapat `foto_url`.
3. Hit `POST /api/reports/` dengan menyertakan `foto_url` yang didapat di step 2.

---

## 🏷️ 3. Modul Kategori (`/api/categories`)

| Endpoint | Method | Auth | Keterangan |
|---|---|---|---|
| `/` | GET | ❌ | Ambil daftar kategori untuk dropdown form laporan. |

---

## 🛑 Panduan Handling Error (Penting untuk AI)
Backend sudah diatur untuk mengembalikan format error standar HTTP:
- **400 Bad Request**: Input tidak valid, format file salah, password lama salah, atau user sudah pernah upvote laporan.
- **401 Unauthorized**: Token tidak ada, tidak valid, atau expired. Frontend **HARUS** otomatis mengarahkan user ke halaman login jika mendapat error ini.
- **403 Forbidden**: User mencoba mengakses fitur Admin.
- **404 Not Found**: Data tidak ditemukan (misal ID laporan salah).
- **422 Unprocessable Entity**: Error validasi data (misal password < 6 karakter).

Baca pesan error detail dari response body JSON: `error.response.data.detail`.
