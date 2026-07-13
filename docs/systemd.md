# 使用 systemd 執行 Find Me

這份文件說明如何在 Debian 主機上將 Find Me 設為 systemd 服務。服務會在開機時自動啟動，異常結束後自動重啟，並維持監聽 `127.0.0.1:8613`，對外連線由其他服務處理。

以下範例使用目前的主機設定：

- 執行帳號：`user`
- 專案目錄：`/home/user/find-me`
- uv 路徑：`/home/user/.local/bin/uv`
- 服務名稱：`find-me`

換機或更換帳號時，請替換上述帳號與路徑。可用 `command -v uv` 確認新主機上的 uv 絕對路徑。

## 首次部署

安裝 OpenCV 在 Debian 需要的系統函式庫：

```bash
sudo apt update
sudo apt install -y libxcb1 libgl1
```

確認專案已放在預定目錄後，同步正式環境依賴：

```bash
cd /home/user/find-me
/home/user/.local/bin/uv sync --locked --no-dev
```

第一次執行 InsightFace 時會下載模型。建立服務前，先手動啟動一次並確認應用程式可以正常運作；確認完成後按 `Ctrl+C` 停止，避免服務啟動時發生 port 衝突：

```bash
cd /home/user/find-me
/home/user/.local/bin/uv run --locked --no-sync python main.py
```

## 建立服務

建立 `/etc/systemd/system/find-me.service`：

```bash
sudo tee /etc/systemd/system/find-me.service >/dev/null <<'EOF'
[Unit]
Description=Find Me web service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/find-me
Environment=HOME=/home/user
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/user/.local/bin/uv run --locked --no-sync python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

`--locked` 會拒絕使用過期的 lockfile；`--no-sync` 會禁止服務啟動時同步虛擬環境。依賴必須在部署或更新階段手動同步。

驗證設定檔後，載入並立即啟用服務：

```bash
sudo systemd-analyze verify /etc/systemd/system/find-me.service
sudo systemctl daemon-reload
sudo systemctl enable --now find-me
```

確認服務與本機 HTTP 端點正常：

```bash
sudo systemctl status find-me --no-pager
curl --fail http://127.0.0.1:8613/
```

## 日常操作

```bash
# 查看狀態
sudo systemctl status find-me --no-pager

# 即時查看日誌
sudo journalctl -u find-me -f

# 查看本次開機後的日誌
sudo journalctl -u find-me -b --no-pager

# 重新啟動
sudo systemctl restart find-me

# 停止與啟動
sudo systemctl stop find-me
sudo systemctl start find-me
```

## 更新程式

取得新版程式碼後，先同步 lockfile 指定的正式環境依賴，再重新啟動服務：

```bash
cd /home/user/find-me
/home/user/.local/bin/uv sync --locked --no-dev
sudo systemctl restart find-me
sudo systemctl status find-me --no-pager
```

如果只修改程式碼且依賴沒有變動，可以省略 `uv sync`，直接重新啟動服務。

## 修改服務設定

修改 `/etc/systemd/system/find-me.service` 後，需要重新載入 systemd 並重啟服務：

```bash
sudo systemd-analyze verify /etc/systemd/system/find-me.service
sudo systemctl daemon-reload
sudo systemctl restart find-me
```

## 停用與移除

```bash
sudo systemctl disable --now find-me
sudo rm /etc/systemd/system/find-me.service
sudo systemctl daemon-reload
```

移除 service 不會刪除專案、虛擬環境、索引、照片或 InsightFace 模型。

## 參考資料

- [uv：Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Debian systemd.service(5)](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html)
- [Debian systemd.exec(5)](https://manpages.debian.org/trixie/systemd/systemd.exec.5.en.html)
- [Debian systemctl(1)](https://manpages.debian.org/trixie/systemd/systemctl.1.en.html)
- [Debian libxcb1](https://packages.debian.org/trixie/libxcb1)
- [Debian libgl1](https://packages.debian.org/trixie/libs/libgl1)
