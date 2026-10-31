# 安全審查報告（claude）

## 0. 一句話結論

驅動程式本體（USB 解析、特徵序列化、gallery cache、adaptive 側檔）在我讀到的範圍內做了嚴謹的邊界檢查與 fail-closed 設計，130/130 既有測試（含故意餵壞資料的案例）通過；真正該修的是三個低/中風險的流程面問題（GitHub workflow 最小權限、match.cpp 一個死掉的常數、lockscreen 補丁有一段我無法在本 repo 內獨立驗證的假設），而「這把感應器本質上有多安全」這個大問題（FAR、仿冒、sudo）答案是否定的──詳見 E 段；README 已經寫了「not a security boundary」，我同意這個結論，而且 sudo 的風險比鎖屏還高。

## B. 發現（依嚴重度排序：高 → 低）

### B-1 GitHub Actions：build job 繼承了不必要的 `contents: write`，且 checkout 預設把 token 留在工作樹裡再餵給容器

- 嚴重度: 中
- 證據: `.github/workflows/release.yml:10-11`（`permissions: contents: write` 寫在 workflow 層級，沒有 per-job override）；`:32` 與 `:55` 兩個 `actions/checkout@v4` 都沒有 `persist-credentials: false`；`:36` 的 `docker run --rm -v "$PWD:/repo:ro" ... bash /repo/packaging/scripts/${{ matrix.script }}` 把整個工作樹（含 checkout 寫入的 git 憑證）以唯讀掛載進容器，容器內執行的是 PR 自己帶來的 `packaging/scripts/*.sh`。我實際跑的指令與輸出：
  ```
  $ grep -n "GH_TOKEN\|secrets\.\|GITHUB_TOKEN\|permissions:\|contents:" .github/workflows/release.yml
  10:permissions:
  11:  contents: write
  64:          GH_TOKEN: ${{ github.token }}
  $ grep -n "checkout@\|persist-credentials" .github/workflows/release.yml
  32:      - uses: actions/checkout@v4
  55:      - uses: actions/checkout@v4
  ```
  `GH_TOKEN` 只在 `release` job（line 64）明確用到；`build` job 完全沒有引用 token，但仍繼承 workflow 層級的 `contents: write`。
- 風險情境: `actions/checkout@v4` 預設 `persist-credentials: true`，會把帶權限的 GITHUB_TOKEN 寫進 checkout 出來的 `.git/config`。`:ro` 掛載只擋得住寫入，擋不住讀取──如果觸發事件是**同一個 repo**（非 fork）開出的 PR（例如有寫入權限的協作者、或 Dependabot 之類），`build` job 拿到的就是具備 `contents: write` 的 token；該 PR 若同時修改了 `packaging/scripts/build_*.sh`（這些腳本本來就會在容器內執行），就能讀取掛載進來的 `.git/config` 把 token 外洩出去（容器預設有對外網路）。對於**來自 fork** 的 PR，GitHub 平台本身會把 `pull_request`（非 `pull_request_target`）事件的 token 強制降為 read-only、不帶 secrets，這部分不受 workflow 的 `permissions:` 影響——但這是 GitHub 平台行為，我在這個沙箱裡無法對 GitHub Actions 實際觸發一次來驗證，列入 C。
- 建議修法: 把 `permissions: contents: write` 從 workflow 層級移到只有 `release` job 需要；`build` job 顯式宣告 `permissions: contents: read`（或省略，讓其落在組織預設的最小權限）。`build` job 的 `actions/checkout@v4` 加 `with: persist-credentials: false`（它不需要往回寫）。
- 工時: 小

### B-2 `egis0570touch-match.cpp` 裡有一個已經不是真正門檻值的死常數，容易誤導之後的審閱者

