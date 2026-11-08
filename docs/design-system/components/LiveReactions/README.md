# LiveReactions

直播畫面右下的 5 個即時反應：喜歡（heart）、美（sparkle）、好笑（smile）、感動（tear）、想看更多（plus）。只用線條圖示，不用表情符號。

- 按下後自己的符號用 `amber` 從按鈕上方飄起約 2 秒；其他人的反應來自伺服器每秒的 `burst`（全場每秒最多 20 個）。
- 每人每 2 秒只能按 1 次：按完按鈕會暫時停用 2 秒。
- 一定要給 `toggleLabel` 與 `onToggleHidden`，讓觀眾關掉畫面上的反應；偏好存在瀏覽器。
- `prefers-reduced-motion` 時不飄動，只送出反應。
