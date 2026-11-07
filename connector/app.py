"""macOS menu bar UI for the unofficial Grok Mac Connector."""
from __future__ import annotations

import subprocess
import threading
import time
import webbrowser

import rumps
from rumps import rumps as _rumps_impl

from . import __version__, config
from .agent_mgr import AgentManager
from .tunnel_mgr import TunnelManager

GROK_CONNECTORS_URL = "https://grok.com/connectors"
ONBOARDING_MARKER = config.APP_SUPPORT_DIR / "onboarding-v0.1-shown"

HOW_TO_USE = """You only need to remember one thing: open the app, then add the connector in Grok.

1. OPEN GROK MAC CONNECTOR
Double-click Grok Mac Connector.app. Look for the small circle in the top menu bar (and the Dock icon). The app starts your Mac connection for you.

2. WAIT FOR READY
The connector creates your free Cloudflare Quick Tunnel automatically. When it is ready, the MCP URL is available.

3. ADD TO GROK
Go to grok.com/connectors → New Connector → Custom. Paste the tunnel URL (use Copy MCP URL from the menu). Complete any auth Grok requests.

4. IF GROK NEEDS FULL COMPUTER ACCESS
Grok can request Full Computer Mode. Your Mac will show an approval dialog. If you approve it, the running connector switches immediately — no config edit or restart.

5. IF GROK ASKS FOR THE ACCESS KEY
Click the menu-bar circle, choose Copy Access Key, and paste it only into Grok's secure credential field if prompted.

IF YOU RESTART OR THE CONNECTION BREAKS
Open Grok Mac Connector again, or choose Reconnect & Copy Setup from the menu. Wait for the Ready notification, then update the connector URL in Grok if it changed. That's it.

The menu-bar icon and Dock icon stay visible so you always know the connector is running."""

def _handle_application_reopen(delegate, ns_app, has_visible_windows):
    """Treat reopening the already-running .app as reconnect-and-copy."""
    state = getattr(delegate, "_app", {})
    callback = state.get("_reopen_callback") if isinstance(state, dict) else None
    if callback:
        callback()
    return True


setattr(
    _rumps_impl.NSApp,
    "applicationShouldHandleReopen_hasVisibleWindows_",
    _handle_application_reopen,
)


PRIVACY_PANES = {
    "files": "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders",
    "full_disk": "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
}