- 嚴重度: 低
- 證據: `.tmp/pkg/f-try/libfprint-v1.94.100/libfprint/drivers/egis0570touch-match.cpp:68`：
  ```cpp
  constexpr double kDefaultThreshold = 0.38;
  ```
  我實際跑的指令，確認這個常數在整棵已套用全部 10 個 patch 的樹裡只出現這一次、沒有任何地方讀取它：
  ```
  $ grep -rn "kDefaultThreshold" .tmp/pkg/f-try/libfprint-v1.94.100/
  .tmp/pkg/f-try/libfprint-v1.94.100/libfprint/drivers/egis0570touch-match.cpp:68:constexpr double kDefaultThreshold = 0.38;
  ```
  真正生效的門檻值在 `libfprint/drivers/egis0570touch.c:26`（`#define MATCH_THRESHOLD_DEFAULT 0.49`，patch 0010 已經改對）。這個常數是 patch 0005 引入、patch 0010 修 0.38→0.49 時只改了 `egis0570touch.c`、沒有一併處理 `match.cpp` 裡這個同名概念的殘留值：
  ```
  $ grep -n "kDefaultThreshold" patches/0005-egis0570touch-ncc-multiframe-adaptive.patch patches/0010-egis0570touch-safe-defaults.patch packaging/debian/egis0570touch.patch
  patches/0005-egis0570touch-ncc-multiframe-adaptive.patch:95:+constexpr double kDefaultThreshold = 0.38;
  packaging/debian/egis0570touch.patch:107:+constexpr double kDefaultThreshold = 0.38;
  ```
  （0010 沒有碰這一行，三個檔案都停在 0.38。）
- 風險情境: 目前**不是**可被利用的安全缺陷——這個值真的沒人讀取，實際門檻仍是 0.49。風險是「人」：之後有人（包含準備投上游的 reviewer）只看 `match.cpp` 的 diff，會以為 0.38 是現行門檻，或在重構時誤把這個常數接回去用,等於悄悄把已知不安全的 0.38 復活。
- 建議修法: 刪掉這行死碼（或在旁邊補一行註解說明「門檻已搬到 egis0570touch.c 的 MATCH_THRESHOLD_DEFAULT，這裡不再使用」），同時更新 `packaging/debian/egis0570touch.patch`（手動維護的合併補丁）讓三份檔案一致。
- 工時: 小

### B-3 lockscreen 補丁有一段「指紋在 grace period 內不會生效」的安全性假設，寄生在我無法於本 repo 驗證的上游行為上

- 嚴重度: 低（風險殘留，非已證實的繞過）
- 證據: `lockscreen/lockscreen_keys_patch.py:58-86`。`LockScreenUi.qml` 被插入的程式碼：
  ```python
  # 第 67-76 行
  FP = '// [local-patch] fingerprintAlways'
  if FP not in u:
      old = "        Component.onCompleted: launchAnimation.start();\n"
      ...
      u = u.replace(old,
          "        " + FP + "\n"
          "        Component.onCompleted: {\n"
          "            launchAnimation.start();\n"
          "            authenticator.startAuthenticating();\n"   # <- 無條件呼叫
          "        }\n"
          "        Timer {\n"
          "            id: fpRearmTimer\n"
          ...
          "            onTriggered: {\n"
          "                if (!authenticator.unlocked && !graceLockTimer.running)\n"  # <- 這裡才檢查 grace period
          "                    authenticator.startAuthenticating();\n"
          "            }\n"
          "        }\n", 1)
  ```
  重複計時器（`fpRearmTimer`）每次觸發前會檢查 `!graceLockTimer.running`，但鎖屏載入時第一次呼叫（`Component.onCompleted` 裡那一行）完全沒有這個檢查，純粹依賴腳本自己寫的註解（lines 58-65）宣稱「`startAuthenticating()` 在 `graceLockTimer` 運作時本身就是 no-op」。
- 風險情境: 如果這個「上游 `startAuthenticating()` 在 grace period 時自動 no-op」的假設在某個 Plasma 版本不成立，鎖屏剛載入、grace period 還在走的那個瞬間就會多一次指紋嘗試視窗。但即使真的觸發，grace period 本身的定義就是「這段時間內不需要任何憑證就能解鎖」，所以就算假設不成立，也看不出這比 grace period 原本的語意多開了一個新的繞過面——只是我沒有上游 Plasma 的 QML 原始碼（不在這個 repo 裡）可以逐行核對這個 no-op 保證。
- 建議修法: 在 `Component.onCompleted` 那次呼叫也補上 `if (!graceLockTimer.running) authenticator.startAuthenticating();`，讓程式碼本身不依賴對上游行為的假設描述；或者在程式碼註解旁邊附上驗證方式（例如對應的 Plasma commit/版本號）。
- 工時: 小

