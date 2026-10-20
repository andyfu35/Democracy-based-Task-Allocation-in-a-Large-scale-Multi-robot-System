# P2H Figure 1 — 獨立正式實驗稽核報告

核對日期：2026-10-20。基礎資料：使用者提供的 `p2h_interactive_figure1_100seed.zip`。本報告只是資料稽核，不修改任何正式實驗數值或 GitHub 原生演算法。

- 原始正式實驗來源 Git SHA：`a54a13d454bb07cdfa9a20aa53753f9b6f61039d`
- 原始 ZIP SHA256：`171508bd596060352c7d8a7493c2724e293225b17c9a7af2390713770490373f`
- 原始 per-seed CSV SHA256：`fe2f6dd92ca6fd66da272addde4380fdb55a06b0a045b0d8e6b76894513e61a6`
- **正式原始案例 2,000 筆、統計 20 組；獨立檢查 266,856 項，失敗 0 項。**
- 自動稽核重建 E0 原始 seeded 座標，使用 `random.Random(seed)`、Euclidean `math.dist` 和 task-ID-order Greedy 重新計算 100 個 full-info 成本，逐一比對所有 2,000 筆 source sha、scene sha、實際完成配對成本和成功後成本差異。所用方法來自同分支 `democracy_mrta.scenario.generate_e0_scenario` 的原始可見演算法。
- 驗證了原始 ZIP manifest 內全部四個 SHA256、per-seed 排序 10 loss×100 seeds×2 modes、單機器人 capacity=1、每個任務只嘗試一次、Proposed 每輪 0/1 Commit、中央只能選實際收到 Cost 的機器人、每個 assignment 的實際 SEND/Commit 日期因果順序、Cost 僅一次、全部物理 SEND 的 Bytes（包含掉包）、原始 vs summary 每個欄位與所有成功樣本的條件式成本。
- 正式圖一可解析為 1800×1120 SVG，底部無註釋文字；**71 個實際 plotted 數據點的 tooltip 各自可由對應 summary CSV 值以四位小數重算**。

## 正式結果（每個掉包率各 100 Seeds）

P/C = Proposed / Baseline Centralized。完整成功率是每個 Seed 必須完整分配 100 任務的比例。集中式在 PL10～90 完整成功 Seed=0，因此 **集中式成本差異全部為缺值（不是 0%）**。

| Loss | 完整成功率 P/C | 集中式平均任務配置率 | Proposed 成本差異¹ | 模擬停時 P/C (秒) | 發送量 P/C (kB) |
|---:|---:|---:|---:|---:|---:|
| 0% | 100% / 100% | 100.00% | +0.00% | 16.47 / 7.48 | 249.25 / 89.23 |
| 10% | 100% / 0% | 90.29% | +0.34% | 18.58 / 6.83 | 252.81 / 88.73 |
| 20% | 100% / 0% | 80.20% | +0.60% | 19.43 / 6.09 | 254.26 / 88.20 |
| 30% | 100% / 0% | 70.33% | +0.85% | 20.13 / 5.38 | 255.50 / 87.69 |
| 40% | 100% / 0% | 60.12% | +2.33% | 20.80 / 4.72 | 256.64 / 87.16 |
| 50% | 100% / 0% | 50.06% | +4.77% | 21.47 / 4.01 | 257.64 / 86.64 |
| 60% | 100% / 0% | 40.41% | +9.62% | 22.33 / 3.31 | 258.49 / 86.13 |
| 70% | 100% / 0% | 30.74% | +17.93% | 23.30 / 2.69 | 258.76 / 85.63 |
| 80% | 100% / 0% | 20.80% | +35.88% | 24.48 / 2.00 | 257.76 / 85.11 |
| 90% | 100% / 0% | 10.54% | +79.26% | 27.50 / 1.37 | 254.23 / 84.58 |

¹ 成本差異相對同 Seed 完整資訊 **Task-ID-Ordered Greedy**，只對完成全部 100 個任務的 Seeds 計算。Proposed 10/10 Loss levels 都 100 個成功 Seeds；集中式只有 Loss=0 時完整成功（100 Seeds；成本差異 0%）。

## 關鍵解讀與不應誤寫的結論

