# SignInDialog

以 CAFECA 登入的對話框，三種方式：

1. **彈出視窗**（桌機）：`onPopup` 必須直接在點擊事件裡呼叫 CAFECA SDK 的 `signIn`，否則瀏覽器會擋。
2. **在這個分頁登入**（手機、App 內建瀏覽器）：`onRedirect` 用 `redirect` 模式，回到 `/auth/callback`。
3. **QR 碼**（用手機登入這台電腦）：`qr` 放 `authLink({ mode: 'post' })` 產生的 QR；頁面輪詢伺服器取結果。

說明文字固定說三件事：用通行金鑰、不需要密碼、不必另外註冊；`footer` 說明 Midea 會收到哪些資料。錯誤放在 `error`（例：瀏覽器擋下了登入視窗）。
