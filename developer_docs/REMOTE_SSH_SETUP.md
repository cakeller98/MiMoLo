# Remote SSH Setup (macOS → Windows 11 → WSL2)

This guide sets up a **secure, LAN‑only** SSH connection from macOS to a Windows 11 desktop, with optional WSL2 usage. It assumes **VS Code Insiders** and **Remote‑SSH**.

## Goals
- Key‑only SSH (no passwords)
- LAN‑only firewall scope
- Verifiable connection steps

---

## Windows Bootstrap (Dev Tools)

This project includes a Windows per‑user bootstrap script for the dev toolchain:

```
scripts/install_dev_tools_windows.ps1
```

It installs (per‑user):
- Python 3.11+ (via winget)
- uv (via winget)
- pipx (via `py -m pip`)
- Poetry (via `pipx`)
- nvm‑windows (portable, per‑user)
- Node.js 24 (via nvm)
- TypeScript (`tsc`)

Notes:
- Run in a **GUI session** (UAC prompts may appear).
- `nvm use` requires **Admin** or **Developer Mode** (for symlink creation).
- Use `-Validate` to skip installs and only verify PATH/tool availability.

Example:
```powershell
.\scripts\install_dev_tools_windows.ps1
.\scripts\install_dev_tools_windows.ps1 -Validate
```

Critical Caveats:
- This script is tailored to ensure the main developer account (often Admin) can co‑exist with a limited SSH user.
- NVM requires extra care. Using the `nvm-noinstall.zip` portable build with per‑user `NVM_HOME`/`NVM_SYMLINK` avoids cross‑user conflicts.
- The SSH limited user must either have permission to create symlinks (Developer Mode), or you must provide admin credentials for `nvm use`. The latter is safer but less convenient.

---

## File Map (Who Has What, Where)

*note: replace placeholders like `<ssh_limited_user>` and `<key_name>` with your own values.*

| Actor                               | Purpose                        | File              | Exact Path / Notes                                                                     |
| ----------------------------------- | ------------------------------ | ----------------- | -------------------------------------------------------------------------------------- |
| macOS (SSH client)                  | **Private key** (stays on Mac) | `<key_name>`      | `~/.ssh/<key_name>`                                                                    |
| macOS (SSH client)                  | **Public key** (copy from Mac) | `<key_name>.pub`  | `~/.ssh/<key_name>.pub`                                                                |
| Windows (SSHD server, admin)        | SSH server config              | `sshd_config`     | `%ProgramData%\ssh\sshd_config`                                                        |
| Windows (SSHD server, limited user) | Authorized keys                | `authorized_keys` | `C:\Users\<ssh_limited_user>\.ssh\authorized_keys` ← **paste the Mac public key here** |

---

## Windows 11 (SSHD Server)

### 1) Ensure OpenSSH Server is installed
PowerShell (Admin):
```powershell
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH*'
```
You should see `OpenSSH.Server` as `Installed`.

### 2) Start and enable the SSH service
PowerShell (Admin):
```powershell
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
Get-Service sshd
```
Expected: `Status` is `Running`.

### 3) Harden sshd_config (minimal edits)
Open as admin:
```
%ProgramData%\ssh\sshd_config
```

**Do not edit the huge default block.** Instead, append a **small override block at the end** of the file:
```
# --- Custom overrides (LAN-only + key auth) ---
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no

# Optional: bind sshd to the server LAN IP (replace with your SSHD server IP)
ListenAddress <sshd_server_ip>

# Optional: restrict to a single user
AllowUsers <ssh_limited_user>
```

> Note: **Do not disable TCP forwarding** if you plan to use VS Code Remote‑SSH. It relies on port forwarding. The default allows it, so leave it alone.

If your Windows user is in the **Administrators** group, keep this default block as-is and **make sure it stays last** in the file:
```
Match Group administrators
       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```

Restart:
```powershell
Restart-Service sshd
```

### 4) Create a non-admin SSH user (recommended)
If your existing Windows user is an **Administrator**, **create a dedicated non-admin SSH user**. This is the safest option and prevents the SSH account from doing admin-level damage.

PowerShell (Admin):
```powershell
$pass = Read-Host "Password for <ssh_limited_user>" -AsSecureString
New-LocalUser -Name "<ssh_limited_user>" -Password $pass -FullName "<ssh_limited_user>" -Description "SSH limited user"
Remove-LocalGroupMember -Group "Administrators" -Member "<ssh_limited_user>"
```

If the remove command errors, the user was not in Administrators (safe to ignore).

Then update `AllowUsers` to:
```
AllowUsers <ssh_limited_user>
```

### 5) Add your macOS public key
Create the file if it doesn’t exist:
```
C:\Users\<ssh_limited_user>\.ssh\authorized_keys
```
Paste your macOS public key (see macOS steps below) into that file.

> **Do not** change `AuthorizedKeysFile` unless you know why; use the default per-user location.
> If your Windows user is in **Administrators**, Windows may use:
> `C:\ProgramData\ssh\administrators_authorized_keys`

### 6) Restrict firewall to LAN and your SSH client IP
The firewall rule is **not** part of `sshd_config`. It must be set in your firewall UI.

For the built-in Windows Defender Firewall:
Open **Windows Defender Firewall** → **Inbound Rules** → **OpenSSH SSH Server**:
- **Scope** → **Remote IP address** → **Add** your **SSH client IP** (the machine that will connect).

For Norton Firewall:
If you use **Norton 360** as the active firewall, create the equivalent inbound rule there (TCP port 22, remote IP = **SSH client IP**).

Norton rule example (summary):
- Search **Firewall** → **Traffic Rules** → **Add**
- Protocol: **TCP**
- Direction: **Inbound**
- Remote address: `<ssh_client_ip>`
- Local port: `22`
- Remote port: leave blank
- Reporting: Notification or Security History
- Save

---

## macOS (SSH Client)

### 1) Generate an SSH key (if you don’t already have one)
```bash
ssh-keygen -t ed25519 -C "<ssh_limited_user>@mac" -f ~/.ssh/<key_name>
```
This writes to `~/.ssh/<key_name>` and `~/.ssh/<key_name>.pub`.

### 2) Show your public key
```bash
cat ~/.ssh/<key_name>.pub
```
Copy the output and paste into Windows `authorized_keys` file on the Windows machine's user home, e.g. `C:\Users\<ssh_limited_user>\.ssh\authorized_keys`.

### 3) Verify SSH connection
```bash
ssh <ssh_limited_user>@<sshd_server_ip>
```
Expected: you should get a shell on Windows without a password prompt.

---

## VS Code Insiders (Remote‑SSH)

1. Install **VS Code Insiders**.
2. Install the **Remote‑SSH** extension.
3. Command Palette → **Remote‑SSH: Connect to Host…** → `user@host`.
4. Confirm the status bar shows `SSH: <sshd_server_ip>`.

---

## WSL2 (Optional)

Once connected to Windows in VS Code Insiders:
- Use **Remote‑WSL: Connect to WSL** to open the Ubuntu distro.
- Verify in a terminal:
```bash
uname -a
```

---

## Troubleshooting

### Check SSH service status (Windows)
```powershell
Get-Service sshd
```

### Inspect SSH logs (Windows)
```powershell
Get-WinEvent -LogName OpenSSH/Operational -MaxEvents 50
```

### Confirm Windows IP
```powershell
ipconfig
```
Look for your LAN adapter’s IPv4 address.

---

## Security Notes
- Keep SSH LAN‑only; do not forward port 22 on your router.
- Use key‑only auth.
- Consider a dedicated Windows user with minimal privileges for SSH.