### B-4 Ubuntu 的合併補丁（`packaging/debian/egis0570touch.patch`）是手動同步，沒有自動產生腳本

- 嚴重度: 低
- 證據: `packaging/scripts/build_deb.sh:10` 直接套用這個單一大檔，而不是像 Fedora/Arch 一樣逐個套用 `patches/0001...0010`：
  ```
  $ grep -rln "egis0570touch.patch" packaging/
  packaging/scripts/build_deb.sh
  packaging/fedora/patch_spec.py   # 只是字串提到檔名，給 rpm spec 用
  packaging/debian/apply.sh
  ```
  沒有任何腳本從 `patches/*.patch` 重新產生這個合併檔；`packaging/debian/port_to_tod.py` 是另一套（搬到 Ubuntu tod 樹），也不負責重新生成它。目前內容是對的（我已核對過 0.49/`adapt_enabled` 的邏輯都在），但這次是靠人工記得同步。
- 風險情境: 未來任何一次只改 `patches/00xx` 卻忘了手動重新生成 `packaging/debian/egis0570touch.patch`，Ubuntu 套件就會悄悄停留在舊行為（例如舊門檻值或 adaptive 預設開啟），而 Fedora/Arch 的使用者拿到的是新行為，三個發行版的安全預設值會不一致，而且不會有任何測試失敗來提醒——`build_deb.sh` 的測試只驗證「Ubuntu 這份補丁內部自洽」,不會跟 `patches/` 的最新版本做差異比對。
- 建議修法: 加一個 CI 檢查（或 `build-all.sh` 裡的一步）：用 `patches/0001..0010` 依序 `git apply` 出一棵樹，和套用 `packaging/debian/egis0570touch.patch` 的樹做 `diff -r`，不同就讓 build 失敗。
- 工時: 小

## C. 我沒能複核的

1. **GitHub 平台對 fork PR 的 token 限制**：B-1 的風險在「同一 repo 開出的 PR」才完全成立；對 fork PR，GitHub 官方文件描述 `pull_request`（非 `pull_request_target`）事件的 `GITHUB_TOKEN` 會被平台強制降為 read-only、且不帶 secrets，不受 workflow 檔案裡 `permissions:` 影響。我在這個沙箱裡無法實際觸發一次 GitHub Actions 來驗證這條平台行為是否仍然如此、或這個 repo 的組織/repo 設定（例如「非協作者的 PR 是否需要人工核准才能跑 workflow」）目前是什麼。
2. **Plasma 的 `authenticator.startAuthenticating()` 在 grace period 期間是否真的是 no-op**（B-3）：這是 KDE Plasma 自己的 QML/C++ 原始碼，不在這個 repo 裡，我沒有去抓對應版本的 Plasma 原始碼來核對這個假設。
3. **`/var/lib/fprint/` 以及 `.egis0570-adaptive/` 的實際擁有者/權限、`fprintd` 實際跑在哪個 UID**：driver 端程式碼（`adapt_dir()`、`g_mkdir_with_parents(..., 0700)`）假設自己能掌控新建目錄的權限，但它沿用的父目錄 `/var/lib/fprint/` 的所有權/權限是由發行版的 fprintd 套件決定，不在這個 repo 範圍內，我沒有一台裝好的機器可以 `stat` 它。
4. **仿冒攻擊（presentation attack）的實測成功率**：E-2 的推論是文獻等級（capacitive 小面積感應器、無 liveness check 的已知脆弱性），我沒有實體感應器或模具可以真的做一次 replay/假指紋測試。
5. **GitHub repo 的實際 branch protection / Actions 權限設定**（例如是否要求對外部貢獻者的 workflow 先人工核准）：這些是 GitHub 網站上的設定，不在 git 版本控制的檔案裡,我讀不到。
6. **`lockscreen_keys_patch.py` 實際安裝到的 apt hook 檔案**（README 提到的 `/etc/apt/apt.conf.d/99-lockscreen-patch`）：這個檔案本身不在 repo 裡（它會安裝到使用者系統上），我只能看到 README 裡描述的那一行 `DPkg::Post-Invoke` 設定，無法確認實機上真的是這樣設定、也無法確認它是否真的對 `||true` 失敗容錯。

