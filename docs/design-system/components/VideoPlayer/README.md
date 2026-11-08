# VideoPlayer

單一影片播放：原生控制列、字幕軌（`captions`，WebVTT）、直式影片（`vertical`）。

- `highlights` 是直播時觀眾最有反應的片段（峰值前後 7 秒），在播放器下方的進度條上用圓點標出，點一下跳過去；`highlightsLabel` 說明圓點的意思。
- `onProgress(seconds, duration, ended)` 回報看到的最遠秒數；看完 90% 以上才算「完整看完」（最多人看只算這個）。
