# Private project sites on Azure Static Web Apps

For organizations on Microsoft 365: only colleagues who sign in with the organization's Microsoft
account can open the project site.

1. Create an Azure Static Web App (Standard plan: restricting sign-in to your own tenant uses
   custom authentication, which is only available on Standard).
2. Register an app in Microsoft Entra ID; store its client ID and secret as the app settings
   `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` of the Static Web App.
3. Copy `staticwebapp.config.json` to `.github/` in the project repository and replace `<TENANT_ID>`.
4. Copy `publish-project-site.yml` to `.github/workflows/` and add the deployment token as the
   repository secret `AZURE_STATIC_WEB_APPS_API_TOKEN`.

Every saved change to `.bimai/` then rebuilds the site. The site sends `noindex` and `no-store`
headers so it's never indexed or cached.

Other options: an internal web server (copy `.bimai/site/out/`), or a zip file for a one-off hand-over.
Never publish a project site to a public host.
