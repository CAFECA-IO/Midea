# LivePlayer

官方頻道直播。從節目表算出的位置（`offset`）開始播，不能快轉；一部播完（`onEnded`）就向伺服器要下一部。

- 預設靜音自動播放，左下有開聲音與全螢幕按鈕（文字由呼叫端給）。
- 左上 `badge` 放 LIVE 與「Midea 官方頻道」，右上 `topRight` 放 `ViewerCount`。
- 疊加元件（`LiveReactions`、時段結束的 `PollCard`）放在 `children`。
