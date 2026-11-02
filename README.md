# Speech to Text

Ứng dụng web chuyển giọng nói thành văn bản, viết bằng Python (Flask). Ghi âm trực tiếp trên trình duyệt hoặc upload file ghi âm, chọn dùng **SpeechRecognition** (miễn phí) hoặc **Google Cloud Speech-to-Text** (chính thức, cần API Key), và có thể lưu kết quả vào **PostgreSQL**.

## Mục lục

1. [Tính năng](#tính-năng)
2. [Yêu cầu](#yêu-cầu)
3. [Cài đặt](#cài-đặt)
4. [Chạy ứng dụng](#chạy-ứng-dụng)
5. [Sử dụng](#sử-dụng)
6. [Cấu hình Google Cloud Speech-to-Text](#cấu-hình-google-cloud-speech-to-text)
7. [Cấu hình PostgreSQL](#cấu-hình-postgresql)
8. [Xử lý lỗi thường gặp](#xử-lý-lỗi-thường-gặp)
9. [Giới hạn](#giới-hạn)
10. [Bảo mật](#bảo-mật)
11. [Cấu trúc dự án và API](#cấu-trúc-dự-án-và-api)

---

## Tính năng

- **Hai engine nhận diện**
  - **SpeechRecognition**: dùng Google Web Speech API, miễn phí, không cần API Key.
  - **Google Cloud STT**: API chính thức của Google, có dấu câu tự động và độ tin cậy, cần API Key.
- **Ghi âm trực tiếp** trên trình duyệt, có hiển thị sóng âm và bộ đếm thời gian (tự dừng sau 2 phút).
- **Upload file ghi âm** (kéo thả hoặc chọn file): WAV, MP3, FLAC, OGG, OPUS, WEBM, M4A, AAC, AMR — tối đa 100 MB.
- **File dài** được tự động chia thành nhiều đoạn (cắt ở chỗ ngắt hơi) rồi ghép kết quả.
- **12 ngôn ngữ**: Tiếng Việt, English (US/UK), 日本語, 한국어, 中文 (giản thể/phồn thể), Français, Deutsch, Español, ภาษาไทย, Bahasa Indonesia.
- **Kết quả**: sao chép, tải về file `.txt`, lưu vào PostgreSQL.
- **PostgreSQL**: kết nối tới localhost hoặc server khác qua IP, tự động lưu mỗi kết quả, xem lịch sử 20 bản ghi gần nhất.

## Yêu cầu

| Thành phần | Bắt buộc? | Ghi chú |
|---|---|---|
| Python 3.10+ | Có | Đã chạy thử trên Python 3.13 / Windows 11 |
| Trình duyệt hiện đại | Có | Chrome, Edge, Firefox — cần quyền dùng microphone để ghi âm |
| Kết nối Internet | Có | Cả hai engine đều gửi audio lên Google để nhận diện |
| ffmpeg | Tùy | Cần khi upload file không phải WAV (xem bảng bên dưới) |
| PostgreSQL | Tùy | Chỉ cần nếu muốn lưu kết quả |
| Google Cloud API Key | Tùy | Chỉ cần nếu dùng engine Google Cloud STT |

**Khi nào cần ffmpeg?**

| Định dạng file | SpeechRecognition | Google Cloud STT |
|---|---|---|
| WAV (kể cả ghi âm trực tiếp) | Không cần | Không cần |
| MP3, FLAC, OGG, OPUS, WEBM, AMR | **Cần** | Không cần (file dài hơn 1 phút thì **cần** để chia đoạn) |
| M4A, AAC | **Cần** | **Cần** |

## Cài đặt

1. Cài các thư viện Python (mở terminal trong thư mục dự án):

   ```bash
   pip install -r requirements.txt
   ```

2. (Tùy chọn) Cài ffmpeg trên Windows:

   ```bash
   winget install Gyan.FFmpeg
   ```

   Ứng dụng tự tìm ffmpeg trong thư mục cài của winget, nên **không cần** tự thêm vào PATH. Sau khi cài, khởi động lại ứng dụng.

   Các nơi khác cũng được tự nhận: `C:\ffmpeg\bin`, `C:\Program Files\ffmpeg\bin`, Scoop, Chocolatey, hoặc bất kỳ thư mục nào đã có trong PATH.

## Chạy ứng dụng

```bash
python app.py
```

Mở trình duyệt tại **http://localhost:5000**.

- Ứng dụng chỉ nghe trên `127.0.0.1`, nên chỉ truy cập được từ chính máy đang chạy.
- Chế độ debug đang bật: sửa code Python thì server tự nạp lại, không cần chạy lại.
- Để dừng: nhấn `Ctrl+C` trong terminal.
- **Chỉ chạy một server.** Nếu cổng 5000 đã có server khác, ứng dụng sẽ báo `Cổng 5000 đang được dùng` và thoát — hãy tắt server cũ trước.

## Sử dụng

### 1. Chọn engine và ngôn ngữ

Ở thẻ **Công cụ nhận diện**, chọn **SpeechRecognition** hoặc **Google Cloud STT**. Chọn **Ngôn ngữ** của giọng nói trong ô bên dưới.

Engine và ngôn ngữ được ghi nhớ khi bạn bấm **Lưu cài đặt** trong ⚙️.

### 2a. Ghi âm trực tiếp

1. Chọn tab **Ghi âm**.
2. Bấm nút micro tròn (lần đầu trình duyệt sẽ hỏi quyền dùng microphone — chọn **Cho phép**).
3. Nói. Nút chuyển sang màu đỏ, hiện sóng âm và thời gian.
4. Bấm lại để dừng. Kết quả hiện ở thẻ **Kết quả** sau vài giây.

Ghi âm tự dừng sau 2 phút.

### 2b. Upload file ghi âm

1. Chọn tab **Upload file**.
2. Kéo thả file vào khung, hoặc bấm **Chọn file từ máy**.
3. Kiểm tra tên, dung lượng và định dạng file hiện ra. Bấm ✕ để chọn file khác.
4. Bấm **Nhận diện giọng nói**.

File dài có thể mất vài phút. Khi file được chia đoạn, dòng thông tin kết quả sẽ ghi *“Xử lý N đoạn”*.

### 3. Dùng kết quả

| Nút | Chức năng |
|---|---|
| **Sao chép** | Chép văn bản vào clipboard |
| **Tải .txt** | Tải văn bản về máy |
| **Lưu DB** | Lưu vào PostgreSQL (chuyển thành *“Đã lưu #id”* sau khi lưu) |
| **Xóa** | Xóa kết quả đang hiển thị (không xóa trong DB) |

Với Google Cloud STT, dòng thông tin còn hiện **độ tin cậy** (%).

## Cấu hình Google Cloud Speech-to-Text

### Lấy API Key

1. Vào [Google Cloud Console](https://console.cloud.google.com/) và tạo (hoặc chọn) một project.
2. Bật **Cloud Speech-to-Text API** cho project (*APIs & Services → Library*).
3. Liên kết tài khoản thanh toán (billing) cho project — Google yêu cầu điều này để dùng API. Google có hạn mức miễn phí hằng tháng, vượt quá sẽ tính phí theo thời lượng audio; xem bảng giá chính thức của Google để biết con số hiện tại.
4. Vào [*APIs & Services → Credentials*](https://console.cloud.google.com/apis/credentials) → **Create credentials → API key**.
5. Nên giới hạn key (*API restrictions*) chỉ cho **Cloud Speech-to-Text API**.

### Nhập vào ứng dụng

1. Bấm ⚙️ ở góc trên bên phải.
2. Dán key vào ô **Google Cloud Speech-to-Text API Key**.
3. Bấm **Kiểm tra API Key** — phải thấy *“API Key hợp lệ ✓”*.
4. Bấm **Lưu cài đặt**. Ô trạng thái chuyển thành *“✓ API Key đã cấu hình”*.

Sau khi lưu, để trống ô nhập và bấm **Kiểm tra API Key** sẽ kiểm tra key đã lưu.

## Cấu hình PostgreSQL

### Kết nối

1. Bấm ⚙️, kéo xuống phần **PostgreSQL**.
2. Chọn **Localhost** (PostgreSQL trên cùng máy) hoặc **Server khác (IP)** rồi nhập IP/host.
3. Nhập **Port** (mặc định `5432`), **Database**, **User** và **Mật khẩu**.
4. (Tùy chọn) Tích **Tự động lưu mỗi kết quả nhận diện vào DB**.
5. Bấm **Kiểm tra kết nối DB** — phải thấy *“Kết nối thành công ✓ …”*.
6. Bấm **Lưu cài đặt**. ⚠️ Nút kiểm tra **không** lưu cấu hình — phải bấm **Lưu cài đặt**.

Sau khi lưu, thẻ **Lịch sử (PostgreSQL)** xuất hiện dưới thẻ Kết quả. Bấm vào một bản ghi để xem lại nội dung; bấm **Tải lại** để cập nhật danh sách.

Ô mật khẩu luôn để trống khi mở lại Cài đặt. Để trống khi lưu thì **giữ nguyên** mật khẩu cũ; chỉ nhập khi muốn đổi.

### Bảng dữ liệu

Ứng dụng tự tạo bảng `transcripts` (nếu chưa có) trong database đã chọn:

| Cột | Kiểu | Nội dung |
|---|---|---|
| `id` | `SERIAL` | Khóa chính |
| `text` | `TEXT` | Văn bản nhận diện được |
| `engine` | `VARCHAR(64)` | `SpeechRecognition` hoặc `Google Cloud STT` |
| `language` | `VARCHAR(16)` | Mã ngôn ngữ, ví dụ `vi-VN` |
| `source` | `VARCHAR(16)` | `record` (ghi âm) hoặc `upload` |
| `filename` | `VARCHAR(255)` | Tên file (`recording.wav` với ghi âm) |
| `confidence` | `REAL` | Độ tin cậy (%), chỉ có với Google Cloud STT |
| `created_at` | `TIMESTAMPTZ` | Thời điểm lưu |

Tài khoản PostgreSQL cần quyền `CREATE` trên schema (chỉ lần đầu, để tạo bảng), sau đó chỉ cần `SELECT` và `INSERT`.

Muốn dùng một user riêng ít quyền: kết nối lần đầu bằng user có quyền tạo bảng (ví dụ `postgres`) để bảng được tạo, rồi chạy (đổi `stt_app` và mật khẩu theo ý bạn):

```sql
CREATE ROLE stt_app LOGIN PASSWORD 'mat-khau-cua-ban';
GRANT CONNECT ON DATABASE postgres TO stt_app;
GRANT USAGE ON SCHEMA public TO stt_app;
GRANT SELECT, INSERT ON transcripts TO stt_app;
GRANT USAGE ON SEQUENCE transcripts_id_seq TO stt_app;
```

Sau đó đổi **User**/**Mật khẩu** trong Cài đặt sang `stt_app`.

Ví dụ truy vấn:

```sql
SELECT id, created_at, source, language, left(text, 80) AS preview
FROM transcripts
ORDER BY created_at DESC
LIMIT 20;
```

### Kết nối tới PostgreSQL trên máy khác

Trên **máy chạy PostgreSQL**, cần làm 3 việc rồi khởi động lại dịch vụ PostgreSQL:

1. **`postgresql.conf`**: cho phép nhận kết nối từ mạng, ví dụ:

   ```
   listen_addresses = '*'
   ```

2. **`pg_hba.conf`**: cho phép IP (hoặc dải IP) của máy chạy ứng dụng, ví dụ:

   ```
   host    all    all    192.168.1.0/24    scram-sha-256
   ```

3. **Firewall**: mở cổng `5432` (TCP) cho máy chạy ứng dụng.

Nên dùng một user riêng chỉ có quyền trên database này, thay vì user `postgres`.

## Xử lý lỗi thường gặp

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| *Không gọi được server app (Failed to fetch)* / *Lỗi kết nối server* | Server Flask không chạy hoặc vừa bị tắt | Kiểm tra terminal, chạy lại `python app.py`, rồi F5 |
| *Cổng 5000 đang được dùng* | Đã có một server khác đang chạy | Tắt server cũ (`Ctrl+C` trong terminal của nó) rồi chạy lại |
| *Không tìm thấy ffmpeg* | Chưa cài ffmpeg | `winget install Gyan.FFmpeg`, rồi chạy lại ứng dụng |
| *Không đọc được file âm thanh: … End of file / Invalid data …* | File hỏng, rỗng, hoặc ghi chưa xong | Mở thử file bằng trình phát nhạc; xuất lại file ghi âm |
| *Không nhận diện được. Hãy nói to và rõ hơn.* | Không có giọng nói rõ ràng, hoặc chọn sai ngôn ngữ | Kiểm tra microphone, nói gần hơn, chọn đúng ngôn ngữ |
| *Chưa cấu hình Google API Key* | Chọn Google Cloud STT nhưng chưa lưu key | Xem [Cấu hình Google Cloud](#cấu-hình-google-cloud-speech-to-text) |
| *API Key không hợp lệ* | Key sai hoặc đã bị xóa | Tạo key mới trong Google Cloud Console |
| *API Key bị từ chối (chưa bật Cloud Speech-to-Text API …)* | Chưa bật API, chưa có billing, hoặc key bị giới hạn sai API | Bật API, liên kết billing, kiểm tra *API restrictions* |
| *… CERTIFICATE_VERIFY_FAILED …* | Mạng công ty kiểm tra HTTPS bằng chứng chỉ riêng | Đảm bảo đã cài `truststore` (`pip install -r requirements.txt`) |
| *Server đã kết nối được nhưng yêu cầu mật khẩu* | Chưa nhập mật khẩu PostgreSQL | Nhập mật khẩu, bấm **Lưu cài đặt** |
| *Sai user hoặc mật khẩu PostgreSQL* | Sai thông tin đăng nhập | Kiểm tra lại user/mật khẩu (có thể đặt lại trong pgAdmin) |
| *Database không tồn tại* | Tên database sai | Sửa tên, hoặc tạo database: `CREATE DATABASE ten_db;` |
| *Không kết nối được tới server (kiểm tra IP, port, firewall, pg_hba.conf)* | Sai IP/port, PostgreSQL không chạy, hoặc bị chặn | Xem [Kết nối tới PostgreSQL trên máy khác](#kết-nối-tới-postgresql-trên-máy-khác) |
| *Đã nhận diện nhưng lưu DB thất bại: …* | Nhận diện thành công nhưng DB lỗi khi tự động lưu | Văn bản vẫn hiện bình thường; sửa lỗi DB rồi bấm **Lưu DB** |
| *Chưa cấu hình PostgreSQL* (khi bấm Lưu DB) | Chưa lưu cấu hình DB | Xem [Cấu hình PostgreSQL](#cấu-hình-postgresql) |
| *File quá lớn (giới hạn 100MB)* | File vượt 100 MB | Cắt file hoặc chuyển sang định dạng nén (MP3, M4A) |

Trình duyệt không hỏi quyền microphone? Kiểm tra biểu tượng 🔒 trên thanh địa chỉ → cho phép **Microphone** cho `localhost:5000`, rồi F5.

## Giới hạn

- **Cần Internet**: cả hai engine đều gửi audio lên máy chủ Google; không nhận diện được khi offline.
- **SpeechRecognition** dùng API web miễn phí, không chính thức của Google: không có cam kết về độ ổn định hay hạn mức, không có dấu câu và độ tin cậy.
- **File dài** được chia đoạn 20 giây (SpeechRecognition) hoặc 50 giây (Google Cloud) và xử lý lần lượt, nên thời gian chờ tăng theo độ dài file. Một từ nằm đúng chỗ cắt (khi không tìm được chỗ ngắt hơi) có thể bị nhận sai.
- Ghi âm trực tiếp tối đa **2 phút**; upload tối đa **100 MB**.
- Ô kết quả chỉ để đọc — nội dung lưu vào DB đúng như kết quả nhận diện.
- Ứng dụng dùng server phát triển của Flask, phù hợp chạy trên máy cá nhân, **không** dùng để triển khai cho nhiều người.

## Bảo mật

- **API Key Google và mật khẩu PostgreSQL được lưu dạng chữ thường** trong file `config.json` ở thư mục dự án. **Không** chia sẻ, gửi hay commit file này lên Git.
- Mật khẩu PostgreSQL không bao giờ được gửi ngược về trình duyệt.
- Audio được gửi tới Google để nhận diện — cân nhắc trước khi xử lý nội dung nhạy cảm hoặc có thông tin cá nhân.
- Nên giới hạn API Key chỉ cho Cloud Speech-to-Text API, và dùng user PostgreSQL riêng có quyền tối thiểu.

Đặt lại toàn bộ cài đặt: tắt ứng dụng, xóa file `config.json`, rồi chạy lại.

## Cấu trúc dự án và API

```
speech-to-text/
├── app.py              Flask server: nhận diện, chuyển đổi định dạng, chia đoạn, API
├── db.py               Kết nối PostgreSQL, tạo bảng, lưu và đọc bản ghi
├── templates/
│   └── index.html      Giao diện (HTML + CSS + JavaScript)
├── requirements.txt    Thư viện Python
└── config.json         Cài đặt (tự tạo khi bấm Lưu cài đặt — chứa thông tin bí mật)
```

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| `GET` | `/` | Giao diện web |
| `GET` | `/api/settings` | Đọc cài đặt (không gồm API Key và mật khẩu) |
| `POST` | `/api/settings` | Lưu cài đặt (`engine`, `language`, `google_api_key`, `db`) |
| `POST` | `/api/test-api-key` | Kiểm tra Google API Key (gửi `{"api_key": "..."}` hoặc `{}` để thử key đã lưu) |
| `POST` | `/api/db/test` | Kiểm tra kết nối PostgreSQL (không lưu cài đặt) |
| `POST` | `/api/transcribe` | Nhận diện — form-data: `audio` (file), `engine`, `language`, `source` (`record`/`upload`) |
| `POST` | `/api/transcripts` | Lưu một kết quả vào PostgreSQL |
| `GET` | `/api/transcripts?limit=20` | Đọc lịch sử (tối đa 100 bản ghi) |