## D. 我判定是刻意取捨而不是缺陷的（附理由）

- **NCC 影像比對取代 minutiae、0.49 門檻、78% 單次通過率**：README.md 全文 + `egis0570touch.c:20-26` 的註解已經完整揭露來源與取捨（41 筆冒充樣本上限 0.468 + 0.02）。這是任務檔案第 26-31 行明列「不要當缺陷回報」的項目，我同意這樣的揭露程度合理，詳細計算見 E-1。
- **adaptive learning 預設關閉**：已核對 `egis0570touch.c:114-122`（`adapt_enabled()`）與 `patches/0010-egis0570touch-safe-defaults.patch:42-51` 的 diff,確認邏輯從「預設開、設 `0` 才關」改成「預設關、設 `1` 才開」，且 `tests/test-egis0570touch-driver.c` 的 `defaults()` 測試（line 332 `g_assert_false (adapt_enabled())`）在 `.tmp/ci/rpm/rpm-test.log` 裡隨整個測試套件一起跑過（OK, 0.14s, line 119）。符合文件宣稱。
- **`temp_hot_seconds = -1`（無熱保護模型）**：`egis0570touch.c:929-933` 的註解與 `fpi_device_egis0570touch_class_init` 裡的設定一致，`defaults()` 測試也斷言 `cls->temp_hot_seconds == -1`（`test-egis0570touch-driver.c:338`）。這是主動選擇，不是漏設。
- **PAM `max-tries=1000000 timeout=-1`**：這是 README 給使用者的手動設定建議（README.md:146），**這個 repo 本身沒有任何腳本會自動把這段寫進 `/etc/pam.d/`**——我搜過整個 repo 沒有找到會寫 `/etc/pam.d/*` 的程式：
  ```
  $ grep -rln "pam.d\|pam_fprintd\|pam_unix" . --include="*.sh" --include="*.py" --include="*.md" --include="*.yml" | grep -v ".tmp\|.git"
  ./lockscreen/lockscreen_keys_patch.py   (只在註解裡提到這個事實，沒有寫檔)
  ./TASK_security_audit.md
  ./README.md
  ```
  沒有自動化根寫入腳本，是比我原本預期更保守的設計，我認為是刻意（或至少是合理）的取捨：使用者必須自己手動編輯系統 PAM 檔案才會生效。
- **模板以未加密原始影像存放在 `/var/lib/fprint/`**：這和其它 libfprint 影像類驅動（如 `elan`、`vfs301` 等）的做法一致,不是這個驅動自己的新缺陷,任務檔案第 36-37 行也明列為既知取捨。
- **`EGIS0570_DUMP_DIR` 除錯轉存預設關閉**：`fpi_egis0570touch_dump_frames()`（`egis0570touch-match.cpp:469-492`）第一行就是 `if (!dir || ...) return;`，`dir` 來自 `getenv("EGIS0570_DUMP_DIR")`，沒設就不會寫任何檔案。已核對程式碼,確認預設關閉屬實。
- **`tools/` 下的離線評估腳本使用 `pickle`/`np.load(allow_pickle=True)`**：
  ```
  $ grep -n "pickle\|allow_pickle" tools/*.py
  live3_eval.py:108,125; live3_repr.py:6,85; xsession_eval.py:39; xsession_report.py:3
  ```
  這些都是對自己本機產生的 `.tmp/`、`.pkl` 檔案做 pickle，不是對外部/不可信輸入做反序列化，而且 README 明確寫「No biometric data is included in this repository」「they need your own captures」,不隨套件安裝、不被 `install.sh`/`packaging/*` 任何腳本呼叫。我判定這不是攻擊面。
- **`packaging/arch/PKGBUILD:32` 的 `b2sums=('SKIP')`**：單獨看像是關掉完整性驗證,但 `packaging/arch/README.md:10` 的發佈流程寫明發佈前要先跑 `updpkgsums`（`packaging/scripts/build_arch.sh:7` 的 CI 流程也會跑一次,並把結果另存成 `PKGBUILD.withsums`）,真正推到 AUR 的版本不會是 `SKIP`。這是 AUR 社群慣用的模板寫法,我判定非缺陷。

