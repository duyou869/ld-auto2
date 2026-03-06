# LinuxDo 每日签到（每日打卡）

## 项目描述

这个项目用于自动登录 [LinuxDo](https://linux.do/) 网站并随机读取几个帖子。它使用 Python 和 Playwright
自动化库模拟浏览器登录并浏览帖子，以达到自动签到的功能。

有时会登录失败，重试一下就行了，嫌失败邮件通知烦的可以吧action的邮件通知关了

## 功能

- 自动登录`LinuxDo`。
- 自动浏览帖子。
- 每天在`GitHub Actions`中自动运行。
- 支持`Github Actions` 自动运行。
- (可选)`Telegram`通知功能，推送获取签到结果。
## 环境变量配置

### 登录方式（二选一）

**方式一：Cookie 登录（优先）**

| 环境变量名称             | 描述                                         | 示例值                          |
|--------------------|--------------------------------------------|------------------------------|
| `LINUXDO_COOKIES`  | 从浏览器 DevTools 复制的 Cookie 字符串，设置后优先使用，无需账号密码 | `_t=xxx; _forum_session=yyy` |

> 获取方式：打开 [linux.do](https://linux.do/) 并登录 → 按 F12 → Application → Cookies → `https://linux.do` → 全选所有 Cookie 复制为字符串粘贴即可。

**方式二：账号密码登录**

| 环境变量名称             | 描述                | 示例值                                |
|--------------------|-------------------|------------------------------------|
| `LINUXDO_USERNAME` | 你的 LinuxDo 用户名或邮箱 | `your_username` 或 `your@email.com` |
| `LINUXDO_PASSWORD` | 你的 LinuxDo 密码     | `your_password`                    |

> 若同时设置了 `LINUXDO_COOKIES` 和账号密码，**Cookie 登录优先**；Cookie 失效时自动回退到账号密码登录。

~~之前的USERNAME和PASSWORD环境变量仍然可用，但建议使用新的环境变量~~

### 可选变量

| 环境变量名称                | 描述                   | 示例值                                    |
|----------------------|----------------------|----------------------------------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token   | `123456789:ABCdefghijklmnopqrstuvwxyz` |
| `TELEGRAM_CHAT_ID`   | Telegram 用户 ID       | `123456789`                            |
| `BROWSE_ENABLED`     | 是否启用浏览帖子功能           | `true` 或 `false`，默认为 `true`           |

---

## 如何使用

### GitHub Actions 自动运行

此项目的 GitHub Actions 配置会自动每天运行2次签到脚本。你无需进行任何操作即可启动此自动化任务。GitHub Actions 的工作流文件位于 `.github/workflows` 目录下，文件名为 `daily-check-in.yml`。

#### 配置步骤

1. **设置环境变量**：
    - 在 GitHub 仓库的 `Settings` -> `Secrets and variables` -> `Actions` 中添加以下变量：
        - （二选一）`LINUXDO_COOKIES`：从浏览器复制的 Cookie 字符串（**推荐，优先使用**）。
        - （二选一）`LINUXDO_USERNAME` + `LINUXDO_PASSWORD`：你的 LinuxDo 用户名/邮箱和密码。
        - (可选) `BROWSE_ENABLED`：是否启用浏览帖子，`true` 或 `false`，默认为 `true`。
        - (可选) `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`。

2. **手动触发工作流**：
    - 进入 GitHub 仓库的 `Actions` 选项卡。
    - 选择你想运行的工作流。
    - 点击 `Run workflow` 按钮，选择分支，然后点击 `Run workflow` 以启动工作流。

#### 运行结果

##### 网页中查看

`Actions`栏 -> 点击最新的`Daily Check-in` workflow run -> `run_script` -> `Execute script`

可看到`Connect Info`：
（新号可能这里为空，多挂几天就有了）
![image](https://github.com/user-attachments/assets/853549a5-b11d-4d5a-9284-7ad2f8ea698b)

### Telegram 通知

可选功能：配置 Telegram 通知，实时获取签到结果。

需要在 GitHub Secrets 中配置：
- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `TELEGRAM_CHAT_ID`：Telegram 用户 ID

获取方法：
1. Bot Token：与 [@BotFather](https://t.me/BotFather) 对话创建机器人获取
2. 用户 ID：与 [@userinfobot](https://t.me/userinfobot) 对话获取

未配置时将自动跳过通知功能，不影响签到。


