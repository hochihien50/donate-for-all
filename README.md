# Donate API — nền tảng thanh toán donate đa website

```
Website A / B / C ──▶ Donate API (Flask) ──▶ PaymentProvider (ZaloPay | VietQR | …)
                              ▲                         │ user thanh toán
                              │                         ▼
                        PostgreSQL ◀── xác minh ◀── Payment Webhook
```

## Nguyên tắc an toàn tiền
- Donation luôn được tạo ở `pending`. **Chỉ webhook đã xác minh chữ ký** mới chuyển được sang `completed`.
  `POST /donations/create` trả 400 nếu client gửi trường `status`.
- Webhook kiểm tra: chữ ký (HMAC, so sánh constant-time) → order tồn tại → **amount khớp** → mới hoàn tất.
- Idempotent: `unique(provider, event_id)` ở `webhook_events`, `unique(provider, provider_transaction_id)` và
  `unique(payment_order_id)` ở `transactions`, `unique(provider, provider_order_id)` ở `payment_orders`.
  Webhook gửi lại 2 hay 10 lần vẫn chỉ tạo 1 transaction. Event + transaction + order + donation được commit **trong 1 DB transaction**,
  order bị khóa `SELECT … FOR UPDATE` khi xử lý.
- Provider `sandbox` (giả lập local) **bị từ chối khi `APP_ENV=production`**. Nó vẫn đi qua đường webhook có chữ ký thật.

## API
Header: `Authorization: Bearer <token>` (chủ project) hoặc `X-API-Key: dk_…` (website).

| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/auth/register`, `/auth/login` | – |
| POST/GET | `/api/v1/projects` | Bearer |
| POST | `/api/v1/projects/<id>/api-keys` (key chỉ hiện 1 lần) | Bearer |
| DELETE | `/api/v1/projects/<id>/api-keys/<kid>` | Bearer |
| POST | `/api/v1/donations/create` `{amount, donor_name?, message?, provider?}` | API key |
| GET | `/api/v1/donations/<id>`, `/api/v1/donations` | API key |
| POST | `/api/v1/webhooks/<provider>` | chữ ký provider |

## Thêm provider mới
Tạo class kế thừa `PaymentProvider` (`create_order`, `parse_webhook`), đăng ký trong `app/payments/__init__.py`,
thêm tên vào `ENABLED_PROVIDERS`. Donation/transaction code không đổi.

## Provider
- **ZaloPay**: dùng `ZALOPAY_APP_ID/KEY1/KEY2/CALLBACK_URL`. `PAYMENT_MODE=sandbox` → endpoint sandbox, `live` → production.
  Callback URL = `https://<api>/api/v1/webhooks/zalopay` (cấu hình cả trong dashboard ZaloPay).
- **VietQR**: sinh QR chuyển khoản; tiền về tài khoản ngân hàng của bạn. VietQR/NAPAS không tự gọi webhook, bạn cần một dịch vụ
  báo biến động số dư (SePay, Casso…). Adapter nhận JSON `{id, content, transferAmount, transferType}` ký HMAC-SHA256 ở header
  `X-Signature`; **hãy chỉnh `parse_webhook` cho đúng định dạng nhà cung cấp bạn chọn** và đối chiếu tài liệu của họ.
- Cần xác minh thêm với tài liệu mới nhất của ZaloPay trước khi chạy live (field, endpoint có thể thay đổi).

## Database
- Dữ liệu nằm trong **Render PostgreSQL** (service riêng `donate-db` trong `render.yaml`), không nằm trên filesystem của Flask service.
  Backend chỉ biết `DATABASE_URL`. Production từ chối khởi động nếu không phải PostgreSQL.
- **Deploy có mất dữ liệu không?** Không. Redeploy chỉ thay web service; DB giữ nguyên. Lệnh start chạy `flask db upgrade`
  (chỉ áp migration chưa chạy). Code không có `create_all`, `drop_all`, `DROP`, `DELETE FROM` lúc startup.
- Lưu ý: Postgres gói **free của Render hết hạn sau 30 ngày** → dùng gói trả phí cho tiền thật.

### Migration (thay đổi schema an toàn)
```bash
flask --app wsgi db migrate -m "add column x"   # sinh file, LUÔN đọc lại trước khi commit
flask --app wsgi db upgrade                     # áp dụng
```
Quy tắc: thêm cột mới phải `nullable` hoặc có `server_default`; đổi tên/xóa cột làm 2 bước qua 2 lần deploy
(thêm mới + copy dữ liệu → deploy → xóa cũ); không bao giờ sửa file migration đã chạy ở production; test migration trên bản restore của DB thật.
`downgrade()` của migration đầu tiên xóa bảng — chỉ dùng thủ công khi đã backup.

### Backup / Restore
```bash
# backup (dùng External Database URL của Render)
pg_dump --format=custom --no-owner "$DATABASE_URL" -f donate_$(date +%F).dump
# restore vào DB TRỐNG (khuyến nghị thử trên DB mới trước)
pg_restore --no-owner --clean --if-exists -d "$NEW_DATABASE_URL" donate_2026-10-04.dump
```
Gói Render Postgres trả phí có backup tự động + point-in-time recovery; vẫn nên giữ `pg_dump` định kỳ ngoài Render
(cron/GitHub Actions + lưu S3/R2) và **thử restore định kỳ**. Sau restore, chạy `flask --app wsgi db upgrade`.

## Deploy lên Render
1. Push repo lên GitHub (không commit `.env`). 2. Render → New → Blueprint → chọn repo (đọc `render.yaml`).
3. Điền biến `sync: false`: `ALLOWED_ORIGINS` (vd `https://site-a.com,https://site-b.com`), `ZALOPAY_*`.
`SECRET_KEY` tự sinh; `DATABASE_URL` tự nối từ DB.

## Chạy local & test
```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env     # đặt ENABLED_PROVIDERS=sandbox, DEFAULT_PROVIDER=sandbox
flask --app wsgi db upgrade && flask --app wsgi run
python scripts/sandbox_pay.py <order_id từ response> <amount>   # giả lập gateway gọi webhook có chữ ký
pytest
```