## E. 六個問題的回答（E-1 … E-6）

### E-1 False accept 風險：41 次冒充按壓能說明什麼、不能說明什麼；無限重試下的有效風險

**能說的**：在**這一位**使用者、**這一台**感應器、**這 4 根**（家人）未註冊手指、**這 41 次**按壓的條件下，0.49 門檻把全部 41 次都擋在外面（最高分 0.468），而 0.38 當時放過了 12 次。這只足以說明「0.38 太低」,不足以估計任何有統計意義的 population-level FAR——41 次、4 根手指遠低於生物辨識 FAR 研究常見的千人以上規模,且樣本全部來自同一個家庭、同一支感應器、同一種環境,對任意陌生攻擊者的代表性完全未知。README.md:29 自己也寫了同一句話，我同意。

**無限重試下的有效風險（具體估計，附假設）**：
假設每次按壓的接受機率（對某個固定的「其他人」）是獨立同分布的 p（這是近似——同一根手指重複嘗試並非真正獨立，但在缺乏更好模型時是標準做法）。對「0/41 次成功」這個觀察,用 rule-of-three 做 95% 信賴上界：p ≲ 3/41 ≈ 7.3%（這是本資料集唯一能給出的統計上界，而且前面說過代表性很弱，實際上界可能遠高於或低於這個數字）。
在無限重試（`max-tries=1000000, timeout=-1`，README.md:146）下，n 次嘗試後至少成功一次的機率是 1-(1-p)^n：

| 假設的單次接受率 p | 50% 機率解鎖所需次數 n |
|---|---|
| 7.3%（本資料集 95% 上界） | ≈9 次 |
| 1% | ≈69 次 |
| 0.1% | ≈693 次 |

鎖屏一次按壓+回饋大約數秒,一個有實體存取權、肯花十幾分鐘到一小時反覆按壓的人，在這個門檻設計下幾乎可以把「指紋辨識」的安全性壓到接近「只要攻擊者有耐心就能解鎖」，而不是接近「隨機猜中的機率」。這跟 README 的結論一致：重試次數無上限，把任何非零的 per-attempt FAR 都放大成遲早會發生的事件，41 次資料連這個 p 是不是真的非零都答不清楚。adaptive learning 預設關閉（patch 0010）至少移除了「門檻會隨使用而自己往上飄」這個額外風險,但不影響上面這個無限重試的算術。

### E-2 仿冒 / presentation attack

程式碼裡**沒有任何 liveness check**：`process_packet()`（`egis0570touch.c:619-686`）判斷「有沒有手指」只靠單一強度門檻 `mean > EGIS0570_MIN_MEAN`（line 20 定義 `EGIS0570_MIN_MEAN 20`），比對演算法（`fpi_egis0570touch_features_compare`）純粹是靜態影像的正規化互相關,沒有脈動、溫度、介電係數變化、多幀間的生理動態等任何活體特徵。

文獻等級的推論（我無法在這個沙箱裡實測，見 C 段）：這類低解析度（114×57）電容式按壓感應器，在已公開的研究與社群實作中，對「翻模指紋」（導電凝膠/石墨/銀漆模具,Matsumoto 2002 式的 gummy finger 攻擊路線）或「列印導電墨水複製品」這類 presentation attack 的抵抗力普遍偏低——電容感應器偵測的是導電/介電分布，只要複製品的導電圖案夠接近，沒有活體檢測的情況下很難從單張影像判斷真偽。這個驅動額外依賴 NCC 分數閾值做唯一防線,而 E-1 已經說明這個閾值本身只用極小樣本校準過。結論：**無法排除、也沒有機制防禦** lifted-print 或複製品攻擊；這跟缺不缺指紋辨識軟體本身的 bug 無關,是這類感應器+演算法組合的本質限制。

### E-3 sudo 要不要開指紋

**建議：不要。**

