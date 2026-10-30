# 讓 Ubuntu / Fedora / Arch 都能用：發行材料

三條路，由近到遠：

| 路線 | 給誰用 | 你要做的事 | 維護成本 |
|---|---|---|---|
| ① 套件庫（PPA / COPR / AUR） | 願意加一個來源的使用者 | 各平台開帳號、上傳一次 | 發行版每次更新 libfprint 都要重打包 |
| ② 進上游 libfprint | 所有人（內建） | 與 keno2003 合併送審 MR !662 | 最低，但要數個月審查 |
| ③ 直接 install.sh | 測試者 | 無 | 系統更新會蓋掉 |

## 本資料夾內容（全部實際建置驗證過）

| 檔案 | 用途 | 驗證結果 |
|---|---|---|
| `../patches/0001–0007` | 上游 libfprint 1.94.100 補丁 | Fedora 44 全測試 130/130 通過 |
| `debian/egis0570touch.patch` | Ubuntu「+tod」分支專用移植版 | Ubuntu 26.04 全測試 215/215 通過 |
| `debian/apply.sh` | 把補丁加進 Ubuntu 原始碼套件、改版號 | 產出 `1:1.95.1+tod1-0ubuntu2+egis1` |
| `debian/port_to_tod.py` | 從上游補丁重新產生 Ubuntu 移植版 | — |
| `debian/ppa.md` | Launchpad PPA 上架步驟 | — |
| `fedora/patch_spec.py` | 把補丁與 OpenCV 依賴加進 Fedora spec | 產出 `libfprint-1.94.100-1.egis1.fc44` |
| `fedora/*.copr.md` | Fedora COPR 上架步驟 | — |
| `arch/PKGBUILD` | AUR 套件 | 見下方 |
| `scripts/build-all.sh` | 用 Docker 在乾淨環境重現全部建置 | — |

## 為什麼 Ubuntu 要另外一份補丁

Ubuntu/Debian 用的不是上游 libfprint，而是 Ubuntu 自己的「tod」分支（版本 1.95.1+tod1），
建置設定（meson.build）結構不同，上游補丁套不上去。驅動程式碼本身一模一樣，
只有建置設定與測試清單用 `port_to_tod.py` 重新改寫。

## 建置與安裝驗證做了什麼

- 在乾淨的 Ubuntu 26.04 / Fedora 44 容器裡從官方原始碼套件建置，跑發行版自己的完整測試套件。
- 把產出的套件裝進另一個乾淨容器：版本確實蓋過官方版、硬體清單有 1c7a:0570、
  驅動有編進去、OpenCV 有連結、Python 綁定可載入。
- **沒驗證的**：在真實 Fedora/Ubuntu 機器上用手指解鎖（只在 152 這台 Ubuntu 上實測過）。

## 上游送審前還缺的（維護者大概會要求）

1. 觸控路徑的 USB 錄製重播測試（取代 0006 移除的舊測試）。
2. 多人、跨日的辨識數據（目前只有一人一晚）。
3. 自適應學習可能被要求預設關閉或改走 fprintd 正式 API。
4. 減少 OpenCV 依賴（目前只用 core + imgproc，可改純 C）。