1. **Proposed 100% 完成並非封包完全可靠。** 原生 `greedy_task` 使用本地可見 Cost 選當前任務候選者；本地自投票不經遠端丟包，而 `received_plurality` 的公告資格只要求一張正票。永遠至少存在一台全體在役機器人中目前真實成本最低的候選人；若它的本地視圖找不到更便宜的機器人（必然），它便可以自投一票。再加上本實驗可靠的 Score/Commit，故此模型有特別強的逐任務完成保障。這不能外推至 Score/Commit 也掉包、嚴格過半門檻、沒有本地自投票或實際 Wi-Fi 硬體。
2. **此集中式基準只是一個特定 one-shot Cost 單點接收模型。** 99 台遠端機器人各向協調者發送一次 Cost；任何沒收到的資料都無法用於本次 Greedy，且沒有重傳。因此 PL10~90 完整成功率 0%，不是「所有集中式方法皆 0%」。該協調者的逐任務 Assignment/Commit 紀錄與任務數一致，且不使用丟失 Cost。
3. **失敗停止時間不可當作成功完成時間。** 在 PL90 Baseline Centralized 平均只完成 10.54% 任務，因此 1.37 秒是完成部分分配後的停止時間，不能宣稱比 Proposed 完整完成 100 個任務的 27.50 秒快二十倍。兩者在 PL0 同樣成功時，Proposed 16.47 秒、249.25 kB，相對 Baseline 7.48 秒、89.23 kB，約 2.20 倍時間與 2.79 倍發送量。這是額外多輪 Voting 的成本。
4. **高掉包成本顯著惡化。** PL50 Proposed 成本差異 +4.77%；PL70 +17.93%；PL90 平均 **+79.26%**、中位數 **+75.44%**、單 Seed 分布 +37.12% 至 +184.38%。這不是遺失成本的「補零」造成：100 個 Seeds 均有原生完整分配並實際依場景座標重新驗證。
5. **圖一與圖二成本的 0% 基準不同。** 圖一用 Task-Ordered Greedy；舊圖二用 Global Minimum-Pair Greedy。絕對不能把「+79.26% vs Task-Ordered」和舊圖二 Proposed「+5.04% vs Global」直接視為相同成本基準下的效能差。
6. **對照舊圖二需要控制更多因素。** 舊圖二的 Proposed 不只通訊回合不同，也採 Global minimum-pair Greedy（圖一採 Task-ID Greedy）；不能把跨圖性能差完全歸因於 Voting 次序。

### 僅供方法學稽核：同一 Global Greedy 基準下重新評估新圖一

使用以前通過原始 ZIP SHA 校驗的 P2G per-seed centralized_retry 資料中的「同一 Seed 完整資訊 Global Greedy cost」作**獨立離線參考**，並檢查 E0 scene SHA 完全一致，對目前 P2H Proposed **原始絕對總距離**計算相同的基準（未回饋至訓練或演算法，也未修改圖一）：

| Loss | 新逐任務 Proposed 對 Global Greedy 成本差異 | 全資訊 Task-Ordered Greedy 對 Global Greedy 差異 |
|---:|---:|---:|
| 0% | +9.55% | +9.55% |
| 10% | +9.90% | +9.55% |
| 50% | +14.64% | +9.55% |
| 90% | +96.18% | +9.55% |

這表示即使 0% 掉包，Task-ID-Ordered Greedy 的成本與 Global Greedy 本身便有平均 +9.55% 的差距；比較兩張研究圖時必須明確區分方法與成本基準。

## 資料限制與交付

- 原始 Rady 網路延遲輸入檔沒有附於 ZIP；可驗證 config 內記錄的 SHA256、時序帳本與模擬輸出，但**無法從 ZIP 獨立重跑相同網路隨機延遲**。
- Proposed 存檔含 100 個 native task epoch ID、per-task Commit、遠端 Cost/Vote 觀察與 sender phase **總帳**，沒有包含全部 100 輪的每個 Vote/Score/Commit 封包原始時間戳；因此這是逐 Seed / 原生 trace / sender ledger 審計，不等於完整空中封包重放。
- 正式 ZIP 內沒有 Mac `compileall` 或全部 unittest 的 log，因此本報告只確認正式原生 2,000 案例、程式輸出與可驗證資料完整性，**不宣稱所有測試已另行執行通過**。
- 圖一原始 SVG、PNG 預覽、正式摘要 CSV 及稽核 JSON 已獨立留存；原始 ZIP 完全不動。舊圖二的數據曲線保留，底部說明文字移除版本另存。

**結論：這次 P2H 數據與其聲稱的『逐任務各一次 Vote/Commit、一次 Cost、有效 sender Bytes』契約一致，可用於呈現限定網路模型下的結果；然而 100% 成功率的重要成因是本地自投票 + 一票相對多數 + 可靠 Score/Commit，須在論文正文交代，避免把它宣稱為不受掉包影響的一般分散式共識保證。**