理由：
1. sudo 給的是 root,風險等級跟鎖屏（只是解鎖一個已登入的桌面會話）不對等。
2. **遠端 session（ssh）**：`pam_fprintd` 查詢的是本機 USB 感應器；透過 ssh 進來的使用者執行 `sudo` 時,PAM 會呼叫 `pam_fprintd`,但沒有人在本機把手指放上去,這一步只會失敗或 timeout,接著視 PAM stack 的 `sufficient`/`required` 排列方式 fallback 到 `pam_unix`（密碼）。問題不是「遠端使用者會被要求按本機感應器」——是反過來：**如果這段時間有任何人實體在本機（例如同住的人、訪客、或闖入者）**，他們可以在本機按感應器,直接幫**遠端那個已經開著 ssh session 的使用者**的 `sudo` 提示通過驗證,完全不需要知道密碼、也不需要是同一個人。這比鎖屏的風險更大，因為鎖屏至少還綁定「這台機器已經被這個使用者解鎖過一次」,sudo 提示可能在使用者毫無防備、甚至人不在電腦前（只是 ssh session 還開著）的情況下被别人代打。
3. **本機已有 shell 的攻擊者**：如果攻擊者已經用其他方式（例如竊取另一支 session、或物理接觸但還沒鎖屏）取得使用者的本機 shell,指紋辨識不會增加任何防禦——攻擊者只要自己按裝置,或者（如 E-2）用複製品,就能把普通使用者權限直接變成 root,完全跳過密碼。
4. **polkit vs sudo 的爆炸半徑不同**：polkit 的指紋整合通常是針對單一、範圍受限的授權動作（例如掛載磁碟、改網路設定）；`sudo` 這個 PAM service 覆蓋的是「任意 root shell 命令」,把同一套「無限重試、無逾時」的信任放進這裡,等於把 E-1、E-2 的所有弱點直接乘到最高權限上。

**如果使用者堅持要開**（README 和這份報告都建議不要）,最安全的設定方式：
- **不要**沿用鎖屏的 `max-tries=1000000 timeout=-1`。`sudo` 的 PAM stack 裡指紋應設成**低重試、有限逾時**，例如 `max-tries=3 timeout=10`——sudo 本來就假設使用者就在終端前等著輸入,不需要鎖屏那種「螢幕關著也要一直重試」的場景。
- 順序：`pam_fprintd.so sufficient max-tries=3 timeout=10` 放在 `pam_unix.so` **之前**,讓指紋失敗時乾淨地 fallback 到密碼,而不是擋住密碼路徑（`required`/`requisite` 會在指紋失敗時直接擋掉,不應該這樣設）。
- 範圍盡量只放在互動式、本機終端場景會用到的 service（`sudo`、`su`）,不要放進任何可能被遠端或非互動流程呼叫到的 PAM service（例如避免放進會被 cron/腳本用到的 service）。Linux-PAM 本身不會自動分辨「這個 sudo 呼叫是不是從 ssh 來的」,所以第 2 點描述的風險無法只靠 PAM 設定消除,只能靠「不要在遠端可能開著 session 的機器上啟用」這個使用習慣來緩解。
- 這一切都建立在「指紋本身的強度」之上,而 E-1/E-2 已經說明這個強度是有限且未被嚴謹量化的——這是不建議啟用的根本原因,不是設定細節能解決的。

### E-4 鎖屏補丁會不會削弱鎖定

就程式碼讀到的範圍（`lockscreen/lockscreen_keys_patch.py` 全檔），**沒有找到能在沒有驗證的情況下直接解鎖的路徑**：

