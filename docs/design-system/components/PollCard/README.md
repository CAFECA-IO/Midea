# PollCard

「觀眾決定」投票與時段結束投票。

- `variant="tile"`：首頁首屏的琥珀色磚（1×2），週一到週四取代「本週主題」；截止後首頁改回 `ThemeTile`，寫出投票結果。
- `variant="full"`：節目表頁上方，候選各附 3 張代表影片劇照，`allowChange` 讓觀眾在截止前改投。
- `variant="overlay"`：直播時段最後 60 秒疊在畫面左下：「下週還想看「…」嗎？」想／不想。
- 投票前不顯示比例；投過或截止後才顯示 `share`（%）。投票不要求 KYC 等級，但結果依等級分開統計（API 的 `by_kyc`）。
- 未登入時 `cta` 寫「投這一個（以 CAFECA 登入）」，按下先開 `SignInDialog`，登入後自動送出。
