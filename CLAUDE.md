# Midea — 專案規則

## 頁面與介面：先讀設計系統

規劃、設計或開發任何頁面與介面（midea.cafeca.io 網站、分鏡看板、廣告片尾卡、動態圖形範本等）時，**動手前先讀 `docs/design-system/`**：

1. `docs/design-system/README.md`：設計語言（原則、文案、色彩、字體、間距、影像、狀態、登入、無障礙）。
2. `docs/design-system/layout.md`：Bento 格線與首頁區塊順序。
3. `docs/design-system/components-plan.md`：已有哪些元件、哪些在規劃中。

規則：

- 顏色、字級、間距、圓角一律用 `docs/design-system/tokens.css` 的 CSS 變數（來源是 `tokens.json`），不寫死色碼。
- 先用現有元件（`docs/design-system/components/`）；沒有的元件，照 `components-plan.md` 的名稱與 API 約定新增，完成後更新該檔與元件說明。
- 改 token 只改 `tokens.json`，再跑 `python scripts/gen_tokens_css.py`。
- 文案照設計語言的「文案」一節：繁體中文、平實、24 小時制、片名保留原文、演員寫姓名加 @代號、頁尾保留「演員皆為虛擬角色」。
- 登入只用 CAFECA（「以 CAFECA 登入」），不做自有帳號密碼。
