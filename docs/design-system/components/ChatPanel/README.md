# ChatPanel

直播聊天室（第二期）。桌機在直播頁右側，手機預設收起（`defaultOpen`）。

- 最上方 `pinned` 是官方置頂訊息：本時段的組成與 AI 排入理由，標 `pinnedLabel`（「官方」）。
- 訊息只顯示通過審核的；被規則擋下時，`notice` 告訴發言者是哪一類（「這則訊息沒有顯示：疑似個資內容」）。
- 每則最多 100 字、每 5 秒 1 則（`hint` 要寫出來）；未登入顯示「以 CAFECA 登入後聊天」；禁言時 `disabled`，`placeholder` 寫原因與期限。
- 每則訊息滑過時出現檢舉（flag），`onReport` 打開檢舉對話框。