- `MainBlock.qml` 被插入的 key handler（lines 37-45）只在 `!sessionManager.lockScreenUiVisible` 時把按鍵吞掉、呼叫 `wakeRequested()`、`event.accepted = true`——效果是「顯示密碼輸入框」，不是「解鎖」。
- `LockScreenUi.qml` 的 `onWakeRequested: lockScreenRoot.uiVisible = true`（line 56）只是切換 UI 可見性,同一個道理。
- 讓指紋從「只有密碼框出現後才開始跑」變成「鎖屏一載入就開始跑」的那段（lines 67-86）,是把既有的 `authenticator.startAuthenticating()` 提前呼叫,**沒有新增任何繞過驗證的分支**——它呼叫的仍然是 Plasma 自己的驗證器,成功與否的判斷邏輯完全在 Plasma 端,這個 patch 檔案本身不做任何「視為已通過」的捷徑。
- 重複計時器會在 `graceLockTimer.running` 時跳過重新觸發指紋驗證（line 83），顯示作者有意識地避免在 grace period 裡做事；唯一我無法獨立核實的是「鎖屏剛載入那一次」是否也受這個保護（見 B-3 / C 段）。
- 腳本本身是 fail-closed 設計：每個字串錨點替換前都 `s.count(old) != 1` 檢查，不符合就 `sys.exit(1)`（lines 28-29, 53-54, 69-70），失敗時**不會**寫入半套修改的檔案（寫入動作都在所有替換成功後才執行，line 46、line 87）；且保留 `/root/*.qml.orig` 乾淨備份。

**結論**：這個補丁改的是「指紋驗證什麼時候開始跑」，不是「驗證通過與否怎麼判斷」，就程式碼本身看不出會讓鎖屏在未驗證下開啟；殘留的不確定性只在 B-3 描述的那個邊界情況,且就算成立，風險也不比 grace period 本身的既有語意更大。

### E-5 以 root 執行的腳本：injection / path / TOCTOU

- **`install.sh`**：沒有把任何外部/使用者輸入字串拼進 shell 指令（只接受 `--revert` 這個固定字面比對的參數，`install.sh:16`）；upstream libfprint 用**固定 commit hash** 鎖版（`install.sh:9` `BASE=6f9479c3...`），不是浮動 branch/tag,供應鏈風險低；`meson test` 失敗會因為 `set -euo pipefail`（line 6）讓腳本在碰到任何 `sudo install`/`sudo ln` 之前就中止（line 42 測試,line 44 起才動系統檔案）,fail-closed；唯一的 TOCTOU 候選是 `[ -f "$BACKUP" ] || sudo cp ...`（line 44）,但 `$BACKUP` 在 `/var/backups/` 下,一般只有 root 可寫,本機非 root 攻擊者插不進這個窗口。
- **`lockscreen_keys_patch.py`**：見 E-4,無 shell/eval、路徑全部硬編碼、fail-closed、apt hook 呼叫方式是 `... || true`（README.md:155）不會卡住套件安裝。
- **build 腳本（`build_deb.sh`/`build_rpm.sh`/`build_arch.sh`）**：全部跑在用 `docker run --rm -v ...:/repo:ro` 啟的拋棄式容器裡（`packaging/scripts/build-all.sh:11`、`ci_local.sh:10`），不會碰到使用者的真實系統；沒有任何步驟把 PR 外部輸入（例如 issue 內容、PR 標題）插進指令字串,只操作固定檔名。`build_arch.sh:4` 在容器內建立一個有 NOPASSWD sudo 的使用者 `b`，範圍僅限該拋棄式容器,沒有外洩到 host。
- **GitHub workflow**：見 B-1——真正的問題不是注入,是最小權限與 `persist-credentials` 預設值疊加後的 token 外洩路徑,且只在非 fork PR 情境下成立（fork PR 受 GitHub 平台限制,見 C 段）。
- release 階段（`.github/workflows/release.yml:60-69`）用 `sha256sum` 只做傳輸/下載完整性校驗,沒有 GPG/sigstore 簽章——對有 repo 寫入權的惡意行為者沒有防禦力,但這和多數同等規模的開源專案一致,不特別標成高風險,僅在此記錄為殘留風險。

### E-6 驅動記憶體安全

USB 封包解析（`egis0570touch.c:690-699` 的 `receive_frames_cb`、`:615-687` 的 `process_packet`）用的緩衝區大小都是協定定義的常數（`EGIS0570_INPSIZE=32512`、`EGIS0570_IMGCOUNT*FRAME_PIXELS=5*6498=32490`,留 22 bytes 餘量,`egis0570touch-proto.h:90-101`），索引全部在常數範圍內,沒有看到可變長度輸入影響這段的界限。