class ConnectorApp(rumps.App):
    def __init__(self):
        super().__init__("Grok Mac Connector", title="◉", quit_button=None)
        self.agent = AgentManager()
        self.tunnel = TunnelManager()
        self.token = config.ensure_agent_token()
        self._copy_when_ready = True
        self._open_grok_when_ready = False
        self._show_first_run = not ONBOARDING_MARKER.exists()
        self._reopen_callback = self._handle_app_reopen

        permissions = rumps.MenuItem("Permissions & Capabilities")
        permissions.add(rumps.MenuItem("About Permissions", callback=self.copy_permissions_guide))
        permissions.add(rumps.MenuItem("Open Files & Folders Settings", callback=self.open_files_permissions))
        permissions.add(rumps.MenuItem("Open Full Disk Access Settings", callback=self.open_full_disk_access))
        permissions.add(rumps.MenuItem("Open Automation Settings", callback=self.open_automation_permissions))
        permissions.add(rumps.MenuItem("Open Accessibility Settings", callback=self.open_accessibility_permissions))
        permissions.add(rumps.MenuItem("Open Screen Recording Settings", callback=self.open_screen_permissions))

        advanced = rumps.MenuItem("Advanced Setup")
        advanced.add(rumps.MenuItem("Open Config File", callback=self.open_config))
        advanced.add(rumps.MenuItem("Open Scripts Folder", callback=self.open_scripts_folder))
        advanced.add(rumps.MenuItem("Open Connector Data Folder", callback=self.open_data_folder))

        self.menu = [
            rumps.MenuItem("Status", callback=None),
            None,
            rumps.MenuItem("How to Use — Easy Steps", callback=self.show_how_to_use),
            rumps.MenuItem("Capability Index", callback=self.show_capability_index),
            rumps.MenuItem("Enable Full Computer Mode", callback=self.enable_full_computer_mode),
            rumps.MenuItem("Open Grok Connectors", callback=self.open_grok_connectors),
            rumps.MenuItem("Reconnect & Copy Setup", callback=self.restart_tunnel),
            rumps.MenuItem("Copy MCP URL", callback=self.copy_url),
            rumps.MenuItem("Copy Access Key", callback=self.copy_access_key),
            permissions,
            advanced,
            None,
            rumps.MenuItem("Start Connector", callback=self.start_connector),
            rumps.MenuItem("Stop Connector", callback=self.stop_connector),
            None,
            rumps.MenuItem("Pause Agent", callback=self.toggle_pause),
            rumps.MenuItem("View Agent Log", callback=self.view_log),
            None,
            rumps.MenuItem("Quit Connector", callback=self.quit_connector),
            rumps.MenuItem(f"v{__version__}", callback=None),
        ]
        self._ensure_services()
        self._refresh()

    def _notify(self, message: str) -> None:
        rumps.notification("Grok Mac Connector", "", message)

    def _ensure_services(self) -> None:
        if not self.agent.is_running():
            self.agent.start(self.token)
        if self.agent.is_running() and TunnelManager.installed() and not self.tunnel.is_running():
            self.tunnel.start()

    def _refresh(self) -> None:
        agent_status = "running" if self.agent.is_running() else "stopped"
        tunnel_status = "running" if self.tunnel.is_running() else "stopped"
        paused = " (PAUSED)" if self.agent.paused() else ""
        url = self.tunnel.public_url or "starting..."
        self.menu["Status"].title = (
            f"Agent: {agent_status}{paused} | Tunnel: {tunnel_status}\n{url}"
        )
        self.title = "◉" if self.agent.is_running() and self.tunnel.is_running() else "○"

    def _copy(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text.encode(), check=False)

    def _queue_connection_copy(self, *, open_grok: bool = False) -> None:
        self._ensure_services()
        self._copy_when_ready = True
        self._open_grok_when_ready = self._open_grok_when_ready or open_grok
        self._finish_connection_copy_if_ready()

    def _finish_connection_copy_if_ready(self) -> bool:
        if not self._copy_when_ready or not self.tunnel.public_url:
            return False
        self._copy(self.tunnel.public_url)
        if self._open_grok_when_ready:
            webbrowser.open(GROK_CONNECTORS_URL)
        self._copy_when_ready = False
        self._open_grok_when_ready = False
        self._notify("Ready — MCP URL copied. Open grok.com/connectors and paste it as a Custom connector.")
        return True

    def _handle_app_reopen(self) -> None:
        self.restart_tunnel(None)

    def _clear_access_key_later(self) -> None:
        token = self.token

        def worker():
            time.sleep(60)
            current = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False).stdout
            if current == token:
                subprocess.run(["pbcopy"], input=b"", check=False)

        threading.Thread(target=worker, daemon=True).start()

    def show_how_to_use(self, _):
        rumps.alert(
            title="Grok Mac Connector — How to Use",
            message=HOW_TO_USE,
            ok="Got it",
        )
        try:
            ONBOARDING_MARKER.write_text("shown\n")
        except OSError:
            pass
        self._show_first_run = False

    def show_capability_index(self, _):
        try:
            index = self.agent.capabilities(self.token)
            lines = [f"Mode: {index['mode']}",
                     f"Filesystem: {index.get('filesystem_scope', 'unknown')}",
                     f"Commands: {index.get('command_execution', 'unknown')}", ""]
            for name, spec in index["packs"].items():
                status = "ON" if spec["enabled"] else "off"
                lines.append(f"{name}: {status} — {spec['description']}")
            message = "\n".join(lines)
        except (OSError, ValueError, KeyError) as exc:
            message = f"Cannot read the running helper's capability index: {exc}"
        rumps.alert(title="Grok Mac Connector — Capability Index", message=message, ok="Done")

    def enable_full_computer_mode(self, _):
        result = self.agent.enable_full_mode(self.token)
        self._refresh()
        if result.get("ok"):
            self._notify("Full Computer Mode enabled and verified: user-accessible files, general commands and installed apps.")
        else:
            rumps.alert(title="Full Computer Mode", message=result.get("error", "Activation failed."), ok="Done")

    def _open_privacy_pane(self, pane: str, label: str) -> None:
        url = PRIVACY_PANES[pane]
        subprocess.Popen(["open", url])
        self._notify(f"Opened {label}. Grant only the access you want this connector to have.")

    def copy_permissions_guide(self, _):
        guide = (
            "Grok Mac Connector permissions guide\n\n"
            "Restricted Mode limits file work to configured folders. Full Computer Mode removes those "
            "connector folder fences and lets Grok work anywhere your logged-in Mac account can access.\n\n"
            "macOS still controls protected data and app control. Full Disk Access may be needed for protected "
            "files; Accessibility is needed for clicking/typing; Screen Recording is needed for visual inspection; "
            "and Automation permissions may appear when controlling apps. The connector cannot silently grant "
            "those macOS permissions."
        )
        self._copy(guide)
        self._notify("Permissions guide copied.")

    def open_files_permissions(self, _):
        self._open_privacy_pane("files", "Files & Folders settings")

    def open_full_disk_access(self, _):
        self._open_privacy_pane("full_disk", "Full Disk Access settings")

    def open_automation_permissions(self, _):
        self._open_privacy_pane("automation", "Automation settings")

    def open_accessibility_permissions(self, _):
        self._open_privacy_pane("accessibility", "Accessibility settings")

    def open_screen_permissions(self, _):
        self._open_privacy_pane("screen", "Screen Recording settings")

    def open_config(self, _):
        from mac_agent.config import write_example_config
        path = config.APP_SUPPORT_DIR / "config.yaml"
        write_example_config(str(path))
        subprocess.Popen(["open", "-e", str(path)])
        self._notify("Config opened. Changes apply after restarting the connector.")

    def open_scripts_folder(self, _):
        path = config.APP_SUPPORT_DIR / "scripts"
        path.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", str(path)])

    def open_data_folder(self, _):
        config.ensure_dirs()
        subprocess.Popen(["open", str(config.APP_SUPPORT_DIR)])

    def start_connector(self, _):
        self._queue_connection_copy()
        self._refresh()
        self._notify("Connector starting. MCP URL will copy automatically when ready.")

    def stop_connector(self, _):
        self.tunnel.stop()
        self.agent.stop()
        self._copy_when_ready = False
        self._open_grok_when_ready = False
        self._refresh()
        self._notify("Connector stopped.")

    def open_grok_connectors(self, _):
        webbrowser.open(GROK_CONNECTORS_URL)
        self._queue_connection_copy()

    def copy_access_key(self, _):
        self._copy(self.token)
        self._clear_access_key_later()
        self._notify("Access key copied for 60 seconds. Paste it only into Grok's secure field if asked.")

    def restart_tunnel(self, _):
        self.tunnel.stop()
        self._copy_when_ready = True
        self._open_grok_when_ready = False
        if self.agent.is_running(self.token) and self.tunnel.start():
            self._notify("Reconnecting. The new MCP URL will copy automatically when ready.")
        else:
            self._notify("Reconnect failed. Check the agent log or choose Start Connector.")
        self._refresh()

    def copy_url(self, _):
        if not self.tunnel.public_url:
            self._notify("No tunnel URL yet.")
            return
        self._copy(self.tunnel.public_url)
        self._notify("MCP URL copied. Paste it at grok.com/connectors → Custom.")

    def toggle_pause(self, sender):
        paused = not self.agent.paused()
        self.agent.set_paused(paused)
        sender.title = "Resume Agent" if paused else "Pause Agent"
        self._notify("Agent paused." if paused else "Agent resumed.")
        self._refresh()

    def view_log(self, _):
        subprocess.Popen(["open", str(self.agent.log_path)])

    def quit_connector(self, _):
        self.tunnel.stop()
        self.agent.stop()
        rumps.quit_application()

    @rumps.timer(2)
    def _tick(self, _):
        self._ensure_services()
        self._refresh()
        self._finish_connection_copy_if_ready()
        if self._show_first_run and self.tunnel.public_url:
            self.show_how_to_use(None)


def main():
    config.ensure_dirs()
    ConnectorApp().run()


if __name__ == "__main__":
    main()
