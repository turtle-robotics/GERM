# M8 synthetic offline host operating instructions

These commands run a local host simulation, not the Pi or production services. Install the repository's pinned host dependencies in the existing virtual environment first; offline installation requires previously available local packages. No runtime internet access or model download is required. Do not point the launcher at deployed data or copy over a live DB/image directory.

From the repository root, initialize a **new** disposable host workspace:

```powershell
New-Item -ItemType Directory -Force build/offline-demo
.venv/Scripts/python.exe pi_hmi/offline_host.py --workspace build/offline-demo --create --port 5055
```

Open `http://127.0.0.1:5055`. The seven screens use local assets. The built-in adapter only acknowledges synthetic STATUS/OFF; sensors, physical camera/model and crop timing approvals are absent. The CLI deliberately leaves the POST authorizer unset: it does not enable command, export, backup or recovery POSTs. Trusted test harnesses explicitly provide their synthetic input/authorizer; no CLI/env/browser option turns those tests into production controls.

For a later run use the same command without `--create`. Startup remains inhibited and no schedule resumes automatically. `--create` cannot recreate a missing marked database or adopt a pre-existing unmarked database. An unavailable/corrupt database needs a separately reviewed repair/restore procedure into a new offline location; do not delete/rewrite it or remove the marker to suppress the fault. Existing M7 restores remain isolated copies and are never auto-adopted.

The collapsed service summary shows local connection and host readiness. Expand it for dependencies and recovery guidance. Internet loss should not affect the loopback HMI. If the browser cannot reach this local server, values/permission status become unknown, commands are not queued, and reconnect only refreshes state. A missing camera/model/sensor is not evidence of healthy data. Historical exports/results remain historical, not current measurements.

In an explicitly authorized synthetic harness, **Recover host services** stops/quiesces old owners and rebuilds dependencies. If a worker/request/export/backup/inference is still active, recovery refuses rather than creating a duplicate worker. Wait for the existing job to finish and inspect its durable receipt. After recovery, recheck fresh inputs; grow schedules require a separate confirmed Start, camera scheduling requires explicit reconfiguration and the existing M5 clock recovery rule still applies. Never use an old confirmation/status as permission.

Before Ctrl+C, let exports/backups/inference finish. Shutdown inhibits first and requests STOP only through M1, then releases idle owners. A forced process exit can leave incomplete stages/running receipts; the next startup reports them interrupted and does not replay them. Retry only explicitly using the existing M6/M7 interfaces, which preserve previous attempts. Do not clear quotas by deleting historical data; the retention proposal is still awaiting approval.

For keyboard use, Tab to the visible skip link and Enter to focus page content. Navigation identifies the current page; controls show a visible focus outline. Command dialogs initially focus Cancel; Escape cancels. Scroll each screen for all controls at 739×447. Scripted checks do not replace target/human accessibility and usability acceptance.

Run the complete host campaign with `python pi_hmi/tests/run_host_checks.py --root-app --output build/m8-evidence`; run the six M1/M4/M5/M6/M7/M8 Chromium flows as in CI. No firmware flashing, hardware access, production installation/deployment, history deletion, PR merging or Gantt updates is part of this procedure.