模板反序列化（`egis0570touch-match.cpp:585-634` 的 `fpi_egis0570touch_features_deserialise`）：讀 `width`/`height` 之後**先**檢查 `width/height` 落在 `(0, 4096]`、`quant_scale` 有限且為正,**再**用 `20 + pixels*sizeof(int16_t)` 算出 `expected`、跟實際 `size` 精確比較相等才往下讀（lines 605-613）,不符合就回 `nullptr`──一個惡意／損壞的 `/var/lib/fprint/` 模板檔不會導致越界讀寫,只會讓這個樣本在比對時直接被當成 0 分（fail closed）。adaptive 側檔解析（`egis0570touch.c:134-164` 的 `adapt_load`）每讀一個長度欄位前都先檢查 `off + 4 > len`、每讀一個 blob 前先檢查 `n == 0 || n > len - off`,損壞檔案會在第一個不合法的地方停止、回傳目前已解析出的內容,不會讀出界外。gallery cache 的 key 是模板的 SHA-256 十六進位字串（`template_key()`,`egis0570touch.c:240-245`）,adaptive 側檔路徑也是 SHA-256 十六進位檔名（`adapt_path()`,lines 124-131）,兩者都不可能包含 `/` 或 `..`,沒有路徑穿越的空間；寫檔用 `g_file_set_contents_full(..., 0600, ...)`、目錄用 `g_mkdir_with_parents(..., 0700)`（lines 185-187）,權限在建立時就設定,不是建立後再 `chmod`,沒有競態窗口。C++ 例外會在 `catch (const std::exception &)` 處被攔住、一律回傳 `nullptr`/`0.0`（`extract`/`serialise`/`deserialise`/`compare` 四個函式都有,lines 494-531, 544-583, 585-634, 636-663）,不會讓 OpenCV 丟出的例外穿到 C 的驅動層造成未定義行為。

**實測證據**（既有的 CI 產物，不是我在本次對話中重新建置的——`.tmp/ci/` 底下的 log 檔早於這次審查就存在；我只讀取、沒有重新執行 build）：
```
$ grep -n "egis0570touch\|^Ok:\|^Fail:" .tmp/ci/rpm/rpm-test.log
114:112/130 unit-tests - libfprint:egis0570touch-storage          OK   0.06s
119:117/130 unit-tests - libfprint:egis0570touch-driver           OK   0.14s
134:Ok:                130
135:Fail:              0
```
對應的測試檔（`tests/test-egis0570touch.cpp:103-130`）明確餵了截斷 blob、改壞 magic、改壞寬高三種壞資料,斷言都回 `nullptr`；`tests/test-egis0570touch-driver.c:217-221` 對 adaptive 側檔餵 `"EA01garbage"` 這種殘缺檔案,斷言 `adapt_load()` 回傳長度 0 而不是當掉。我在這個沙箱裡沒有 `glib-2.0`/`opencv4` 的開發套件（`pkg-config --exists` 回非 0）,所以無法自己重新編譯一份來獨立重跑這些測試,只能讀程式碼 + 讀這份既有 log 交叉核對;這點本身也記錄在 C 段。

我在讀到的範圍內沒有找到緩衝區溢位、整數溢位或 use-after-free；唯一算得上「記憶體/儲存安全」相關的瑕疵是 B-2（死碼,不影響實際行為）。

---

## 最終檢查：`git status --short`

```
$ git status --short
 M README.md
 M packaging/arch/PKGBUILD
 M packaging/debian/egis0570touch.patch
 M packaging/fedora/patch_spec.py
 M packaging/scripts/build_rpm.sh
 M tools/fftncc.py
?? .github/
?? .logs/
?? TASK_security_audit.md
?? audit/claude.md
?? lockscreen/
?? packaging/release-notes/
?? packaging/scripts/ci_local.sh
?? patches/0009-egis0570touch-held-finger-gallery-cache.patch
?? patches/0010-egis0570touch-safe-defaults.patch
?? tools/live3_eval.py
?? tools/live3_labels.py
?? tools/live3_repr.py
```

和對話開始時的 `git status` 相比，唯一新增的是 `audit/claude.md`；其餘 modified/untracked 項目都是這次審查開始前就已存在於工作目錄的狀態，我沒有修改、提交或推送任何東西。
