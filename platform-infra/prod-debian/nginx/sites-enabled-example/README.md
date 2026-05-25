# Example Site Enablement

```bash
sudo cp platform-infra/prod-debian/nginx/nightcraft.conf /etc/nginx/sites-available/nightcraft.conf
sudo ln -s /etc/nginx/sites-available/nightcraft.conf /etc/nginx/sites-enabled/nightcraft.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```
