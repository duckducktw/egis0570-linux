#!/usr/bin/env python3
"""Idempotent patch for the KDE Plasma lock screen (MainBlock.qml):
the key that wakes the lock screen (clock view -> password view) is swallowed
instead of being typed into the password box. Afterwards typing is normal.

Re-applied after plasma-desktop-data upgrades via
/etc/apt/apt.conf.d/99-lockscreen-patch. Pristine copy: /root/MainBlock.qml.orig
"""
import os, shutil, sys
F = '/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/MainBlock.qml'
ORIG = '/root/MainBlock.qml.orig'
MARK = '// [local-patch] wakeKeySwallow'
OLD_MARK = '// [local-patch] typingArmed'

s = open(F).read()
done_main = MARK in s
if done_main:
    pass
elif OLD_MARK in s:                    # previous click/Tab variant: start from pristine
    s = open(ORIG).read()
elif not os.path.exists(ORIG):
    shutil.copy2(F, ORIG)
else:
    shutil.copy2(F, ORIG)              # package upgrade shipped a new pristine file

def sub(old, new):
    global s
    if s.count(old) != 1:
        print('anchor not found/unique:', old[:60]); sys.exit(1)
    s = s.replace(old, new, 1)

if not done_main:
    sub("    property bool lockScreenUiVisible: false\n",
        "    property bool lockScreenUiVisible: false\n"
        "    " + MARK + ": key that wakes the UI is not typed\n"
        "    signal wakeRequested()\n")
    sub("            Keys.onPressed: event => {\n"
        "                if (event.key === Qt.Key_Left && !text) {",
        "            Keys.onPressed: event => {\n"
        "                if (!sessionManager.lockScreenUiVisible) {\n"
        "                    sessionManager.wakeRequested();\n"
        "                    event.accepted = true;\n"
        "                    return;\n"
        "                }\n"
        "                if (event.key === Qt.Key_Left && !text) {")
    open(F, 'w').write(s)

L = os.path.join(os.path.dirname(F), 'LockScreenUi.qml')
u = open(L).read()
if MARK not in u:
    shutil.copy2(L, '/root/LockScreenUi.qml.orig')
    old = "                lockScreenUiVisible: lockScreenRoot.uiVisible\n"
    if u.count(old) != 1:
        print('anchor not found in LockScreenUi.qml'); sys.exit(1)
    u = u.replace(old, old + "                " + MARK + "\n"
                  "                onWakeRequested: lockScreenRoot.uiVisible = true\n", 1)

# Fingerprint from the clock view / screen off: stock QML only calls
# startAuthenticating() when uiVisible changes, so a freshly locked screen
# that nobody touched has no fingerprint listener. Start it at load. The
# timer covers the grace period (startAuthenticating() is a no-op while
# graceLocked) and the 3 s after a wrong password; it is a no-op while
# already Authenticating. pam_fprintd itself runs with unlimited tries and
# no timeout (/etc/pam.d/kde-fingerprint), because a non-interactive
# failure never returns the authenticators to Idle.
FP = '// [local-patch] fingerprintAlways'
if FP not in u:
    old = "        Component.onCompleted: launchAnimation.start();\n"
    if u.count(old) != 1:
        print('anchor not found: launchAnimation'); sys.exit(1)
    u = u.replace(old,
        "        " + FP + "\n"
        "        Component.onCompleted: {\n"
        "            launchAnimation.start();\n"
        "            if (!graceLockTimer.running)\n"
        "                authenticator.startAuthenticating();\n"
        "        }\n"
        "        Timer {\n"
        "            id: fpRearmTimer\n"
        "            interval: 1500\n"
        "            repeat: true\n"
        "            running: true\n"
        "            onTriggered: {\n"
        "                if (!authenticator.unlocked && !graceLockTimer.running)\n"
        "                    authenticator.startAuthenticating();\n"
        "            }\n"
        "        }\n", 1)

# Fingerprint after suspend/resume (KDE bug 508247): the reader is
# re-enumerated on resume and fprintd restarts, so pam_fprintd returns
# PAM_AUTHINFO_UNAVAIL. The greeter then marks the fingerprint worker
# permanently unavailable and never runs it again. /etc/pam.d/kde-fingerprint
# therefore maps every non-success to pam_deny (PAM_AUTH_ERR), and here a
# failed non-interactive attempt is simply retried after 2 s on the same
# authenticator. Only a PAM success unlocks; this only re-runs PAM.
FP2 = '// [local-patch] fingerprintRetry'
if FP2 not in u:
    old = "            id: fpRearmTimer\n"
    if u.count(old) != 1:
        print('anchor not found: fpRearmTimer'); sys.exit(1)
    i = u.index(old)
    # end of the fpRearmTimer block: its onTriggered body closes with
    # "            }\n", then the Timer itself with "        }\n"
    k = u.index("            }\n", u.index("            onTriggered: {\n", i))
    j = u.index("        }\n", k + len("            }\n")) + len("        }\n")
    u = (u[:j] +
        "        " + FP2 + "\n"
        "        Timer {\n"
        "            id: fpRetryTimer\n"
        "            interval: 2000\n"
        "            property var auth: null\n"
        "            onTriggered: {\n"
        "                if (auth && !authenticator.unlocked)\n"
        "                    auth.tryUnlock();\n"
        "            }\n"
        "        }\n"
        "        Connections {\n"
        "            target: authenticator\n"
        "            function onFailed(kind, auth) {\n"
        "                if (kind != 0 && auth) {\n"
        "                    fpRetryTimer.auth = auth;\n"
        "                    fpRetryTimer.restart();\n"
        "                }\n"
        "            }\n"
        "        }\n" + u[j:])
open(L, 'w').write(u)
print('patched')
