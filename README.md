# TyrePing website

Static website for **https://www.tyreping.com**. Plain HTML, CSS and JavaScript; no app server, dependency installation or build step.

## Preview

```sh
python3 -m http.server 8080 --directory public
```

Open http://localhost:8080. Apache reads `public/.htaccess` in production for canonical redirects, the custom 404 response, cache policy, compression and security headers.

## Check and deploy

```sh
python3 scripts/check.py
bash scripts/deploy.sh
```

Deployment targets `paul@webhost2:/var/www/html/tyreping.com/`. The script validates the site, backs up the existing directory outside the document root, and copies only `public/`. It does not delete remote files. Source and maintenance scripts are never published. SSH key authentication, rsync and curl are required.

The backup path is printed during deployment. To restore a backup, SSH to the host and extract it into the web directory; restore or remove `.htaccess` as appropriate if reverting to a version without it. The initial deployment backs up the original placeholder page.

## Releases and content

App source: https://github.com/TerminalAddict/TyrePing, branch `tyreping`. Downloads deliberately identify **v0.5.0 as a preview**. The stable alternative links through GitHub's latest stable release page. GitHub's `/releases/latest` endpoint excludes prereleases.

For a new release, update the version, tag, APK and checksum links in `public/index.html` and `public/install/index.html`, plus `softwareVersion` in homepage JSON-LD. Update FAQ and install instructions together if the process changes. Add a real Google Play URL and official badge once the listing is public.

## Screenshots

Original captures are preserved in `tyreping screenshots/`. The homepage uses actual car and tandem-axle trailer screens in its hero and includes a gallery of all seven supplied captures. Each screen has 540px and 1080px WebP assets in `public/assets/images/screenshots/`, descriptive alt text, intrinsic dimensions and a full-size link. Clicking a screenshot (including either hero image) or its full-size link opens an accessible modal with previous/next controls, arrow keys, touch swipes and a zoom control for viewing the original 1080px image. Escape, the close button or the backdrop closes the modal and restores focus. Direct image URLs remain available without JavaScript. Below-the-fold gallery images are lazy-loaded. The gallery works as a static collection without JavaScript; JavaScript adds a screenshot selector. Screenshots show example readings, not live sensor data or recommended settings.

When replacing screenshots, keep the original aspect ratio, update both WebP sizes, and update the `SoftwareApplication.screenshot` entries in homepage JSON-LD. Use a new asset filename for changed images to avoid stale browser caches. Keep the screenshot count, gallery labels and descriptions consistent.

## Assets and metadata

The dedicated `/licenses/` page credits TPMS Advanced (Vincent Masselis and contributors) and Persistent TPMS (aveshev and contributors), reproduces the complete Apache 2.0 licence, and links downloadable licence and attribution text. Both checked upstream `develop` snapshots have identical licence files and no `NOTICE`/`NOTICE.*` file. Their reviewed commit IDs are recorded on the page and in `public/licenses/ATTRIBUTIONS.txt`; update this information when incorporating new upstream code. Keep copyright and attribution notices intact. The page also links the website font's OFL notice. This website page does not package notices into an Android APK; maintain the app's own bundled licence/notices when releasing it.

- App artwork is copied from TyrePing's `mipmap-xxxhdpi/ic_launcher.png`; favicon and social-card derivatives use that icon. Preserve its provenance and branding.
- Manrope variable font is self-hosted; its licence is in `public/assets/fonts/OFL.txt`.
- Interface icons and vehicle illustrations are native SVG.
- Pages include canonical metadata, Open Graph and Twitter cards, and JSON-LD. There are no invented reviews, ratings, prices or store listings.
- `robots.txt`, `sitemap.xml`, `site.webmanifest`, Apple/Android icons, a maskable icon, PNG favicons and multi-resolution ICO are included.
- No analytics, ads, forms, external embeds, cookies, browser storage or service worker. The privacy page describes hosting access logs and external GitHub downloads.

Change sitemap `lastmod` only for pages whose content changed. Run checks and test mobile navigation, FAQ disclosure, the screenshot selector and download links before deploying. `scripts/check.py` uses only Python's standard library.
