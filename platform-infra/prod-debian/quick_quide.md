# FLOWS

## DEPLOYMENT

### Clean debian 12 server, Fresh install

#### Prequisites

- working ssh(ssh ionos-dev), scp, and sudo access to the server
- server has debian 12 installed and updated

#### sync code to server (scp, no git)

directly copy the changed files instead of whole folders because app-researchAgent has 50mb worth of text files. its failing over scp.
If the whole holder needs to be copied, a much better way is to zip it and unzip on the server.

Run these from local machine before deployment scripts:

scp -r "D:/dev_work/web_dev/personal site/ionos-server/platform-infra/prod-debian" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/service-auth" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/app-radio" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/app-landing" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/app-artsy" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/app-admin" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/app-researchAgent" ionos-dev:/platform-infra/
scp -r "D:/dev_work/web_dev/personal site/ionos-server/app-game" ionos-dev:/platform-infra/

#### commands to run

cd /platform-infra/prod-debian/scripts
chmod +x *.sh
sudo ./install-env.sh
sudo ./setup-postgres.sh
sudo ./install-systemd.sh
sudo ./install-nginx.sh
sudo ./deploy-all.sh
./status-all.sh

`deploy-all.sh` now also seeds the auth DB with one standard user role account and one admin role account, in addition to OAuth client seeds.


## OTHER DEPLOYMENT RELATED CODES

If only postgres SQL templates changed:

scp -r "D:/dev_work/web_dev/personal site/ionos-server/platform-infra/prod-debian/postgres/" ionos-dev:/platform-infra/prod-debian/