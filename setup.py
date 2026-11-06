from setuptools import setup

APP = ["run_live.py"]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/AppIcon.icns",
    "packages": ["connector", "mac_agent"],
    "plist": {
        "CFBundleName": "Grok Mac Connector",
        "CFBundleDisplayName": "Grok Mac Connector",
        "CFBundleIdentifier": "com.grokmacconnector.app",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "10",
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
    },
}

setup(
    app=APP,
    name="Grok Mac Connector",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
