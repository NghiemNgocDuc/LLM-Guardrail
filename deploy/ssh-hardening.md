# SSH Hardening — server setup notes

Run these on the host machine **before** deploying.

```bash
# 1. Disable password auth
sudo sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# 2. Disable root login
sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sudo sed -i 's/^#PermitRootLogin prohibit-password/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config

# 3. Use key-based auth only
sudo sed -i 's/^#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#AuthorizedKeysFile/AuthorizedKeysFile/' /etc/ssh/sshd_config

# 4. Restart SSH
sudo systemctl restart sshd

# 5. Install fail2ban
sudo apt install -y fail2ban
sudo cp deploy/fail2ban-docker.conf /etc/fail2ban/jail.d/guardrails.conf
sudo systemctl restart fail2ban

# 6. Firewall — only 80, 443, SSH
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow ssh
sudo ufw enable

# 7. Automatic security updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```
